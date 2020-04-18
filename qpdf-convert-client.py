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

PROG_NAME = os.path.basename(sys.argv[0])
ARCHIVE_PATH = f"{os.path.expanduser('~')}/QubesUntrustedPDFs"

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
    except asyncio.IncompleteReadError:
        logging.error("server may have died...")
        raise

    if not untrusted_data:
        raise EOFError

    return untrusted_data


# TODO (?): Size limit for readline()
async def recvline_b(proc):
    """Qrexec wrapper for receiving a line of binary data from the server"""
    untrusted_data = await proc.stdout.readline()

    if not untrusted_data:
        raise EOFError

    return untrusted_data


async def recv(proc, size):
    """Convenience wrapper for receiving text data from the server"""
    try:
        untrusted_data = (await recv_b(proc, size)).decode()
    except EOFError:
        raise
    except (AttributeError, UnicodeError):
        logging.error("failed to decode received data!")
        raise

    return untrusted_data


async def recvline(proc):
    """Convenience wrapper for receiving a line of text data from the server"""
    try:
        untrusted_data = (await recvline_b(proc)).decode("ascii").rstrip()
    except EOFError:
        raise
    except (AttributeError, UnicodeError):
        logging.error("failed to decode received data!")
        raise

    return untrusted_data


async def send(proc, data):
    """Qrexec wrapper for sending data to the server"""
    if isinstance(data, (str, int)):
        data = str(data).encode()

    proc.stdin.write(data + b"\n")
    try:
        await proc.stdin.drain()
    except BrokenPipeError:
        # logging.error("server may have died")
        raise



###############################
#        Image-related
###############################


async def get_img_dim(proc):
    try:
        untrusted_w, untrusted_h = map(int, (await recvline(proc)).split(" ", 1))
    except (AttributeError, EOFError, UnicodeError) as e:
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

def recv_page_count():
    try:
        untrusted_page_count = int(recvline_b().decode())
        check_range(untrusted_page_count, MAX_PAGES)
    except ValueError:
        die("Invalid number of pages returned... aborting!")

    return untrusted_page_count

def send_pdf(untrusted_pdf_path):
    info(f'Sending {untrusted_pdf_path} to a Disposable VM...')

    # To process multiple files, we have to avoid closing STDIN since we can't
    # reopen it afterwards without duplicating it to some new fd which doesn't
    # seem ideal. Unfortunately, unless STDIN is being read from a terminal, I
    # couldn't find a way to indicate to the server that we were done sending
    # stuff.
    #
    # So, the current solution is to send file's size in advance so that the
    # server can know when to stop reading from STDIN. The problem then becomes
    # that the server may start its read after we send the PDF file.  Thus, we
    # make the client sleep so that the server can start its read beforehand.
    send(os.path.getsize(untrusted_pdf_path))
    time.sleep(0.1)

    with open(untrusted_pdf_path, 'rb') as f:
        send_b(f.read())

def archive_pdf(untrusted_pdf_path):
    archived_pdf_path = f'{ARCHIVE_PATH}/{os.path.basename(untrusted_pdf_path)}'
    os.rename(untrusted_pdf_path, archived_pdf_path)
    info(f'Original PDF saved as: {archived_pdf_path}')

def process_pdf(untrusted_pdf_path, untrusted_page_count):
    page = 1
    images = []
    pdf_path = f'{os.path.splitext(untrusted_pdf_path)[0]}.trusted.pdf'

    info("Waiting for converted sample...")

    while page <= untrusted_page_count:
        info(f'Receiving page {page}/{untrusted_page_count}...', '\r')
        untrusted_dimensions = get_img_dimensions()
        png_path = convert_rgb_file(untrusted_dimensions, page)
        images.append(Image.open(png_path))
        page += 1
    else:
        info('')

    # TODO (?): Save->delete PNGs in a loop to avoid storing all PNGs in memory.
    images[0].save(pdf_path, 'PDF', resolution=100.0, save_all=True,
                   append_images=images[1:])

    for img in images:
        img.close()
        os.remove(img.filename)

    info(f'Converted PDF saved as: {pdf_path}')

def process_pdfs(untrusted_pdf_paths):
    # TODO (?): Add check for duplicate filenames
    for untrusted_pdf_path in untrusted_pdf_paths:
        send_pdf(untrusted_pdf_path)
        untrusted_page_count = recv_page_count()
        process_pdf(untrusted_pdf_path, untrusted_page_count)
        archive_pdf(untrusted_pdf_path)

        if untrusted_pdf_path != untrusted_pdf_paths[-1]:
            info('')


###############################
#           Main
###############################

def main():
    untrusted_pdf_paths = sys.argv[1:]
    mkdir_archive()
    process_pdfs(untrusted_pdf_paths)

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        die("KeyboardInterrupt... Aborting!")
