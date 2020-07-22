#!/usr/bin/python3
# -*- coding: utf-8 -*-

# The Qubes OS Project, https://www.qubes-os.org
#
# Copyright (C) 2013 Joanna Rutkowska <joanna@invisiblethingslab.com>
# Copyright (C) 2020 Jason Phan <td.satch@gmail.com>
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

###########################
# A similar project exist:
# - https://github.com/firstlookmedia/dangerzone-converter
# Both projects can improve the other.
###########################

import asyncio
import subprocess
import sys
import os
import socket
import time
from pathlib import Path
from dataclasses import dataclass
from tempfile import TemporaryDirectory
import magic
import uno

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


    async def convert(self, password):
        """Convert initial representation to final representation"""
        cmd = [
            "gm",
            "convert",
            str(self.initial),
            "-depth",
            str(DEPTH),
            f"rgb:{self.final}"
        ]

        await self.create_irep(password)
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


    async def create_irep(self, password):
        """Create initial representation"""
        cmd = [
            "pdftocairo",
            "-opw",
            password,
            "-upw",
            password,
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
        try:
            await wait_proc(proc, cmd)
        except subprocess.CalledProcessError:
            cmd = [
                "gm",
                "convert",
                str(self.path),
                f"png:{self.initial}"
            ]
            proc = await asyncio.create_subprocess_exec(*cmd)
            await wait_proc(proc, cmd)


    async def _dim(self):
        """Identify image dimensions of initial representation"""
        cmd = ["gm", "identify", "-format", "%w %h", str(self.initial)]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=subprocess.PIPE
        )

        try:
            output, _ = await proc.communicate()
        except asyncio.CancelledError:
            await terminate_proc(proc)
            raise
        return output.partition(b"\n")[0].decode("ascii")


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
        self.password = ""

    def _read_password(self, password_success):
        if not password_success:
            cmd = ["zenity", "--title", "File protected by password", "--password"]
            self.password = subprocess.run(cmd, capture_output=True, check=True)\
                .stdout.split(b"\n")[0]


    def _decrypt(self):
        """
        Try to remove the password of a libreoffice-compatible file,
        and store the resulting file in INITIAL_NAME.nopassword.
        The steps are:
        - Connect to a libreoffice API server, listening on localhost on port 2202
        - Try to load a document with additionnal properties:
              - "Hidden" to not load any libreoffice GUI
              - "Password" to automatically try to decrypt the document
        - Store the document without additionnal properties [this remove the password]
        """

        src = "file://"+str(self.path)
        dst = "file://"+str(self.path)+".nopassword"

        local_context = uno.getComponentContext()
        resolver = local_context.ServiceManager.createInstanceWithContext(
            "com.sun.star.bridge.UnoUrlResolver",
            local_context
        )
        ctx = resolver.resolve(
            "uno:socket,host=localhost,port=2202;urp;StarOffice.ComponentContext"
        )
        smgr = ctx.ServiceManager
        desktop = smgr.createInstanceWithContext("com.sun.star.frame.Desktop", ctx)

        hidden_property = uno.createUnoStruct("com.sun.star.beans.PropertyValue")
        hidden_property.Name = "Hidden"
        hidden_property.Value = True

        password_property = uno.createUnoStruct("com.sun.star.beans.PropertyValue")
        password_property.Name = "Password"
        password_property.Value = self.password

        document = desktop.loadComponentFromURL(
            src,
            "_blank",
            0,
            (password_property, hidden_property,)
        )
        document.storeAsURL(dst, ())


    async def sanitize(self):
        """Start sanitization tasks"""

        password_success = False
        mimetype = magic.detect_from_filename(str(self.path)).mime_type
        if mimetype.startswith("video/") or mimetype.startswith("audio/"):
            raise ValueError
        if mimetype.startswith("image/"):
            self.pagenums = 1
        else:
            if mimetype == "application/pdf":
                while not password_success:
                    cmd = ["pdfinfo", "-opw", self.password, "-upw", self.password, str(self.path)]
                    try:
                        password_success = not b"Incorrect password" in subprocess.\
                                run(cmd, capture_output=True, check=True).stderr
                    except subprocess.CalledProcessError:
                        password_success = False
                        self._read_password(password_success)
            else:
                # Performance could be improved by only starting
                # the libreoffice when needed (aka: when the file need to be decrypted).
                # But code is simpler that way

                # Launch libreoffice server
                cmd = [
                    "libreoffice",
                    "--accept=socket,host=localhost,port=2202;urp;",
                    "--norestore",
                    "--nologo",
                    "--nodefault"
                ]
                libreoffice_process = subprocess.Popen(cmd, stderr=open(os.devnull, 'wb'))

                # Wait until libreoffice server is ready
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(1)
                while sock.connect_ex(('127.0.0.1', 2202)) != 0:
                    time.sleep(1)

                # Remove password from file using libreoffice API
                while not password_success:
                    try:
                        self._decrypt()
                        password_success = True
                    except:
                        self._read_password(False)

                libreoffice_process.terminate()
                cmd = [
                    "libreoffice",
                    "--convert-to",
                    "pdf",
                    str(self.path) + ".nopassword",
                    "--outdir",
                    self.path.parents[0]
                ]
                subprocess.run(cmd, capture_output=True, check=True)
                os.rename(str(self.path) + ".pdf", str(self.path))

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
        cmd = ["pdfinfo", "-opw", self.password, "-upw", self.password, str(self.path)]
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
            task = asyncio.create_task(rep.convert(self.password))
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
