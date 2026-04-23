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
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301, USA.

import asyncio
import click
import functools
import logging
import os
import shutil
import signal
import subprocess
import sys
import tqdm

from enum import Enum, auto
from dataclasses import dataclass
from pathlib import Path
from PIL import Image
from tempfile import TemporaryDirectory

CLIENT_VM_CMD = ["/usr/bin/qrexec-client-vm", "@dispvm", "qubes.PdfConvert"]

MAX_PAGES = 10000
MAX_IMG_WIDTH = 10000
MAX_IMG_HEIGHT = 10000
DEPTH = 8
RESOLUTION = 300

ERROR_LOGS = asyncio.Queue()


class Status(Enum):
    """Sanitization job status"""
    DONE = auto()
    FAIL = auto()
    CANCELLED = auto()


@dataclass(frozen=True)
class ImageDimensions:
    width: int
    height: int
    size: int
    depth: int = DEPTH


class DimensionError(ValueError):
    """Raised if invalid image dimensions were received"""


class PageError(ValueError):
    """Raised if an invalid number of pages was received"""


class QrexecError(Exception):
    """Raised if a qrexec-related error occured"""


class RepresentationError(Exception):
    """Raised if an representation-related error occurred"""


class BadPath(click.BadParameter):
    """Raised if a Path object parsed by Click is invalid"""
    def __init__(self, path, message):
        super().__init__(message, param_hint=f'"{path}"')


async def sigint_handler(tasks):
    await asyncio.gather(*[cancel_task(t) for t in tasks])


def modify_click_errors(func):
    """Decorator for replacing Click behavior on errors"""

    def show(self, file=None):
        """Removes usage message from UsageError error messages"""
        color = None

        if file is None:
            file = click._compat.get_text_stderr()

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


def expand_dir(path):
    """Expand a directory to a sorted list of non-symlink .pdf files (non-recursive)"""
    try:
        entries = sorted(path.iterdir())
    except PermissionError as e:
        raise BadPath(path, "Not readable") from e

    pdfs = []
    for entry in entries:
        if entry.is_symlink():
            continue
        if entry.is_file() and entry.suffix.lower() == ".pdf":
            pdfs.append(entry)
    return pdfs


def validate_paths(ctx, param, untrusted_paths):
    """Callback for validating file paths parsed by Click"""
    paths = []

    for untrusted_path in untrusted_paths:
        untrusted_resolved = untrusted_path.resolve()

        if not untrusted_resolved.exists():
            raise BadPath(untrusted_path, "No such file or directory")

        if untrusted_resolved.is_dir():
            dir_pdfs = expand_dir(untrusted_resolved)
            if not dir_pdfs:
                click.echo(f"warning: no PDF files found in {untrusted_path}",
                           err=True)
                continue
            paths.extend(dir_pdfs)
            continue

        if not untrusted_resolved.is_file():
            raise BadPath(untrusted_path, "Not a regular file")

        try:
            with untrusted_resolved.open("rb"):
                pass
        except PermissionError as e:
            raise BadPath(untrusted_path, "Not readable") from e

        resolved = untrusted_resolved
        paths.append(resolved)

    return tuple(paths)


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


async def send(proc, data):
    """Qrexec wrapper for sending data to the server"""
    if isinstance(data, (int, str)):
        data = str(data).encode()

    proc.stdin.write(data)
    await proc.stdin.drain()


async def recv_b(proc, size):
    """Qrexec wrapper for receiving binary data from the server"""
    return await proc.stdout.readexactly(size)


async def recvline(proc):
    """Qrexec wrapper for receiving a line of text data from the server"""
    untrusted_data = await proc.stdout.readline()
    if not untrusted_data:
        raise EOFError

    return untrusted_data.decode("ascii").rstrip()


