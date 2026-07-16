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
                             [--ocr-lang LANGUAGE] [FILES ...]

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

.. option:: --ocr-lang=LANGUAGE

   Tesseract language code to use for OCR output. Tesseract uses three-letter
   language codes such as ``eng`` for English, not two-letter locale codes.

DESCRIPTION
===========

Qubes file converter is a Qubes Application that uses Qubes' flexible qrexec
(inter-VM communication) infrastructure and Disposable VMs to convert
potentially untrusted files into safe-to-view PDF files.

Supported input formats:

.. list-table::
   :header-rows: 1

   * - Format
     - Notes
   * - PDF
     - Converted directly with the PDF rendering pipeline.
   * - DOCX, ODT
     - Converted through LibreOffice, then through the PDF rendering pipeline.
   * - XLSX, ODS
     - Converted through LibreOffice, then through the PDF rendering pipeline.

For LibreOffice-backed formats, the converter first creates an intermediate PDF
inside the conversion environment, then uses the same bitmap-based PDF
conversion pipeline.

File type detection is performed on the server side. Unsupported file types are
rejected instead of being converted.

LibreOffice is optional for PDF conversion, but it is required for the supported
office document and spreadsheet formats. If LibreOffice is missing, install it
in the relevant template.

As with qvm-convert-pdf, the converted PDF may be larger than the original file
and may lose structural information such as searchable text.

If ``--ocr-lang`` is set, the converter adds a searchable text layer to the
trusted PDF after the pages have been rendered to safe bitmaps. If
``--ocr-lang`` is not set, the command uses the OCR setting saved by
``qvm-convert-pdf-ocr-settings``.

OCR is optional. For English OCR, install ``python3-fitz`` and
``tesseract-ocr-eng`` on Debian templates, or ``python3-PyMuPDF`` and
``tesseract-langpack-eng`` on Fedora templates.

AUTHORS
========
| Joanna Rutkowska <joanna at invisiblethingslab dot com>
| Marek Marczykowski <marmarek at invisiblethingslab dot com>
