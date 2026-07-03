===================
QVM-CONVERT-FILE(1)
===================

NAME
====
qvm-convert-file - converts potentially untrusted files to safe-to-view PDFs

SYNOPSIS
========
:command: `qvm-convert-file` [-h] [--batch SIZE] [--archive PATH] [--in-place]
                             [--resolution RESOLUTION] [--password PASSWORD]
                             [FILES ...]

OPTIONS
========

.. option:: --help, -h

   Show help message and exit

.. option:: --batch=SIZE, -b SIZE

   Maximum number of conversion tasks [x>=1]

.. option:: --archive=PATH, -a PATH

   Directory for storing archived files

.. option:: --in-place, -i

   Replace original files instead of archiving them

.. option:: --resolution=RESOLUTION, -r RESOLUTION

   Output resolution. default is 300 ppi [75<=x<=4800]

.. option:: --password=PASSWORD, -p PASSWORD

   Password to use for encrypted PDF files.

DESCRIPTION
===========

Qubes file converter is a Qubes Application that uses Qubes' flexible qrexec
(inter-VM communication) infrastructure and Disposable VMs to convert
potentially untrusted files into safe-to-view PDF files.

The command supports PDF files directly. It also supports DOCX, ODT, XLSX, and
ODS files by converting them to an intermediate PDF with LibreOffice inside the
conversion environment, then using the same bitmap-based PDF conversion
pipeline.

File type detection is performed on the server side. Unsupported file types are
rejected instead of being converted.

LibreOffice is optional for PDF conversion, but it is required for the supported
office document and spreadsheet formats. If LibreOffice is missing, install it
in the relevant template.

As with qvm-convert-pdf, the converted PDF may be larger than the original file
and may lose structural information such as searchable text.

AUTHORS
========
| Joanna Rutkowska <joanna at invisiblethingslab dot com>
| Marek Marczykowski <marmarek at invisiblethingslab dot com>
