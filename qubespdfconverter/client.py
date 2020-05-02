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
import click
import functools
import logging
import os
import subprocess
import sys
from click._compat import get_text_stderr
from collections import namedtuple
from pathlib import Path
from PIL import Image
from tempfile import TemporaryDirectory

PROG = Path(sys.argv[0]).name
CLIENT_VM_CMD = ["/usr/bin/qrexec-client-vm", "@dispvm", "qubes.PdfConvert"]

MAX_PAGES = 10000
MAX_IMG_WIDTH = 10000
MAX_IMG_HEIGHT = 10000
DEPTH = 8

ARCHIVE_PATH = Path(Path.home(), "QubesUntrustedPDFs")

Dimensions = namedtuple("Dimensions", ["width", "height", "size", "depth"])


class DimensionError(ValueError):
    """Raised if invalid image dimensions were received"""


class PageError(ValueError):
    """Raised if an invalid number of pages was received"""


class ReceiveError(Exception):
    """Raised if a STDOUT read failed in a qrexec-client-vm subprocess"""


class BadPath(click.BadParameter):
    """Raised if a Path object parsed by Click is invalid."""
    def __init__(self, path, message):
        super().__init__(message, param_hint=f'"{path}"')


def unlink(path):
    """Wrapper for pathlib.Path.unlink(path, missing_ok=True)

    :param Path: File path to delete
    """
    try:
        path.unlink()
    except FileNotFoundError:
        pass


async def cancel_task(task):
    """Convenience wrapper for cancelling an asyncio Task

    Presumably, since we're cancelling tasks, we don't care what they returned
    with or raised.

    :param task: Task to cancel
    """
    task.cancel()
    try:
        await task
    except:
        pass


async def terminate_proc(proc):
    """Convenience wrapper for terminating a process

    :param proc: Process to terminate
    """
    if proc.returncode is None:
        proc.terminate()
        await proc.wait()


async def wait_proc(proc, cmd):
    """Convenience wrapper for waiting on a process

    :param proc: Process to wait on
    :param cmd: Command executed by @proc (Exception handling purposes)
    """
    try:
        await proc.wait()
        if proc.returncode:
            raise subprocess.CalledProcessError(proc.returncode, cmd)
    except asyncio.CancelledError:
        await terminate_proc(proc)


async def send(proc, data):
    """Qrexec wrapper for sending data to the server

    :param proc: qrexec-client-vm process
    :param data: Data to send (bytes, String, or int)
    """
    if isinstance(data, (int, str)):
        data = str(data).encode()

    proc.stdin.write(data)
    try:
        await proc.stdin.drain()
    except BrokenPipeError:
        raise


async def recv_b(proc, size):
    """Qrexec wrapper for receiving binary data from the server

    :param proc: qrexec-client-vm process
    :param size: Number of bytes to receive
    """
    try:
        untrusted_data = await proc.stdout.readexactly(size)
    except asyncio.IncompleteReadError as e:
        raise ReceiveError from e

    return untrusted_data


async def recvline_b(proc):
    """Qrexec wrapper for receiving a line of binary data from the server

    :param proc: qrexec-client-vm process
    """
    untrusted_data = await proc.stdout.readline()

    if not untrusted_data:
        logging.error("Server may have died...")
        raise ReceiveError

    return untrusted_data


async def recvline(proc):
    """Convenience wrapper for receiving a line of text data from the server

    :param proc: qrexec-client-vm process
    """
    try:
        untrusted_data = (await recvline_b(proc)).decode("ascii").rstrip()
    except EOFError as e:
        logging.error("Server may have died...")
        raise ReceiveError from e
    except (AttributeError, UnicodeError):
        logging.error("Failed to decode received data!")
        raise

    return untrusted_data


class Representation(object):
    """Umbrella object for the initial & final representations of a file

    The initial representation must be of a format such that if it contains
    malicious code/data, such code/data is excluded from the final
    representation upon conversion. Generally, this makes the initial
    representation a relatively simple format (e.g., RGB bitmap).

    The final representation can be of any format you'd like, provided that
    the initial representation's format was properly selected and you are
    able to combine them later on into a PDF.

    :param loop: Main event loop
    :param prefix: Path prefixes of the representations
    :param initial: Format of the initial representation
    :param final: Format of the final representation
    """

    def __init__(self, loop, prefix, initial, final):
        self.loop = loop
        self.initial = prefix.with_suffix(f".{initial}")
        self.final = prefix.with_suffix(f".{final}")
        self.dim = None


    async def convert(self):
        """Convert initial representation into final representation"""
        cmd = [
            "convert",
            "-size",
            f"{self.dim.width}x{self.dim.height}",
            "-depth",
            f"{self.dim.depth}",
            f"rgb:{self.initial}",
            f"png:{self.final}"
        ]

        try:
            proc = await asyncio.create_subprocess_exec(*cmd)
            await wait_proc(proc, cmd)
        except asyncio.CancelledError:
            await terminate_proc(proc)
            raise
        except subprocess.CalledProcessError:
            logging.error(f"Page conversion failed")
            raise

        await self.loop.run_in_executor(None, unlink, self.initial)


    async def receive(self, proc):
        """Receive initial representation from the server

        :param proc: qrexec-client-vm process
        """
        try:
            self.dim = await self._dim(proc)
            data = await recv_b(proc, self.dim.size)
        except (DimensionError, ReceiveError):
            raise

        await self.loop.run_in_executor(None, self.initial.write_bytes, data)


    async def _dim(self, proc):
        """Receive and compute image dimensions for initial representation

        :param proc: qrexec-client-vm process
        """
        try:
            untrusted_w, untrusted_h = map(int, (await recvline(proc)).split(" ", 1))
        except (AttributeError, EOFError, UnicodeError, ValueError) as e:
            raise ReceiveError from e

        if 1 <= untrusted_w <= MAX_IMG_WIDTH and \
           1 <= untrusted_h <= MAX_IMG_HEIGHT:
            width = untrusted_w
            height = untrusted_h
        else:
            logging.error(f"invalid image measurements received")
            raise DimensionError

        size = width * height * 3
        return Dimensions(width=width, height=height, size=size, depth=DEPTH)


