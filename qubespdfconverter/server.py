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
import subprocess
import sys
from collections import namedtuple
from pathlib import Path
from tempfile import TemporaryDirectory

DEPTH = 8
STDIN_READ_SIZE = 65536

Representation = namedtuple("Representation", ["initial", "final"])


class ConversionError(Exception):
    """
    """

class ReceiveError(Exception):
    """
    """


###############################
#         Utilities
###############################


def info(msg, suffix=None):
    """Qrexec wrapper for displaying information on the client

    @suffix is really only ever used when @msg needs to overwrite the line of
    the previous message (imitating an updating line). This is done by setting
    @suffix to "\r".
    """
    print(msg, end=suffix, flush=True, file=sys.stderr)


def unlink(path):
    """Wrapper for Path.unlink(path, missing_ok=True)"""
    try:
        path.unlink()
    except FileNotFoundError:
        pass


async def cancel_task(task):
    task.cancel()
    try:
        await task
    except:
        pass


async def wait_proc(proc, cmd):
    await proc.wait()
    if proc.returncode:
        raise subprocess.CalledProcessError(proc, returncode, cmd)


async def terminate_proc(proc):
    if proc.returncode is None:
        proc.terminate()
        await proc.wait()


###############################
#       Qrexec-related
###############################


def recv_b():
    """Qrexec wrapper for receiving binary data from the client"""
    try:
        untrusted_data = sys.stdin.buffer.read()
    except EOFError as e:
        raise ReceiveError from e

    if not untrusted_data:
        raise ReceiveError

    return untrusted_data


def recvline():
    """Qrexec wrapper for receiving a line of text data from the client"""
    try:
        untrusted_data = sys.stdin.buffer.readline().decode("ascii")
    except (AttributeError, EOFError, UnicodeError) as e:
        raise ReceiveError from e

    return untrusted_data


def send_b(data):
    """Qrexec wrapper for sending binary data to the client's STDOUT"""
    if isinstance(data, (str, int)):
        data = str(data).encode()

    sys.stdout.buffer.write(data)
    sys.stdout.buffer.flush()


def send(data):
    """Qrexec wrapper for sending text data to the client's STDOUT"""
    print(data, flush=True)


###############################
#         Rep-related
###############################


def get_rep(tmpdir, page, initial, final):
    """Create temporary file for page representations"""
    name = Path(tmpdir, f"{page}")
    return Representation(initial=name.with_suffix(f".{initial}"),
                          final=name.with_suffix(f".{final}"))


###############################
#        Image-related
###############################


async def get_irep(pdfpath, irep, page):
    cmd = ["pdftocairo", f"{pdfpath}", "-png", "-f", f"{page}", "-l",
           f"{page}", "-singlefile", f"{Path(irep.parent, irep.stem)}"]

    try:
        proc = await asyncio.create_subprocess_exec(*cmd)
        await wait_proc(proc, cmd)
    except asyncio.CancelledError:
        await terminate_proc(proc)
        raise
    except subprocess.CalledProcessError:
        raise


async def get_img_dim(irep):
    cmd = ["identify", "-format", "%w %h", f"{irep}"]

    try:
        proc = await asyncio.create_subprocess_exec(*cmd, stdout=subprocess.PIPE)
        output, _ = await proc.communicate()
    except asyncio.CancelledError:
        await terminate_proc(proc)
        raise
    except subprocess.CalledProcessError:
        raise

    return output.decode("ascii")


async def convert_rep(irep, frep):
    cmd = ["convert", f"{irep}", "-depth", f"{DEPTH}", f"rgb:{frep}"]

    try:
        proc = await asyncio.create_subprocess_exec(*cmd)
        await wait_proc(proc, cmd)
    except asyncio.CancelledError:
        await terminate_proc(proc)
        raise
    except subprocess.CalledProcessError:
        raise


async def render(loop, page, pdfpath, rep):
    try:
        try:
            irep_task = asyncio.create_task(get_irep(pdfpath, rep.initial, page))
            await irep_task

            dim_task = asyncio.create_task(get_img_dim(rep.initial))
            convert_task = asyncio.create_task(convert_rep(rep.initial, rep.final))
            dim, _ = await asyncio.gather(dim_task, convert_task)
        except subprocess.CalledProcessError:
            raise
        finally:
            await loop.run_in_executor(None, unlink, rep.initial)

        return (dim, rep.final)
    except asyncio.CancelledError:
        await asyncio.gather(cancel_task(irep_task), cancel_task(dim_task),
                             cancel_task(convert_task))
        raise


###############################
#         PDF-related
###############################


def get_pagenums(pdfpath):
    cmd = ["pdfinfo", f"{pdfpath}"]

    try:
        output = subprocess.run(cmd, capture_output=True, check=True)
    except subprocess.CalledProcessError:
        # TODO: Support converting JPGs and PNGs like the OG script
        logging.error("file is probably not a PDF")
        raise

    for line in output.stdout.decode("ascii").splitlines():
        if "Pages:" in line:
            return int(line.split(":")[1])


###############################
#            Main
###############################


async def recv_pages(loop, queue, path, tmpdir, pagenums):
    for page in range(1, pagenums + 1):
        rep = get_rep(tmpdir, page, "png", "rgb")
        task = asyncio.create_task(render(loop, page, path, rep))

        try:
            await queue.put(task)
        except asyncio.CancelledError:
            await cancel_task(task)
            queue.task_done()
            raise


async def send_pages(loop, queue, pagenums):
    for page in range(1, pagenums + 1):
        task = await queue.get()

        try:
            dim, frep = await task
        except subprocess.CalledProcessError:
            raise
        else:
            queue.task_done()

        send(dim)
        send_b(await loop.run_in_executor(None, frep.read_bytes))
        await loop.run_in_executor(None, unlink, frep)


async def run(loop, path, tmpdir, pagenums):
    queue = asyncio.Queue(pagenums)
    recv_task = asyncio.create_task(recv_pages(loop, queue, path, tmpdir, pagenums))
    send_task = asyncio.create_task(send_pages(loop, queue, pagenums))

    try:
        await asyncio.gather(recv_task, send_task)
    except subprocess.CalledProcessError:
        await cancel_task(recv_task)

        while not queue.empty():
            task = await queue.get()
            await cancel_task(task)
            queue.task_done()

        raise


def main():
    logging.basicConfig(level=logging.INFO, format="DispVM: %(message)s")

    try:
        pdf_data = recv_b()
    except ReceiveError:
        sys.exit(1)

    with TemporaryDirectory(prefix="qvm-sanitize-") as tmpdir:
        pdfpath = Path(tmpdir, "original")
        pdfpath.write_bytes(pdf_data)

        try:
            pagenums = get_pagenums(pdfpath)
            send(pagenums)
        except subprocess.CalledProcessError:
            sys.exit(1)

        try:
            loop = asyncio.get_event_loop()
            loop.run_until_complete(run(loop, pdfpath, tmpdir, pagenums))
        except subprocess.CalledProcessError:
            sys.exit(1)
        finally:
            loop.run_until_complete(loop.shutdown_asyncgens())


if __name__ == "__main__":
    main()
