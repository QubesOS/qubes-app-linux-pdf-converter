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

from collections import namedtuple
import logging
import os
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
    '''Qrexec wrapper for displaying information

    `suffix` is typically only ever used when `msg` needs to overwrite
    the line of the previous message (so as to imitate an updating
    line). This is done by setting `suffix` to '\r'.
    '''
    print(msg, end=suffix, flush=True, file=sys.stderr)

def die(msg):
    '''Qrexec wrapper for displaying error messages'''
    logging.error(msg)
    sys.exit(1)

def send(data):
    '''Qrexec wrapper for sending text data to the client's STDOUT'''
    print(data, flush=True)

def send_b(data):
    '''Qrexec wrapper for sending binary data to the client's STDOUT'''
    sys.stdout.buffer.write(data)
    sys.stdout.buffer.flush()

def recv_b(size=None):
    '''Qrexec wrapper for receiving data from a client'''
    untrusted_data = sys.stdin.buffer.read(size)
    return untrusted_data

def recvline_b():
    '''Qrexec wrapper for receiving a line of data from a client'''
    untrusted_data = sys.stdin.buffer.readline()
    return untrusted_data


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

def recv_pdf(pdf_path):
    filesize = int(recvline_b().decode())
    untrusted_data = recv_b(filesize)

    with open(pdf_path, 'wb') as f:
        f.write(untrusted_data)

def get_page_count(pdf_path):
    untrusted_pages = 0
    output = None
    cmd = ['pdfinfo', pdf_path]

    try:
        output = subprocess.run(cmd, capture_output=True, check=True)
    except subprocess.CalledProcessError:
        info(f'Probably not a PDF...')
    else:
        for line in output.stdout.decode().splitlines():
            if 'Pages:' in line:
                untrusted_pages = int(line.split(':')[1])

    return untrusted_pages

def process_pdf(paths):
    page = 1

    untrusted_pages = get_page_count(paths.pdf)
    send(untrusted_pages)

    while (page <= untrusted_pages):
        pdf_to_png(page, paths.pdf, paths.png)
        send_img_dimensions(paths.png)
        png_to_rgb(page, paths.png, paths.rgb)
        send_rgb_file(paths.rgb)
        page += 1


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