class BaseFile(object):
    """Unsanitized file

    :param loop: Main event loop
    :param path: Path to original, unsanitized file
    """

    def __init__(self, loop, path):
        self.loop = loop
        self.proc = None
        self.rep_q = None
        self.convert_q = None

        self.orig_path = path
        self.save_path = path.with_suffix(".trusted.pdf")
        self.dir = None
        self.pagenums = None


    async def sanitize(self, size):
        """Start Qubes RPC session and sanitization tasks

        :param size: Batch size for queues
        """
        self.rep_q = asyncio.Queue(size)
        self.convert_q = asyncio.Queue(size)
        self.proc = await asyncio.create_subprocess_exec(*CLIENT_VM_CMD,
                                                         stdin=subprocess.PIPE,
                                                         stdout=subprocess.PIPE)

        proc_task = asyncio.create_task(wait_proc(self.proc, CLIENT_VM_CMD))
        send_task = asyncio.create_task(self._send())
        sanitize_task = asyncio.create_task(self._sanitize())

        try:
            await asyncio.gather(proc_task, send_task, sanitize_task)
        except (BrokenPipeError,
                DimensionError,
                PageError,
                ReceiveError,
                subprocess.CalledProcessError) as e:
            await asyncio.gather(cancel_task(send_task),
                                 cancel_task(sanitize_task),
                                 cancel_task(proc_task))


    async def _sanitize(self):
        """Receive and convert representation files"""
        try:
            self.pagenums = await self._pagenums()
        except (PageError, ReceiveError):
            raise

        with TemporaryDirectory(prefix="qvm-sanitize-") as d:
            self.dir = d
            receive_task = asyncio.create_task(self._receive())
            convert_task = asyncio.create_task(self._convert())

            try:
                await asyncio.gather(receive_task, convert_task)
            except (DimensionError, ReceiveError):
                await cancel_task(convert_task)
                raise
            except (IOError, subprocess.CalledProcessError):
                await cancel_task(receive_task)
                raise

        await self.loop.run_in_executor(None, self._archive)
        print(f"Converted PDF saved as: {self.save_path}")


    async def _receive(self):
        """Receive initial representations"""
        for page in range(1, self.pagenums + 1):
            try:
                rep = Representation(self.loop, Path(self.dir, str(page)),
                                     "rgb", "png")
                await rep.receive(self.proc)
            except (DimensionError, ReceiveError):
                raise

            await self.rep_q.put(rep)


    async def _convert(self):
        """Convert initial representations to final representations"""
        try:
            for page in range(1, self.pagenums + 1):
                rep = await self.rep_q.get()
                convert_task = asyncio.create_task(rep.convert())
                await self.convert_q.put((convert_task, rep.final))
                self.rep_q.task_done()

                if self.convert_q.full() or page == self.pagenums:
                    try:
                        await self._complete_batch()
                    except (IOError, subprocess.CalledProcessError):
                        raise
        except asyncio.CancelledError:
            while not self.convert_q.empty():
                convert_task, _ = await self.convert_q.get()
                await cancel_task(convert_task)
                self.convert_q.task_done()
            raise


    async def _complete_batch(self):
        """Wait on current batch of final representations to be combined"""
        convert_tasks = []
        freps = []

        while not self.convert_q.empty():
            convert_task, frep = await self.convert_q.get()
            convert_tasks.append(convert_task)
            freps.append(frep)
            self.convert_q.task_done()

        try:
            await asyncio.gather(*convert_tasks)
        except subprocess.CalledProcessError:
            for convert_task in convert_tasks:
                await cancel_task(convert_task)
            raise

        try:
            await self._combine_reps(freps)
        except IOError:
            raise

        await asyncio.gather(*[self.loop.run_in_executor(None, unlink, frep)
                               for frep in freps])


    async def _combine_reps(self, freps):
        """Combine final representations into a sanitized PDF file

        :param freps: List of final representations
        """
        try:
            img_tasks = [self.loop.run_in_executor(None, Image.open, frep)
                         for frep in freps]
            images = await asyncio.gather(*img_tasks)
        except IOError:
            logging.error("Cannot identify image")
            await asyncio.gather(*[self.loop.run_in_executor(None, img.close)
                                   for img in images])
            raise

        try:
            await self.loop.run_in_executor(None,
                                            functools.partial(
                                                images[0].save,
                                                self.save_path,
                                                "PDF",
                                                resolution=100,
                                                append=self.save_path.exists(),
                                                append_images=images[1:],
                                                save_all=True))
        except IOError:
            logging.error(f"Could not write to {self.save_path}")
            await self.loop.run_in_executor(None, unlink, self.save_path)
            raise
        finally:
            await asyncio.gather(*[self.loop.run_in_executor(None, img.close)
                                   for img in images])


    async def _send(self):
        """Send original document to server"""
        try:
            data = await self.loop.run_in_executor(None,
                                                   self.orig_path.read_bytes)
            await send(self.proc, data)
            self.proc.stdin.write_eof()
        except BrokenPipeError:
            raise


    async def _pagenums(self):
        """Receive number of pages in original document from server"""
        try:
            untrusted_pagenums = int(await recvline(self.proc))
        except (AttributeError, EOFError, UnicodeError, ValueError) as e:
            raise ReceiveError from e

        try:
            if not 1 <= untrusted_pagenums <= MAX_PAGES:
                raise ValueError
        except ValueError as e:
            logging.error("Invalid number of pages received")
            raise PageError from e
        else:
            pagenums = untrusted_pagenums

        return pagenums


    def _archive(self):
        """Move original file into an archival directory"""
        archive_path = Path(ARCHIVE_PATH, self.orig_path.name)
        self.orig_path.rename(archive_path)
        print(f"\nOriginal PDF saved as: {archive_path}")


