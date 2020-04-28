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
from pathlib import Path
from tempfile import TemporaryDirectory

DEPTH = 8
STDIN_READ_SIZE = 65536


class ReceiveError(Exception):
    """Raised if a STDOUT read failed in a qrexec-client-vm subprocess"""


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
    """Qrexec wrapper for sending binary data to the client

    :param data: Data to send (bytes, String, or int)
    """
    if isinstance(data, (str, int)):
        data = str(data).encode()

    sys.stdout.buffer.write(data)
    sys.stdout.buffer.flush()


def send(data):
    """Qrexec wrapper for sending text data to the client

    :param data: Data to send
    """
    print(data, flush=True)


class Representation(object):
    """Umbrella object for the initial & final representations of a file

    The initial representation must be of a format from which we can derive
    the final representation without breaking any of its requirements.
    Generally, this makes the initial representation some sort of image file
    (e.g. PNG, JPEG).

    The final representation must be of a format such that if the initial
    representation contains malicious code/data, such code/data is excluded
    from the final representation upon conversion. Generally, this makes the
    final representation a relatively simple format (e.g., RGB bitmap).

    :param loop: Main event loop
    :param path: Path to original, unsanitized file
    :param prefix: Path prefixes of the representations
    :param initial: The format of the initial representation
    :param final: The format of the final representation
    """

    def __init__(self, loop, path, prefix, initial, final):
        self.loop = loop
        self.path = path
        self.page = prefix.name
        self.initial = prefix.with_suffix(f".{initial}")
        self.final = prefix.with_suffix(f".{final}")
        self.dim = None


    async def convert(self):
        """Convert initial representation to final representation"""
        try:
            irep_task = asyncio.create_task(self._irep())
            await irep_task
        except asyncio.CancelledError:
            await cancel_task(irep_task)
            raise
        except subprocess.CalledProcessError:
            raise

        try:
            dim_task = asyncio.create_task(self._dim())
            self.dim = await dim_task
        except asyncio.CancelledError:
            await cancel_task(dim_task)
            raise
        except subprocess.CalledProcessError:
            raise

        cmd = [
            "convert",
            f"{self.initial}",
            "-depth",
            f"{DEPTH}",
            f"rgb:{self.final}"
        ]

        try:
            proc = await asyncio.create_subprocess_exec(*cmd)
            await wait_proc(proc, cmd)
        except asyncio.CancelledError:
            await terminate_proc(proc)
            raise
        except subprocess.CalledProcessError:
            raise
        finally:
            await self.loop.run_in_executor(None, unlink, self.initial)


    async def _irep(self):
        """Create initial representation"""
        cmd = [
            "pdftocairo",
            f"{self.path}",
            "-png",
            "-f",
            f"{self.page}",
            "-l",
            f"{self.page}",
            "-singlefile",
            f"{Path(self.initial.parent, self.initial.stem)}"
        ]

        try:
            proc = await asyncio.create_subprocess_exec(*cmd)
            await wait_proc(proc, cmd)
        except asyncio.CancelledError:
            await terminate_proc(proc)
            raise
        except subprocess.CalledProcessError:
            raise


    async def _dim(self):
        """Identify image dimensions of initial representation"""
        cmd = ["identify", "-format", "%w %h", f"{self.initial}"]

        try:
            proc = await asyncio.create_subprocess_exec(*cmd,
                                                        stdout=subprocess.PIPE)
            output, _ = await proc.communicate()
        except asyncio.CancelledError:
            await terminate_proc(proc)
            raise
        except subprocess.CalledProcessError:
            raise

        return output.decode("ascii")


class BaseFile(object):
    """Unsanitized file

    :param loop: Main event loop
    :param path: Path to file
    """

    def __init__(self, loop, path):
        self.path = path
        self.dir = path.parent
        self.pagenums = None

        self.loop = loop
        self.queue = None

        try:
            data = recv_b()
            self.path.write_bytes(data)
        except ReceiveError:
            raise


    async def sanitize(self):
        """Start sanitization tasks"""
        try:
            self.pagenums = await self.loop.run_in_executor(None, self._pagenums)
            send(self.pagenums)
            self.queue = asyncio.Queue(self.pagenums)
        except subprocess.CalledProcessError:
            raise

        publish_task = asyncio.create_task(self._publish())
        consume_task = asyncio.create_task(self._consume())

        try:
            await asyncio.gather(publish_task, consume_task)
        except subprocess.CalledProcessError:
            await cancel_task(publish_task)

            while not self.queue.empty():
                convert_task = await self.queue.get()
                await cancel_task(convert_task)
                self.queue.task_done()

            raise


    async def _publish(self):
        """Extract initial representations and enqueue conversion tasks"""
        for page in range(1, self.pagenums + 1):
            rep = Representation(self.loop, self.path, Path(self.dir, str(page)),
                                 "png", "rgb")

            try:
                convert_task = asyncio.create_task(rep.convert())
                await self.queue.put((rep, convert_task))
            except asyncio.CancelledError:
                await cancel_task(convert_task)
                self.queue.task_done()
                raise
            except subprocess.CalledProcessError:
                raise


    async def _consume(self):
        """Await conversion tasks and send final representation to client"""
        for page in range(1, self.pagenums + 1):
            rep, convert_task = await self.queue.get()

            try:
                await convert_task
            except subprocess.CalledProcessError:
                raise
            else:
                self.queue.task_done()

            send(rep.dim)
            send_b(await self.loop.run_in_executor(None, rep.final.read_bytes))
            await self.loop.run_in_executor(None, unlink, rep.final)


    def _pagenums(self):
        """Return the number of pages in the suspect file"""
        cmd = ["pdfinfo", f"{self.path}"]

        try:
            output = subprocess.run(cmd, capture_output=True, check=True)
        except subprocess.CalledProcessError:
            logging.error("File is probably not a PDF")
            raise

        for line in output.stdout.decode("ascii").splitlines():
            if "Pages:" in line:
                return int(line.split(":")[1])


def main():
    logging.basicConfig(level=logging.INFO, format="DispVM: %(message)s")
    loop = asyncio.get_event_loop()

    with TemporaryDirectory(prefix="qvm-sanitize-") as tmpdir:
        try:
            f = BaseFile(loop, Path(tmpdir, "original"))
            loop.run_until_complete(f.sanitize())
        except (ReceiveError, subprocess.CalledProcessError):
            sys.exit(1)
        finally:
            loop.run_until_complete(loop.shutdown_asyncgens())


if __name__ == "__main__":
    main()
