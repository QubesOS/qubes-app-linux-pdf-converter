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
from PIL import Image
import subprocess
import sys
from tempfile import NamedTemporaryFile

PROG_NAME = os.path.basename(sys.argv[0])
ARCHIVE_PATH = f"{os.path.expanduser('~')}/QubesUntrustedPDFs"

MAX_PAGES = 10000
MAX_IMG_WIDTH = 10000
MAX_IMG_HEIGHT = 10000
MAX_IMG_SIZE = MAX_IMG_WIDTH * MAX_IMG_HEIGHT * 3

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

def recv():
    '''Qrexec wrapper for receiving text data from a client'''
    return input()

def recv_b():
    '''Qrexec wrapper for receiving binary data from a client'''
    return sys.stdin.buffer.read()

def check_range(val, upper):
    '''Raises a ValueError if the value isn't between 1 and some upper bound'''
    if (not 1 <= val <= upper) or (not 1 <= val <= upper):
        raise ValueError


###############################
#        Image-related
###############################

def recv_measurements():
    '''Receive image measurements for a PDF page from server'''
    return (int(val) for val in recv().split(' ', 2))

def get_size(width, height):
    '''Compute image size based on the received measurements'''
    size = width * height * 3

    if size > MAX_IMG_SIZE:
        die("Calculated image size is too large... aborting!")

    return size

def get_dimensions():
    '''Compute image dimensions based on received measurements'''
    depth = 8

    try:
        width, height = recv_measurements()
        check_range(width, MAX_IMG_WIDTH)
        check_range(height, MAX_IMG_HEIGHT)
    except ValueError:
        die("Invalid image geometry returned... aborting!")

    size = get_size(width, height)
    Dimensions = namedtuple('Dimensions', ['width', 'height', 'depth', 'size'])

    return Dimensions(width=width, height=height, size=size, depth=depth)

def recv_rgb(rgb_path, size):
    '''Receive a presumably clean RGB file of a PDF page from server'''
    # XXX: For some reason, this leaves us missing alot of bytes
    # rcvd_bytes = input().encode('utf-8', 'surrogateescape')
    # rcvd_bytes = rcvd_bytes[:dimensions.size]

    # XXX: Example of using PIL for performant PNG -> JPG. Maybe use this?
    # png = Image.open(object.logo.path)
    # png.load() # required for png.split()
    # background = Image.new("RGB", png.size, (255, 255, 255))
    # background.paste(png, mask=png.split()[3]) # 3 is the alpha channel
    # background.save('foo.jpg', 'JPEG', quality=80)

    with open(rgb_path, 'wb') as rgb_f:
        # FIXME: Why can't we get this in pure Python????? This isn't
        # Windows-compatible
        cmd = ['head', '-c', str(size)]
        subprocess.run(cmd, stdout=rgb_f, check=True)

        if os.path.getsize(rgb_f.name) != size:
            os.remove(rgb_path)
            die('Invalid number of bytes in RGB file... aborting!')

def rgb_to_png(rgb_path, png_path, dimensions, page):
    '''Convert an RGB file to a PNG file'''
    cmd = ['convert', '-size', f'{dimensions.width}x{dimensions.height}',
           '-depth', str(dimensions.depth), f'rgb:{rgb_path}',
           f'png:{png_path}']

    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError:
        die(f'Page {page} conversion failed (RGB->PNG)... aborting!')
    else:
        os.remove(rgb_path)

def convert_rgb(dimensions, page):
    '''Driver for receiving and converting RGB files'''
    with NamedTemporaryFile(prefix='qpdf-conversion-') as rcvd_f:
        rgb_path = f'{rcvd_f.name}-{page}.rgb'
        png_path = f'{rcvd_f.name}-{page}.png'
        recv_rgb(rgb_path, dimensions.size)
        rgb_to_png(rgb_path, png_path, dimensions, page)

    return png_path


###############################
#         PDF-related
###############################

def recv_page_count():
    '''Receive number of pages in PDF file from server'''
    try:
        page_count = int(recv())
        check_range(page_count, MAX_PAGES)
    except ValueError:
        die("Invalid number of pages returned... aborting!")

    return page_count

def send_pdf_file(untrusted_pdf):
    '''Send untrusted PDF file to server'''
    info('Sending file to a Disposable VM...')
    with open(untrusted_pdf, 'rb') as f:
        send_b(f.read())
    os.close(sys.stdout.fileno())

def archive_pdf(untrusted_pdf):
    '''Move original untrusted PDF to an archive'''
    archived_pdf = f'{ARCHIVE_PATH}/{os.path.basename(untrusted_pdf)}'
    os.rename(untrusted_pdf, archived_pdf)
    info(f'Original PDF saved as: {archived_pdf}')

def process_pdf_file(untrusted_pdf, page_count):
    '''Process an untrusted PDF page and save the trusted result'''
    page = 1
    images = []
    trusted_pdf = f'{os.path.splitext(untrusted_pdf)[0]}.trusted.pdf'

    info("Waiting for converted sample...")

    while page <= page_count:
        dimensions = get_dimensions()

        info(f'Receiving page {page}/{page_count}...', '\r')

        # TODO: There's some weird verbose condition here in the og script
        png_path = convert_rgb(dimensions, page)
        images.append(Image.open(png_path))

        page += 1
    else:
        info('')

    # TODO: Maybe it'd be better to save->delete png over and over again to
    # avoid storing all PNGs in memory
    images[0].save(trusted_pdf, 'PDF', resolution=100.0, save_all=True,
                   append_images=images[1:])

    for img in images:
        img.close()
        os.remove(img.filename)

    info(f'Converted PDF saved as: {trusted_pdf}')

def process_pdfs(untrusted_pdfs):
    '''Wrapper for PDF processing'''
    # TODO: Remove [0] when support for multiple PDFs is available
    # for untrusted_pdf in untrusted_pdfs:
    send_pdf_file(untrusted_pdfs[0])
    page_count = recv_page_count()
    process_pdf_file(untrusted_pdfs[0], page_count)
    archive_pdf(untrusted_pdfs[0])


###############################
#           Main
###############################

def main():
    untrusted_pdfs = sys.argv[1:]

    if not os.path.exists(ARCHIVE_PATH):
        os.mkdir(ARCHIVE_PATH)

    process_pdfs(untrusted_pdfs)

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        die("KeyboardInterrupt... aborting!")