#!/usr/bin/env python3
#
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
#
#

import logging
import os
import sys

PROG_NAME = os.path.basename(sys.argv[0])
QREXEC_CLIENT = '/usr/bin/qrexec-client-vm'

logging.basicConfig(format='%(message)s', stream=sys.stderr)

def die(msg):
    '''Qrexec wrapper for displaying error messages'''
    logging.error(msg)
    sys.exit(1)

def check_pdf_paths(untrusted_paths):
    for untrusted_path in untrusted_paths:
        if not os.path.exists(untrusted_path):
            die(f'{untrusted_path}: No such file')
        elif not os.path.isfile(untrusted_path):
            die(f'{untrusted_path}: Not a regular file')

def main():
    if len(sys.argv) == 1:
        die(f'usage: {PROG_NAME} [FILE ...]')

    untrusted_pdf_paths = [os.path.abspath(path) for path in sys.argv[1:]]
    check_pdf_paths(untrusted_pdf_paths)

    # TODO: Handle os.execl() error (maybe with os._exit(127))
    cmd = [QREXEC_CLIENT, '$dispvm', 'qubes.PdfConvert',
           '/usr/lib/qubes/qpdf-convert-client', *untrusted_pdf_paths]
    os.execvp(QREXEC_CLIENT, cmd)

if __name__ == '__main__':
    # No need to wrap this in a try block since we never return from execvp()
    main()
