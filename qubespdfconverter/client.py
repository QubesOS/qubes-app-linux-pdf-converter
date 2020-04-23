#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# The Qubes OS Project, http://www.qubes-os.org
#
# Copyright (C) 2013 Joanna Rutkowska <joanna@invisiblethingslab.com>
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.

import asyncio
import functools
import logging
import os
import subprocess
import sys
from collections import namedtuple
from pathlib import Path
from PIL import Image
from tempfile import TemporaryDirectory

PROG_NAME = Path(sys.argv[0]).name
ARCHIVE_PATH = Path(Path.home(), "QubesUntrustedPDFs")

MAX_PAGES = 10000
MAX_IMG_WIDTH = 10000
MAX_IMG_HEIGHT = 10000
DEPTH = 8

Dimensions = namedtuple("Dimensions", ["width", "height", "size", "depth"])
Representation = namedtuple("Representations", ["initial", "final"])


class DimensionError(ValueError):
    """
    """


class PageError(ValueError):
    """
    """


class ReceiveError(Exception):
    """Raise if an error occurs when reading from STDOUT"""


###############################
#         Utilities
###############################


def check_paths(paths):
    abs_paths = []

    for path in [Path(path) for path in paths]:
        abspath = Path.resolve(path)

        if not abspath.exists():
            logging.error(f"No such file: \"{path}\"")
            sys.exit(1)
        elif not abspath.is_file():
            logging.error(f"Not a regular file: \"{path}\"")
            sys.exit(1)

        abs_paths.append(abspath)

    return abs_paths


def check_range(val, upper):
    if not 1 <= val <= upper:
        raise ValueError


def unlink(path):
    """Wrapper for Path.unlink(path, missing_ok=True)"""
    try:
        path.unlink()
    except FileNotFoundError:
        pass


async def cancel_task(task):
    if not task.done():
        task.cancel()
        await task


async def wait_proc(proc):
    await proc.wait()
    if proc.returncode:
        raise subprocess.CalledProcessError


async def terminate_proc(proc):
    if proc.returncode is None:
        proc.terminate()
        await proc.wait()


###############################
#       Qrexec-related
###############################


async def recv_b(proc, size):
    """Qrexec wrapper for receiving binary data from the server"""
    try:
        untrusted_data = await proc.stdout.readexactly(size)
    except asyncio.IncompleteReadError as e:
        # got EOF before @size bytes received
        raise ReceiveError from e

    return untrusted_data


async def recvline_b(proc):
    """Qrexec wrapper for receiving a line of binary data from the server"""
    untrusted_data = await proc.stdout.readline()

    if not untrusted_data:
        logging.error("server may have died...")
        raise ReceiveError

    return untrusted_data


async def recvline(proc):
    """Convenience wrapper for receiving a line of text data from the server"""
    try:
        untrusted_data = (await recvline_b(proc)).decode("ascii").rstrip()
    except EOFError as e:
        logging.error("server may have died...")
        raise ReceiveError from e
    except (AttributeError, UnicodeError):
        logging.error("failed to decode received data!")
        raise

    return untrusted_data


async def send(proc, data):
    """Qrexec wrapper for sending data to the server"""
    if isinstance(data, (str, int)):
        data = str(data).encode()

    proc.stdin.write(data)
    try:
        await proc.stdin.drain()
    except BrokenPipeError:
        raise



###############################
#        Image-related
###############################


async def get_img_dim(proc):
    try:
        untrusted_w, untrusted_h = map(int, (await recvline(proc)).split(" ", 1))
    except (AttributeError, EOFError, UnicodeError, ValueError) as e:
        raise ReceiveError from e

    try:
        check_range(untrusted_w, MAX_IMG_WIDTH)
        check_range(untrusted_h, MAX_IMG_HEIGHT)
    except ValueError as e:
        logging.error(f"invalid image measurements received {e}")
        raise DimensionError from e
    else:
        width = untrusted_w
        height = untrusted_h

    size = width * height * 3

    return Dimensions(width=width, height=height, size=size, depth=DEPTH)


###############################
#         PDF-related
###############################


async def send_pdf(loop, proc, path):
    try:
        data = await loop.run_in_executor(None, path.read_bytes)
        await send(proc, data)
        proc.stdin.write_eof()
    except BrokenPipeError:
        raise


async def recv_pagenums(loop, proc):
    try:
        untrusted_pagenums = int(await recvline(proc))
    except (AttributeError, EOFError, UnicodeError, ValueError) as e:
        raise ReceiveError from e

    try:
        check_range(untrusted_pagenums, MAX_PAGES)
    except ValueError as e:
        logging.error("invalid number of pages received")
        raise PageError from e
    else:
        pagenums = untrusted_pagenums

    return pagenums


def archive(path):
    archive_path = Path(ARCHIVE_PATH, path.name)
    path.rename(archive_path)
    print(f"Original PDF saved as: {archive_path}")


###############################
#    Representation-related
###############################


def get_rep(tmpdir, page, initial, final):
    name = Path(tmpdir, str(page))
    return Representation(initial=name.with_suffix(f".{initial}"),
                          final=name.with_suffix(f".{final}"))


async def recv_rep(loop, proc, tmpdir, page):
    """Receive initial representation from the server

    :param loop: Event loop
    """
    try:
        dim = await get_img_dim(proc)
        data = await recv_b(proc, dim.size)
    except (DimensionError, ReceiveError):
        raise

    rep = get_rep(tmpdir, page, "rgb", "png")
    await loop.run_in_executor(None, rep.initial.write_bytes, data)

    return rep, dim


