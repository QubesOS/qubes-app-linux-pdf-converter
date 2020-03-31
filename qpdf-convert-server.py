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
from tempfile import NamedTemporaryFile

logging.basicConfig(format='%(message)s', stream=sys.stderr)


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

def recv_b():
    '''Qrexec wrapper for receiving binary data from a client'''
    return sys.stdin.buffer.read()


###############################
#        Image-related
###############################

def send_dimensions(png_path):
    '''Send dimensions of untrusted PNG file to client for conversion'''
    cmd1 = ['identify', '-format', '%w', png_path]
    cmd2 = ['identify', '-format', '%h', png_path]

    try:
        width = subprocess.run(cmd1, capture_output=True,
                               check=True).stdout.decode()
        height = subprocess.run(cmd2, capture_output=True,
                                check=True).stdout.decode()
    except subprocess.CalledProcessError:
        die("Failed to gather dimensions... Aborting")

    send(f'{width} {height}')

def send_rgb_file(rgb_path):
    '''Send presumably clean RGB file to client'''
    with open(rgb_path, 'rb') as f:
        data = f.read()
        send_b(data)

def pdf_to_png(page, pdf_path, png_path):
    '''Convert an untrusted PDF page into an intermediate PNG file'''
    png_filename = os.path.splitext(png_path)[0]
    cmd = ['pdftocairo', pdf_path, '-png', '-f', str(page), '-l', str(page),
           '-singlefile', png_filename]

    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError:
        cmd = ['convert', pdf_path, f'png:{png_path}']
        try:
            subprocess.run(cmd, check=True)
        except subprocess.CalledProcessError:
            die(f'Page {page} conversion failed (PDF->PNG): {err}')

def png_to_rgb(png_path, rgb_path):
    '''Convert PNG file into a presumably clean RGB file'''
    depth = 8
    cmd = ['convert', png_path, '-depth', str(depth), f'rgb:{rgb_path}']

    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError:
        die(f'Page {page} conversion failed (PNG->RGB): {err}')


###############################
#         File-related
###############################

def get_tmp_files():
    '''Return random temporary file names for images and the untrusted PDF'''
    Files = namedtuple('Files', ['pdf', 'png', 'rgb'])
    suffixes = ('', '.png', '.rgb')
    paths = []

    for suffix in suffixes:
        with NamedTemporaryFile(prefix='qpdf-conversion-', suffix=suffix) as f:
            paths.append(f.name)

    return Files(pdf=paths[0], png=paths[1], rgb=paths[2])

def make_tmp_files(paths):
    '''Create temporary files to store images and the untrusted PDF'''
    for path in paths:
        with open(path, 'wb') as f:
            f.write(b'')


###############################
#         PDF-related
###############################

def recv_pdf(pdf_path):
    '''Receive untrusted PDF file from client'''
    with open(pdf_path, 'wb') as f:
        data = recv_b()
        f.write(data)

def get_page_count(pdf_path):
    '''Get number of pages in the untrusted PDF file'''
    pages = 0
    output = None
    cmd = ['pdfinfo', pdf_path]

    try:
        output = subprocess.run(cmd, capture_output=True, check=True)
    except subprocess.CalledProcessError:
        info(f'Probably not a PDF...')
    else:
        for line in output.stdout.decode().splitlines():
            if 'Pages:' in line:
                pages = int(line.split(':')[1])

    return pages

def process_pdf(paths):
    '''Process pages of the untrusted PDF file'''
    page = 1

    pages = get_page_count(paths.pdf)
    send(pages)

    while (page <= pages):
        pdf_to_png(page, paths.pdf, paths.png)
        send_dimensions(paths.png)
        png_to_rgb(paths.png, paths.rgb)
        send_rgb_file(paths.rgb)
        page += 1


###############################
#            Main
###############################

def main():
    paths = get_tmp_files()
    make_tmp_files(paths)
    recv_pdf(paths.pdf)
    process_pdf(paths)

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        die("KeyboardInterrupt... Aborting!")
