#!/usr/bin/python3
# -*- coding: utf-8 -*-

# The Qubes OS Project, http://www.qubes-os.org
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

import argparse
import asyncio
import functools
import shutil
import subprocess
import sys

from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory

from qubespdfconverter.constants import LIBREOFFICE_MISSING_EXIT_CODE

try:
    import magic
except ImportError:
    magic = None

DEPTH = 8
STDIN_READ_SIZE = 65536
# Default resolution in ppi (pixel per inch)
RESOLUTION = 300


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


class LibreOfficeMissingError(ValueError):
    """Raised if LibreOffice is missing in the relevant template."""


class PdfRenderer:
    """Render PDF pages into image representations."""

    def __init__(self, path, password=b"", resolution=RESOLUTION):
        self.path = path
        self.password = password
        self.resolution = str(resolution)

    def _password_args(self):
        if not self.password:
            return []
        password = self.password.decode()
        return ["-opw", password, "-upw", password]

    def page_count(self):
        """Return the number of pages in the PDF."""
        cmd = ["pdfinfo"] + self._password_args() + [str(self.path)]
        output = subprocess.run(cmd, capture_output=True, check=True)
        pages = 0

        for line in output.stdout.decode().splitlines():
            if "Pages:" in line:
                pages = int(line.split(":")[1])

        return pages

    async def create_page_image(self, page, output):
        """Render one PDF page into an image."""
        cmd = ["pdftocairo"] + self._password_args()
        cmd += [
            str(self.path),
            "-png",
            "-r",
            self.resolution,
            "-f",
            str(page),
            "-l",
            str(page),
            "-singlefile",
            str(Path(output.parent, output.stem)),
        ]

        proc = await asyncio.create_subprocess_exec(*cmd)
        await wait_proc(proc, cmd)

    async def render_page(self, page, prefix):
        """Create an intermediate page representation."""
        rep = Representation(prefix, "png", "rgb")
        await self.create_page_image(page, rep.initial)
        return rep


class LibreOfficeDocumentRenderer:
    """Convert office documents to PDF, then render the PDF pages."""

    def __init__(self, path, password=b"", resolution=RESOLUTION, suffix=".docx"):
        self.path = path
        self.resolution = resolution
        self.suffix = suffix
        self._pdf_renderer = None

    def pdf_renderer(self):
        if self._pdf_renderer is not None:
            return self._pdf_renderer

        document_path = Path(self.path.parent, "input" + self.suffix)
        shutil.copyfile(self.path, document_path)

        cmd = [
            "libreoffice",
            "--headless",
            "--convert-to",
            "pdf",
            "--outdir",
            str(self.path.parent),
            str(document_path),
        ]
        try:
            subprocess.run(cmd, capture_output=True, check=True)
        except FileNotFoundError as exc:
            raise LibreOfficeMissingError(
                "LibreOffice is required for this file type; "
                "install libreoffice in the relevant template"
            ) from exc

        pdf_path = document_path.with_suffix(".pdf")
        if not pdf_path.exists():
            raise ValueError("document conversion did not produce a PDF")

        self._pdf_renderer = PdfRenderer(pdf_path, resolution=self.resolution)
        return self._pdf_renderer

    def page_count(self):
        """Return the number of pages in the converted document."""
        return self.pdf_renderer().page_count()

    async def render_page(self, page, prefix):
        """Render one converted document page into an image."""
        return await self.pdf_renderer().render_page(page, prefix)


RENDERERS = {
    "docx": functools.partial(LibreOfficeDocumentRenderer, suffix=".docx"),
    "ods": functools.partial(LibreOfficeDocumentRenderer, suffix=".ods"),
    "odt": functools.partial(LibreOfficeDocumentRenderer, suffix=".odt"),
    "pdf": PdfRenderer,
    "xlsx": functools.partial(LibreOfficeDocumentRenderer, suffix=".xlsx"),
}

MIME_DISPATCH = {
    "application/pdf": "pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ("docx"),
    "application/vnd.oasis.opendocument.spreadsheet": "ods",
    "application/vnd.oasis.opendocument.text": "odt",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "xlsx",
}


def detect_mime(path):
    """Detect file type inside the DisposableVM side."""
    if magic is None:
        raise ValueError("python-magic is required for MIME detection")

    return magic.from_file(str(path), mime=True)