async def convert_rep(loop, rep, dim):
    """Convert initial representation into final representation"""
    cmd = ["convert", "-size", f"{dim.width}x{dim.height}", "-depth",
           f"{dim.depth}", f"rgb:{rep.initial}", f"png:{rep.final}"]

    try:
        proc = await asyncio.create_subprocess_exec(*cmd)
        await wait_proc(proc)
    except asyncio.CancelledError:
        await terminate_proc(proc)
    except subprocess.CalledProcessError:
        logging.error(f"Conversion failed for page {rep.final.with_suffix('')}")
        raise

    await loop.run_in_executor(None, unlink, rep.initial)


async def combine_reps(loop, save_path, freps):
    images = []

    try:
        tasks = [loop.run_in_executor(None, Image.open, frep) for frep in freps]
        images = await asyncio.gather(*tasks)
    except IOError:
        logging.error("Cannot identify image")
        await asyncio.gather(*[loop.run_in_executor(None, img.close)
                               for img in images])
        raise

    try:
        await loop.run_in_executor(None, functools.partial(
                                            images[0].save,
                                            save_path,
                                            "PDF",
                                            resolution=100,
                                            append=save_path.exists(),
                                            append_images=images[1:],
                                            save_all=True))
    except IOError:
        logging.error(f"Could not write to {save_path}")
        await loop.run_in_executor(None, unlink, save_path)
        raise
    finally:
        await asyncio.gather(*[loop.run_in_executor(None, img.close)
                               for img in images])


###############################
#           Main
###############################


async def receive(loop, proc, pagenums, tmpdir, rep_q):
    for page in range(1, pagenums + 1):
        try:
            rep, dim = await recv_rep(loop, proc, tmpdir, page)
        except (DimensionError, ReceiveError):
            raise

        await rep_q.put((rep, dim))


async def convert_batch(loop, convert_q, save_path):
    convert_tasks = []
    freps = []

    try:
        while not convert_q.empty():
            convert_task, frep = await convert_q.get()
            convert_tasks.append(convert_task)
            freps.append(frep)
            convert_q.task_done()

        try:
            await asyncio.gather(*convert_tasks)
            await combine_reps(loop, save_path, freps)
        except IOError:
            raise
        except subprocess.CalledProcessError:
            await asyncio.gather(*[cancel_task(task) for task in convert_tasks])
            raise

        await asyncio.gather(*[loop.run_in_executor(None, unlink, frep)
                               for frep in freps])
    except asyncio.CancelledError:
        await asyncio.gather(*[cancel_task(task) for task in convert_tasks])


async def convert(loop, path, pagenums, rep_q, convert_q):
    save_path = path.with_suffix(".trusted.pdf")

    for page in range(1, pagenums + 1):
        rep, dim = await rep_q.get()
        convert_task = asyncio.create_task(convert_rep(loop, rep, dim))
        await convert_q.put((convert_task, rep.final))
        rep_q.task_done()

        if convert_q.full() or page == pagenums:
            try:
                await convert_batch(loop, convert_q, save_path)
            except (IOError, subprocess.CalledProcessError):
                raise

    return save_path


async def sanitize(loop, proc, path):
    rep_q = asyncio.Queue(50)
    convert_q = asyncio.Queue(50)

    try:
        pagenums = await recv_pagenums(loop, proc)
    except (PageError, ReceiveError):
        raise

    with TemporaryDirectory(prefix="qvm-sanitize-") as tmpdir:
        receive_task = asyncio.create_task(receive(loop, proc, pagenums, tmpdir,
                                                   rep_q))
        convert_task = asyncio.create_task(convert(loop, path, pagenums, rep_q,
                                                   convert_q))

        try:
            _, save_path = await asyncio.gather(receive_task, convert_task)
        except (DimensionError, ReceiveError):
            cancel_task(convert_task)
            raise
        except (IOError, subprocess.CalledProcessError):
            cancel_task(receive_task)
            raise

    print(f"\nConverted PDF saved as: {save_path}")


async def run(loop, paths):
    cmd = ["/usr/bin/qrexec-client-vm", "@dispvm", "qubes.PdfConvert"]
    procs = []
    send_tasks = []
    sanitize_tasks = []

    print("Sending files to Disposable VMs...")

    for path in paths:
        proc = await asyncio.create_subprocess_exec(*cmd,
                                                    stdin=subprocess.PIPE,
                                                    stdout=subprocess.PIPE)
        procs.append(proc)
        send_tasks.append(asyncio.create_task(send_pdf(loop, proc, path)))
        sanitize_tasks.append(asyncio.create_task(sanitize(loop, proc, path)))

    for proc, path, send_task, sanitize_task in zip(procs, paths, send_tasks,
                                                    sanitize_tasks):
        try:
            await asyncio.gather(send_task, sanitize_task, wait_proc(proc))
        except (BrokenPipeError, DimensionError, PageError, ReceiveError,
                subprocess.CalledProcessError) as e:
            await asyncio.gather(cancel_task(send_task),
                                 cancel_task(sanitize_task))
            await terminate_proc(proc)
        else:
            await loop.run_in_executor(None, archive, path)


def main():
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    if len(sys.argv) == 1:
        print(f"usage: {PROG_NAME} [FILE ...]", file=sys.stderr)
        sys.exit(1)

    paths = check_paths(sys.argv[1:])
    Path.mkdir(ARCHIVE_PATH, exist_ok=True)

    try:
        loop = asyncio.get_event_loop()
        loop.run_until_complete(run(loop, paths))
    except KeyboardInterrupt:
        logging.error("Original files untouched.")
    finally:
        loop.run_until_complete(loop.shutdown_asyncgens())


if __name__ == "__main__":
    main()