def modify_click_errors(func):
    """Decorator for replacing Click behavior on errors"""
    def show(self, file=None):
        """Removes usage message from UsageError error messages"""
        color = None

        if file is None:
            file = get_text_stderr()

        if self.ctx is not None:
            color = self.ctx.color

        click.echo(f"{self.format_message()}", file=file, color=color)

    def format_message(self):
        """Removes 'Invalid value' from BadParameter error messages"""
        if self.param_hint is not None:
            prefix = self.param_hint
        elif self.param is not None:
            prefix = self.param.get_error_hint(self.ctx)
        else:
            return self.message
        prefix = click.exceptions._join_param_hints(prefix)

        return f"{prefix}: {self.message}"

    click.exceptions.BadParameter.format_message = format_message
    click.exceptions.UsageError.show = show

    return func


def validate_paths(ctx, param, untrusted_paths):
    """Callback for validating file paths parsed by Click"""
    for untrusted_path in untrusted_paths:
        if not untrusted_path.resolve().exists():
            raise BadPath(untrusted_path, "No such file or directory")
        elif not untrusted_path.resolve().is_file():
            raise BadPath(untrusted_path, "Not a regular file")

        try:
            with untrusted_path.resolve().open("rb"):
                pass
        except PermissionError:
            raise BadPath(untrusted_path, "Not readable")
    else:
        paths = untrusted_paths

    return paths


async def run(loop, params):
    print("Sending files to Disposable VMs...")
    files = [BaseFile(loop, f) for f in params["files"]]
    await asyncio.gather(*[f.sanitize(params["batch"]) for f in files],
                         return_exceptions=True)


# @click.option("-v", "--verbose", is_flag=True)
@click.command()
@click.option(
    "-b",
    "--batch",
    type=click.IntRange(0),
    default=50,
    metavar="SIZE",
    help="Maximum number of conversion tasks"
)
@click.option(
    "-a",
    "--archive",
    default="~/QubesUntrustedPDFs",
    metavar="PATH",
    help="Directory for storing archived files"
)
@click.option(
    "-d",
    "--dry-run",
    is_flag=True,
    help="Perform only server-side checks and conversions"
)
@click.option(
    "-i",
    "--in-place",
    is_flag=True,
    help="Replace original files instead of archiving them"
)
@click.argument(
    "files",
    type=Path,
    nargs=-1,
    callback=validate_paths,
    metavar="[FILES ...]"
)
@modify_click_errors
def main(**params):
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    if not params["files"]:
        logging.info("No files to sanitize.")
        sys.exit(0)

    Path.mkdir(ARCHIVE_PATH, exist_ok=True)

    try:
        loop = asyncio.get_event_loop()
        loop.run_until_complete(run(loop, params))
    except KeyboardInterrupt:
        logging.error("Original files untouched.")
    finally:
        loop.run_until_complete(loop.shutdown_asyncgens())


if __name__ == "__main__":
    main()
