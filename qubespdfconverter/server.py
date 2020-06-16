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
import subprocess
import sys

from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory

DEPTH = 8
STDIN_READ_SIZE = 65536


def unlink(path):
    """Wrapper for pathlib.Path.unlink(path, missing_ok=True)"""
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


async def terminate_proc(proc):
    if proc.returncode is None:
        proc.terminate()
        await proc.wait()


async def wait_proc(proc, cmd):
    try:
        await proc.wait()
    except asyncio.CancelledError:
        await terminate_proc(proc)
        raise

    if proc.returncode:
        raise subprocess.CalledProcessError(proc.returncode, cmd)


def send_b(data):
    """Qrexec wrapper for sending binary data to the client"""
    if isinstance(data, (str, int)):
        data = str(data).encode()

    sys.stdout.buffer.write(data)
    sys.stdout.buffer.flush()


def send(data):
    """Qrexec wrapper for sending text data to the client"""
    print(data, flush=True)


def recv_b():
    """Qrexec wrapper for receiving binary data from the client"""
    untrusted_data = sys.stdin.buffer.read()
    if not untrusted_data:
        raise EOFError
    return untrusted_data


class Representation:
    """Umbrella object for a file's initial and final representations

    The initial representation must be of a format from which we can derive
    the final representation without breaking any of its requirements.
    Generally, this makes the initial representation some sort of image file
    (e.g. PNG, JPEG).

    The final representation must be of a format such that if the initial
    representation contains malicious code/data, such code/data is excluded
    from the final representation upon conversion. Generally, this makes the
    final representation a relatively simple format (e.g., RGB bitmap).

    :param path: Path to original, unsanitized file
    :param prefix: Path prefix for representations
    :param f_suffix: File extension of initial representation (without .)
    :param i_suffix: File extension of final representation (without .)
    """

    def __init__(self, path, prefix, i_suffix, f_suffix):
        self.path = path
        self.page = prefix.name
        self.initial = prefix.with_suffix(f".{i_suffix}")
        self.final = prefix.with_suffix(f".{f_suffix}")
        self.dim = None


    async def convert(self):
        """Convert initial representation to final representation"""
        cmd = [
            "convert",
            str(self.initial),
            "-depth",
            str(DEPTH),
            f"rgb:{self.final}"
        ]

        await self.create_irep()
        self.dim = await self._dim()

        proc = await asyncio.create_subprocess_exec(*cmd)
        try:
            await wait_proc(proc, cmd)
        finally:
            await asyncio.get_running_loop().run_in_executor(
                None,
                unlink,
                self.initial
            )


    async def create_irep(self):
        """Create initial representation"""
        cmd = [
            "pdftocairo",
            str(self.path),
            "-png",
            "-f",
            str(self.page),
            "-l",
            str(self.page),
            "-singlefile",
            str(Path(self.initial.parent, self.initial.stem))
        ]

        proc = await asyncio.create_subprocess_exec(*cmd)
        await wait_proc(proc, cmd)


    async def _dim(self):
        """Identify image dimensions of initial representation"""
        cmd = ["identify", "-format", "%w %h", str(self.initial)]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=subprocess.PIPE
        )

        try:
            output, _ = await proc.communicate()
        except asyncio.CancelledError:
            await terminate_proc(proc)
            raise

        return output.decode("ascii")


@dataclass(frozen=True)
class BatchEntry:
    task: asyncio.Task
    rep: Representation


class BaseFile:
    """Unsanitized file"""
    def __init__(self, path):
        self.path = path
        self.pagenums = 0
        self.batch = None


    async def sanitize(self):
        """Start sanitization tasks"""
        self.pagenums = self._pagenums()
        self.batch = asyncio.Queue(self.pagenums)

        send(self.pagenums)

        publish_task = asyncio.create_task(self._publish())
        consume_task = asyncio.create_task(self._consume())

        try:
            await asyncio.gather(publish_task, consume_task)
        except subprocess.CalledProcessError:
            await cancel_task(publish_task)

            while not self.batch.empty():
                convert_task = await self.batch.get()
                await cancel_task(convert_task)
                self.batch.task_done()

            raise


    def _pagenums(self):
        """Return the number of pages in the suspect file"""
        cmd = ["pdfinfo", str(self.path)]
        output = subprocess.run(cmd, capture_output=True, check=True)
        pages = 0

        for line in output.stdout.decode().splitlines():
            if "Pages:" in line:
                pages = int(line.split(":")[1])

        return pages


    async def _publish(self):
        """Extract initial representations and enqueue conversion tasks"""
        for page in range(1, self.pagenums + 1):
            rep = Representation(
                self.path,
                Path(self.path.parent, str(page)),
                "png",
                "rgb"
            )
            task = asyncio.create_task(rep.convert())
            batch_e = BatchEntry(task, rep)
            await self.batch.join()

            try:
                await self.batch.put(batch_e)
            except asyncio.CancelledError:
                await cancel_task(task)
                raise


    async def _consume(self):
        """Await conversion tasks and send final representation to client"""
        for _ in range(self.pagenums):
            batch_e = await self.batch.get()
            await batch_e.task

            rgb_data = await asyncio.get_running_loop().run_in_executor(
                None,
                batch_e.rep.final.read_bytes
            )

            await asyncio.get_running_loop().run_in_executor(
                None,
                unlink,
                batch_e.rep.final
            )

            await asyncio.get_running_loop().run_in_executor(
                None,
                send,
                batch_e.rep.dim
            )
            send_b(rgb_data)

            self.batch.task_done()


def main():
    try:
        data = recv_b()
    except EOFError:
        sys.exit(1)

    with TemporaryDirectory(prefix="qvm-sanitize") as tmpdir:
        pdf_path = Path(tmpdir, "original")
        pdf_path.write_bytes(data)
        base = BaseFile(pdf_path)

        loop = asyncio.get_event_loop()
        try:
            loop.run_until_complete(base.sanitize())
        except subprocess.CalledProcessError:
            sys.exit(1)


if __name__ == "__main__":
    main()