def is_pdf_password_protected(path):
    """Lightweight encrypted-PDF detection based on byte signatures.

    This avoids running full PDF parsers on the client side. It scans only
    small chunks from the beginning and end of the file.
    """
    try:
        with path.open("rb") as f:
            head = f.read(64 * 1024)
            if b"%PDF-" not in head[:1024]:
                return False

            f.seek(0, 2)
            size = f.tell()
            tail_size = min(size, 64 * 1024)
            f.seek(max(0, size - tail_size))
            tail = f.read(tail_size)
    except OSError:
        return False

    # Encrypted PDFs contain an Encrypt dictionary reference in trailer/xref.
    return b"/Encrypt" in head or b"/Encrypt" in tail


def prompt_password_zenity(path):
    """Prompt for password using zenity.

    Returns password as string or None if prompt was canceled/failed.
    """
    cmd = [
        "zenity",
        "--password",
        f"--title=Convert protected PDF: {path.name}",
    ]
    proc = subprocess.run(cmd, capture_output=True, check=False)
    if proc.returncode != 0:
        return None
    return proc.stdout.decode("utf-8", errors="ignore").rstrip("\n")


class Tqdm(tqdm.tqdm):
    def set_status(self, status):
        prefix = self.desc[:self.desc.rfind('.') + 1]
        self.set_description_str(prefix + status)
        self.refresh()


    def set_job_status(self, status):
        self.set_status(status.name.lower())


class Representation:
    """Umbrella object for a file's initial and final representations

    The initial representation must be of a format such that if it contains
    malicious code/data, such code/data is excluded from the final
    representation upon conversion. Generally, this restricts the initial
    representation to a relatively simple format (e.g., RGB bitmap).

    The final representation can be of any format you'd like, provided that
    the initial representation's format was properly selected (e.g., PNG).

    :param prefix: Path prefixes for representations
    :param f_suffix: File extension of initial representation (without .)
    :param i_suffix: File extension of final representation (without .)
    """

    def __init__(self, prefix, i_suffix, f_suffix):
        """
        :param initial: File path to initial representation
        :param final: File path final representation
        :param dim: Image dimensions received from the server
        """
        self.initial = prefix.with_suffix(f".{i_suffix}")
        self.final = prefix.with_suffix(f".{f_suffix}")
        self.dim = None


    async def convert(self, bar):
        """Convert initial representation into final representation

        :param bar: Progress bar to update upon completion
        """
        cmd = [
            "gm",
            "convert",
            "-size",
            f"{self.dim.width}x{self.dim.height}",
            "-depth",
            f"{self.dim.depth}",
            f"rgb:{self.initial}",
            f"png:{self.final}"
        ]

        proc = await asyncio.create_subprocess_exec(*cmd)

        try:
            await wait_proc(proc, cmd)
        except subprocess.CalledProcessError as e:
            raise RepresentationError("Failed to convert representation") from e

        await asyncio.get_running_loop().run_in_executor(
            None,
            self.initial.unlink
        )

        bar.update(1)
        bar.set_status(f"{bar.n}/{bar.total}")


    async def receive(self, proc):
        """Receive initial representation from the server

        :param proc: qrexec-client-vm process
        """
        try:
            self.dim = await self._dim(proc)
        except EOFError as e:
            raise QrexecError("Failed to receive image dimensions") from e
        except (AttributeError, UnicodeError, ValueError) as e:
            raise DimensionError("Invalid image dimensions") from e

        try:
            data = await recv_b(proc, self.dim.size)
        except asyncio.IncompleteReadError as e:
            raise QrexecError("Received inconsistent number of bytes") from e

        await asyncio.get_running_loop().run_in_executor(
            None,
            self.initial.write_bytes,
            data
        )


    @staticmethod
    async def _dim(proc):
        """Receive and compute image dimensions for initial representation

        :param proc: qrexec-client-vm process
        """
        untrusted_w, untrusted_h = map(int, (await recvline(proc)).split(" ", 1))

        if 1 <= untrusted_w <= MAX_IMG_WIDTH and 1 <= untrusted_h <= MAX_IMG_HEIGHT:
            width = untrusted_w
            height = untrusted_h
            size = width * height * 3
        else:
            raise ValueError

        return ImageDimensions(width, height, size)


