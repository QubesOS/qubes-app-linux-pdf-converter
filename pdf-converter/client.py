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
    """
    """


class RepresentationError(ValueError):
    """
    """


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


# TODO (?): Size limit for readline()
async def recvline_b(proc):
    """Qrexec wrapper for receiving a line of binary data from the server"""
    untrusted_data = await proc.stdout.readline()

    if not untrusted_data:
        logging.error("server may have died...")
        raise ReceiveError

    return untrusted_data


# async def recv(proc, size):
    # """Convenience wrapper for receiving text data from the server"""
    # try:
        # untrusted_data = (await recv_b(proc, size)).decode()
    # except ReceiveError
        # raise
    # except (AttributeError, UnicodeError):
        # logging.error("failed to decode received data!")
        # raise

    # return untrusted_data


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
        filesize = (await loop.run_in_executor(None, path.stat)).st_size
        await send(proc, f"{filesize}\n")

        data = await loop.run_in_executor(None, path.read_bytes)
        await send(proc, data)
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

    :param proc: Qrexec process to read STDIN from
    :param path: File path which will store the initial representation
    """
    rep = get_rep(tmpdir, page, "rgb", "png")

    try:
        dim = await get_img_dim(proc)
        data = await recv_b(proc, dim.size)
    except (DimensionError, ReceiveError, RepresentationError):
        raise

    # @size bytes must have been received if we're here, so a check on how much
    # is written to @rep.initial isn't needed.
    #
    # Also, since the server sends the dimensions and contents of each page in a
    # simple loop, if the server only sends @size - N bytes for a particular
    # page, either:
    #
    #  1. We'll eventually get @size bytes later on as recv_b() will mistake the
    #  other pages' dimensions and contents as part of the current page's
    #  contents and we end up with a malformed irep, which we'll handle later
    #  during representation's conversion.
    #
    #  2. The server exits (the loop is the last thing it does) and we get an
    #  EOF, causing a ReceiveError.
    await loop.run_in_executor(None, rep.initial.write_bytes, data)

    return rep, dim


async def start_convert(rep, dim):
    cmd = ["convert", "-size", f"{dim.width}x{dim.height}", "-depth",
            f"{dim.depth}", f"rgb:{rep.initial}", f"png:{rep.final}"]

    try:
        proc = await asyncio.create_subprocess_exec(*cmd)
        await wait_proc(proc)
    except asyncio.CancelledError:
        terminate_proc(proc)

    return proc


# TODO (?): Save->delete PNGs in loop to avoid storing all PNGs in memory.
# TODO: Add error handling
def combine_reps(save_path, reps):
    with Image.open(reps[0].final) as first:
        remaining = [Image.open(rep.final) for rep in reps[1:]]
        first.save(save_path, "PDF", resolution=100, append_images=remaining,
                   save_all=True)

    for img in remaining:
        img.close()


###############################
#           Main
###############################

async def receive(loop, proc, tmpdir):
    procs = []
    reps = []

    try:
        pagenums = await recv_pagenums(loop, proc)
    except (PageError, ReceiveError):
        raise

    for page in range(1, pagenums + 1):
        try:
            rep, dim = await recv_rep(loop, proc, tmpdir, page)
        except (DimensionError, ReceiveError, RepresentationError):
            term_tasks = [terminate_proc(p) for p in procs]
            await asyncio.gather(*term_tasks)
            raise

        reps.append(rep)
        procs.append(await start_convert(rep, dim))

    return procs, reps


async def convert(loop, path, procs, reps):
    for proc, rep in zip(procs, reps):
        try:
            await wait_proc(proc)
        except subprocess.CalledProcessError:
            logging.error("page conversion failed")
            raise

        await loop.run_in_executor(None, unlink, rep.initial)

    save_path = path.with_suffix(".trusted.pdf")
    await loop.run_in_executor(None, combine_reps, save_path, reps)

    return save_path


async def sanitize(loop, proc, path):
    with TemporaryDirectory(prefix=f"qvm-sanitize-") as tmpdir:
        try:
            convert_procs, reps = await receive(loop, proc, tmpdir)
        except (DimensionError, PageError, ReceiveError, RepresentationError):
            raise

        try:
            pdf = await convert(loop, path, convert_procs, reps)
        except (asyncio.CancelledError, subprocess.CalledProcessError):
            for proc in convert_procs:
                terminate_proc(proc)
            raise

    print(f"\nConverted PDF saved as: {pdf}")


# TODO: KeyboardInterrupt
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
            await asyncio.gather(send_task,
                                 sanitize_task,
                                 wait_proc(proc))
        except (BrokenPipeError, DimensionError, PageError, ReceiveError,
                RepresentationError, subprocess.CalledProcessError):
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
        logging.error("Original file untouched.")
    finally:
        loop.run_until_complete(loop.shutdown_asyncgens())


if __name__ == "__main__":
    main()
