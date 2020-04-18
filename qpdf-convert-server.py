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


def recv_b(size):
    """Qrexec wrapper for receiving binary data from the client"""
    try:
        untrusted_data = sys.stdin.buffer.read(size)
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
#        Image-related
###############################

def send_img_dimensions(png_path):
    cmd_width = ['identify', '-format', '%w', png_path]
    cmd_height = ['identify', '-format', '%h', png_path]

    try:
        untrusted_width = subprocess.run(cmd_width, capture_output=True,
                                         check=True).stdout.decode()
        untrusted_height = subprocess.run(cmd_height, capture_output=True,
                                         check=True).stdout.decode()
    except subprocess.CalledProcessError:
        die("Failed to gather dimensions... Aborting")

    send(f'{untrusted_width} {untrusted_height}')

def send_rgb_file(rgb_path):
    with open(rgb_path, 'rb') as f:
        data = f.read()
        send_b(data)

def pdf_to_png(pagenum, pdf_path, png_path):
    png_filename = os.path.splitext(png_path)[0]
    cmd = ['pdftocairo', pdf_path, '-png', '-f', str(pagenum), '-l',
           str(pagenum), '-singlefile', png_filename]

    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError:
        cmd = ['convert', pdf_path, f'png:{png_path}']
        try:
            subprocess.run(cmd, check=True)
        except subprocess.CalledProcessError:
            die(f'Page {pagenum} conversion failed (PDF->PNG): {err}')

def png_to_rgb(pagenum, png_path, rgb_path):
    depth = 8
    cmd = ['convert', png_path, '-depth', str(depth), f'rgb:{rgb_path}']

    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError:
        die(f'Page {pagenum} conversion failed (PNG->RGB): {err}')


###############################
#         File-related
###############################

def create_tmp_files():
    '''Create temporary file for storing page images and the untrusted PDF'''
    Files = namedtuple('Files', ['pdf', 'png', 'rgb'])
    suffixes = ('', '.png', '.rgb')
    paths = []

    for suffix in suffixes:
        with NamedTemporaryFile(prefix='qpdf-conversion-', suffix=suffix) as f:
            paths.append(f.name)

    for path in paths:
        with open(path, 'wb') as f:
            f.write(b'')

    return Files(pdf=paths[0], png=paths[1], rgb=paths[2])


###############################
#         PDF-related
###############################


def recv_pdf():
    try:
        filesize = int(recvline())
        data = recv_b(filesize)
    except (ReceiveError, ValueError):
        raise

    return data

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

def main():
    paths = create_tmp_files()

    # FIXME:
    #   When no more PDFs are available to process, the server will exit in
    #   recv() (called in recv_pdf()) with an EOFError. While this works
    #   perfectly fine, it is kinda ugly; successful runs shouldn't exit with an
    #   error, no?
    #
    #   One solution would be to have the client initially send a
    #   space-delimited string containing the sizes of each file. Then, the
    #   server can turn that into an array and use the array's length as the
    #   number of times to loop.
    while True:
        recv_pdf(paths.pdf)
        process_pdf(paths)

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        die("KeyboardInterrupt... Aborting!")
