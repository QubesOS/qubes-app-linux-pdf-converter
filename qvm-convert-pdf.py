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

import argparse
import logging
import os
import sys

PROG_NAME = os.path.basename(sys.argv[0])
QREXEC_CLIENT = '/usr/bin/qrexec-client-vm'


###############################
#         Utilities
###############################

def die(msg):
    '''Qrexec wrapper for displaying error messages'''
    logging.basicConfig(format='%(message)s', stream=sys.stderr)
    logging.error(msg)
    sys.exit(1)


###############################
#          Parsing
###############################

class ArgumentParser(argparse.ArgumentParser):
    '''Overriding class for custom help message.'''
    def print_help(self):
        print(f'''\
usage: {PROG_NAME} [OPTIONS ...] FILE

Options:
   --help      Show this help message and exit.''')
        sys.exit(0)

def parser_new():
    parser = ArgumentParser()

    if len(sys.argv) == 1:
        parser.print_help()

    # parser.add_argument('-v', '--verbose', action='count', default=0)

    return parser.parse_known_args()

def parse_args(args):
    # if args.version:
        # version()
    return

def check_pdf_paths(untrusted_pdfs):
    for untrusted_pdf in untrusted_pdfs:
        if not os.path.exists(untrusted_pdf):
            die(f'{untrusted_pdf}: No such file')


###############################
#           Main
###############################

def main():
    # TODO: Move parsing into qpdf-convert-client
    args, untrusted_pdfs = parser_new()
    parse_args(args)
    check_pdf_paths(untrusted_pdfs)

    # TODO: Handle os.execl() error (maybe with os._exit(127)
    cmd = [QREXEC_CLIENT, 'disp8051', 'qubes.PdfConvert',
           '/usr/lib/qubes/qpdf-convert-client', *untrusted_pdfs]
    os.execvp(QREXEC_CLIENT, cmd)

if __name__ == '__main__':
    # No need to wrap this in a try block since we never return from execl()
    main()