def renderer_name_for_path(path):
    """Return renderer name for a file detected on the server side."""
    mime_type = detect_mime(path)
    try:
        return MIME_DISPATCH[mime_type]
    except KeyError as exc:
        raise ValueError(f"Unsupported file type: {mime_type}") from exc


def create_renderer(name, path, password=b"", resolution=RESOLUTION):
    """Create a renderer for the requested converter type."""
    try:
        renderer_cls = RENDERERS[name]
    except KeyError as exc:
        raise ValueError(f"Unsupported renderer: {name}") from exc

    return renderer_cls(path, password, resolution)


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

    :param prefix: Path prefix for representations
    :param f_suffix: File extension of initial representation (without .)
    :param i_suffix: File extension of final representation (without .)
    """

    def __init__(self, prefix, i_suffix, f_suffix):
        self.page = prefix.name
        self.initial = prefix.with_suffix(f".{i_suffix}")
        self.final = prefix.with_suffix(f".{f_suffix}")
        self.dim = None

    async def convert(self):
        """Convert initial representation to final representation"""
        cmd = [
            "gm",
            "convert",
            str(self.initial),
            "-depth",
            str(DEPTH),
            f"rgb:{self.final}",
        ]

        self.dim = await self._dim()

        proc = await asyncio.create_subprocess_exec(*cmd)
        try:
            await wait_proc(proc, cmd)
        finally:
            await asyncio.get_running_loop().run_in_executor(None, unlink, self.initial)

    async def _dim(self):
        """Identify image dimensions of initial representation"""
        cmd = ["gm", "identify", "-format", "%w %h", str(self.initial)]
        proc = await asyncio.create_subprocess_exec(*cmd, stdout=subprocess.PIPE)

        try:
            output, _ = await proc.communicate()
        except asyncio.CancelledError:
            await terminate_proc(proc)
            raise

        return output.decode("ascii").rstrip()


@dataclass(frozen=True)
class BatchEntry:
    task: asyncio.Task
    rep: Representation


class BaseFile:
    """Unsanitized file"""

    def __init__(self, path, renderer):
        self.path = path
        self.renderer = renderer
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
        return self.renderer.page_count()

    async def _publish(self):
        """Extract initial representations and enqueue conversion tasks"""
        for page in range(1, self.pagenums + 1):
            rep = await self.renderer.render_page(
                page, Path(self.path.parent, str(page))
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
                None, batch_e.rep.final.read_bytes
            )

            await asyncio.get_running_loop().run_in_executor(
                None, unlink, batch_e.rep.final
            )

            await asyncio.get_running_loop().run_in_executor(
                None, send, batch_e.rep.dim
            )
            send_b(rgb_data)

            self.batch.task_done()


parser = argparse.ArgumentParser(
    prog="qubes.PdfConvert",
    description="Server side of qvm-convert-pdf",
    epilog="Refer to qvm-convert-pdf(1) manual for more information",
)

parser.add_argument(
    "resolution",
    nargs="?",
    default=str(RESOLUTION),
    help="Default resolution is 300 ppi",
)

args = parser.parse_args()


def main():
    first_line = sys.stdin.buffer.readline()

    # Password is optional. New clients with a password send
    # "--password=<password>\n" as the first line. Old clients and new
    # clients without a password send the PDF bytes directly, so the
    # first line is part of the PDF data.
    if first_line.startswith(b"--password="):
        password = first_line[len(b"--password=") :].rstrip(b"\n")
        prefix = b""
    else:
        password = b""
        prefix = first_line

    try:
        data = prefix + recv_b()
    except EOFError:
        sys.exit(1)

    with TemporaryDirectory(prefix="qvm-sanitize") as tmpdir:
        pdf_path = Path(tmpdir, "original")
        pdf_path.write_bytes(data)

        try:
            renderer = create_renderer(
                renderer_name_for_path(pdf_path),
                pdf_path,
                password,
                args.resolution,
            )
            base = BaseFile(pdf_path, renderer)
            asyncio.run(base.sanitize())
        except subprocess.CalledProcessError:
            sys.exit(1)
        except LibreOfficeMissingError as exc:
            print(f"error: {exc}", file=sys.stderr, flush=True)
            sys.exit(LIBREOFFICE_MISSING_EXIT_CODE)
        except ValueError as exc:
            print(f"error: {exc}", file=sys.stderr, flush=True)
            sys.exit(1)


if __name__ == "__main__":
    main()