@dataclass(frozen=True)
class BatchEntry:
    task: asyncio.Task
    rep: Representation


class BaseFile:
    """An unsanitized file

    :param path: Path to original, unsanitized file
    :param pagenums: Number of pages in original file
    :param pdf: Path to temporary final PDf
    """

    output_resolution: int = RESOLUTION

    def __init__(self, path, pagenums, pdf):
        """
        :param path: @path
        :param pagenums: @pagenums
        :param batch: Conversion queue
        """
        self.path = path
        self.pagenums = pagenums
        self.pdf = pdf
        self.batch = None


    async def sanitize(self, proc, bar, depth):
        """Receive and convert representation files

        :param archive: Path to archive directory
        :param depth: Conversion queue size
        :param in_place: Value of --in-place flag
        """
        self.batch = asyncio.Queue(depth)

        publish_task = asyncio.create_task(self._publish(proc, bar))
        consume_task = asyncio.create_task(self._consume())

        try:
            await asyncio.gather(publish_task, consume_task)
        finally:
            if not publish_task.done():
                await cancel_task(publish_task)

            if not consume_task.done():
                await cancel_task(consume_task)

            while not self.batch.empty():
                batch_e = await self.batch.get()
                await cancel_task(batch_e.task)
                self.batch.task_done()


    async def _publish(self, proc, bar):
        """Receive initial representations and start their conversions"""
        pages = []

        for page in range(1, self.pagenums + 1):
            rep = Representation(Path(self.pdf.parent, str(page)), "rgb", "png")
            await rep.receive(proc)

            task = asyncio.create_task(rep.convert(bar))
            batch_e = BatchEntry(task, rep)

            try:
                await self.batch.put(batch_e)
            except asyncio.CancelledError:
                await cancel_task(task)
                raise

            pages.append(page)

            if page % self.batch.maxsize == 0 or page == self.pagenums:
                await self.batch.join()
                await self._save_reps(pages)
                pages = []


    async def _consume(self):
        """Convert initial representations to final form and save as PDF"""
        for _ in range(1, self.pagenums + 1):
            batch_e = await self.batch.get()
            await batch_e.task
            self.batch.task_done()


    async def _save_reps(self, pages):
        """Save final representations to a PDF file"""
        images = []

        for page in pages:
            try:
                image = await asyncio.get_running_loop().run_in_executor(
                    None,
                    Image.open,
                    Path(self.pdf.parent, f"{page}.png")
                )
                images.append(image)
                await asyncio.get_running_loop().run_in_executor(
                    None,
                    image.load
                )
            except IOError as e:
                for image in images:
                    await asyncio.get_running_loop().run_in_executor(
                        None,
                        image.close
                    )
                raise RepresentationError("Failed to open representation") from e

        try:
            await asyncio.get_running_loop().run_in_executor(
                None,
                functools.partial(images[0].save,
                                  self.pdf,
                                  "PDF",
                                  resolution=self.output_resolution,
                                  append=self.pdf.exists(),
                                  append_images=images[1:],
                                  save_all=True)
            )
        except IOError as e:
            raise RepresentationError("Failed to save representation") from e
        finally:
            for image, page in zip(images, pages):
                await asyncio.get_running_loop().run_in_executor(
                    None,
                    image.close
                )
                await asyncio.get_running_loop().run_in_executor(
                    None,
                    Path(self.pdf.parent, f"{page}.png").unlink
                )


class Job:
    """A sanitization job

    :param path: Path to original, unsanitized file
    :param pos: Bar position
    """

    def __init__(self, path, pos, password=""):
        """

        :param file: Base file
        :param bar: Progress bar
        :param proc: qrexec-client-vm process
        :param pdf: Path to temporary PDF for appending representations
        """
        self.path = path
        self.password = password
        self.bar = Tqdm(desc=f"{path}...0/?",
                        bar_format=" {desc}",
                        position=pos)
        self.base = None
        self.proc = None
        self.pdf = None

    async def run(self, archive, depth, in_place):
        self.proc = await asyncio.create_subprocess_exec(
            *CLIENT_VM_CMD,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE
        )

        with TemporaryDirectory(prefix="qvm-sanitize-") as tmpdir:
            try:
                await self._setup(tmpdir)
                await self._start(archive, depth, in_place)
            except (OSError,
                    PageError,
                    QrexecError,
                    DimensionError,
                    RepresentationError,
                    subprocess.CalledProcessError) as e:
                # Since the qrexec-client-vm subprocesses belong to the same
                # process group, when a SIGINT is issued, it's sent to each one.
                # Consequently, there's a race between the signal and our
                # cleanup code. Occasionally, the signal wins and causes some
                # qrexec-client-vm subprocesses to exit, potentially during an
                # operation (e.g., a STDOUT read), thereby raising an exception
                # not expected by the cleanup code.
                if self.proc.returncode == -signal.SIGINT:
                    self.bar.set_job_status(Status.CANCELLED)
                    raise asyncio.CancelledError

                self.bar.set_job_status(Status.FAIL)
                await ERROR_LOGS.put(f"{self.path.name}: {e}")
                if self.proc.returncode is None:
                    await terminate_proc(self.proc)
                raise
            except asyncio.CancelledError:
                self.bar.set_job_status(Status.CANCELLED)
                if self.proc.returncode is None:
                    await terminate_proc(self.proc)
                raise

        self.bar.set_job_status(Status.DONE)


    async def _setup(self, tmpdir):
        send_task = asyncio.create_task(self._send())
        page_task = asyncio.create_task(self._pagenums())

        try:
            _, pagenums = await asyncio.gather(send_task, page_task)
        except QrexecError:
            await cancel_task(page_task)
            raise
        try:
            self.bar.reset(total=pagenums)
        except AttributeError:
            self.bar.total = pagenums
            self.bar.refresh()

        self.pdf = Path(tmpdir, self.path.with_suffix(".trusted.pdf").name)
        self.base = BaseFile(self.path, pagenums, self.pdf)


    async def _start(self, archive, depth, in_place):
        await self.base.sanitize(
            self.proc,
            self.bar,
            depth
        )
        await wait_proc(self.proc, CLIENT_VM_CMD)

        if self.password:
            await self._reencrypt()

        await asyncio.get_running_loop().run_in_executor(
            None,
            shutil.move,
            self.pdf,
            Path(self.path.parent, self.pdf.name)
        )

        if in_place:
            try:
                await asyncio.get_running_loop().run_in_executor(
                    None,
                    self.path.unlink
                )
            except FileNotFoundError:
                pass
        else:
            await asyncio.get_running_loop().run_in_executor(
                None,
                self._archive,
                archive
            )


    async def _reencrypt(self):
        """Re-encrypt the trusted PDF with the original password using qpdf"""
        encrypted = self.pdf.with_suffix(".enc.pdf")
        cmd = [
            "qpdf",
            "--encrypt", self.password, self.password, "256", "--",
            str(self.pdf),
            str(encrypted),
        ]
        proc = await asyncio.create_subprocess_exec(*cmd)
        try:
            await wait_proc(proc, cmd)
        except subprocess.CalledProcessError as e:
            raise RepresentationError("Failed to re-encrypt PDF") from e
        await asyncio.get_running_loop().run_in_executor(
            None, encrypted.replace, self.pdf
        )


    async def _send(self):
        """Send original document to server"""
        data = await asyncio.get_running_loop().run_in_executor(
            None,
            self.path.read_bytes
        )

        try:
            if self.password:
                await send(self.proc, f"--password={self.password}\n")
            await send(self.proc, data)
        except BrokenPipeError as e:
            raise QrexecError("Failed to send PDF") from e
        self.proc.stdin.write_eof()


    async def _pagenums(self):
        """Receive number of pages in original document from server"""
        try:
            untrusted_pagenums = int(await recvline(self.proc))
        except (AttributeError, EOFError, UnicodeError, ValueError) as e:
            raise QrexecError("Failed to receive page count") from e

        if 1 <= untrusted_pagenums <= MAX_PAGES:
            pagenums = untrusted_pagenums
        else:
            raise PageError("Invalid page count")

        return pagenums


    def _archive(self, archive):
        """Move original file into an archival directory"""
        Path.mkdir(archive, exist_ok=True)
        self.path.rename(Path(archive, self.path.name))


async def collect_jobs(params):
    """Build Job list and launch their tasks.

    Resolves per-file passwords (prompting via zenity in GUI mode for
    encrypted PDFs), skips files whose prompt was cancelled, then
    creates and starts one asyncio Task per Job.

    Returns (jobs, tasks, skipped_count).
    """
    passwords = {path: params["password"] for path in params["files"]}
    skipped_files = set()
    gui_mode = os.environ.get("PROGRESS_FOR_GUI") == "yes"
    if gui_mode and not params["password"]:
        for path in params["files"]:
            if is_pdf_password_protected(path):
                password = prompt_password_zenity(path)
                if password is None:
                    await ERROR_LOGS.put(
                        f"{path.name}: Password prompt canceled"
                    )
                    skipped_files.add(path)
                    continue
                passwords[path] = password

    selected_files = [path for path in params["files"] if path not in skipped_files]
    jobs = [Job(f, i, passwords[f]) for i, f in enumerate(selected_files)]
    tasks = [
        asyncio.create_task(job.run(params["archive"],
                                    params["batch"],
                                    params["in_place"]))
        for job in jobs
    ]
    return jobs, tasks, len(skipped_files)


async def run(params):
    CLIENT_VM_CMD[-1] += "+" + str(params["resolution"])
    BaseFile.output_resolution = params["resolution"]
    suffix = "s" if len(params["files"]) > 1 else ""
    print(f"Sending file{suffix} to Disposable VM{suffix}...\n")

    jobs, tasks, num_skipped = await collect_jobs(params)

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(
            sig,
            lambda: asyncio.ensure_future(sigint_handler(tasks))
        )

    results = await asyncio.gather(*tasks, return_exceptions=True)
    completed = results.count(None)

    for job in jobs:
        job.bar.close()

    if ERROR_LOGS.empty():
        if tqdm.__version__ >= "4.34.0":
            newlines = "\n"
        else:
            newlines = "\n" if len(jobs) == 1 else "\n" * (len(jobs) + 1)
    else:
        newlines = "\n"

        if tqdm.__version__ >= "4.34.0":
            print()
        else:
            print() if len(jobs) == 1 else print("\n" * len(jobs))

        while not ERROR_LOGS.empty():
            err_msg = await ERROR_LOGS.get()
            logging.error(err_msg)
            ERROR_LOGS.task_done()

    total = len(results) + num_skipped
    print(f"{newlines}Total Sanitized Files:  {completed}/{total}")

    return completed != total


@click.command()
@click.option(
    "-b",
    "--batch",
    type=click.IntRange(1),
    default=50,
    metavar="SIZE",
    help="Maximum number of conversion tasks"
)
@click.option(
    "-a",
    "--archive",
    type=Path,
    default=Path(Path.home(), "QubesUntrustedPDFs"),
    metavar="PATH",
    help="Directory for storing archived files"
)
@click.option(
    "-i",
    "--in-place",
    is_flag=True,
    help="Replace original files instead of archiving them"
)
@click.option(
    "-r",
    "--resolution",
    type=click.IntRange(75, 4800),
    nargs=1,
    default=RESOLUTION,
    metavar='RESOLUTION',
    help="Resolution of output. default is 300 ppi"
)
@click.option(
    "-p",
    "--password",
    default="",
    metavar="PASSWORD",
    help="Password for encrypted PDF files"
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
    logging.basicConfig(format="error: %(message)s")

    if params["files"]:
        sys.exit(asyncio.run(run(params)))
    else:
        print("No files to sanitize.")


if __name__ == "__main__":
    main()
