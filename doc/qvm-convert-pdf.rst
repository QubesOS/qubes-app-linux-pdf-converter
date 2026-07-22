.. program:: qvm-convert-pdf

====================================================
``qvm-convert-pdf`` -- |qvm-convert-pdf-description|
====================================================

SYNOPSIS
========

:program:`qvm-convert-pdf` [FILES ...]

:program:`qvm-convert-pdf` [:option:`--password=PASSWORD`] [FILES ...]

:program:`qvm-convert-pdf` [:option:`--ocr-lang=LANGUAGE`] [FILES ...]

OPTIONS
=======

.. option:: --help, -h

   Show help message and exit

.. option:: --batch={<SIZE>}, -b {<SIZE>}

   Maximum number of conversion tasks. :samp:`{<SIZE>}` should be greater or
   equal to ``1``.

.. option:: --archive={<PATH>}, -a {<PATH>}

   Directory for storing archived files

.. option:: --in-place, -i

   Replace original files instead of archiving them

.. option:: --resolution={<RESOLUTION>}, -r {<RESOLUTION>}

   Output resolution. Default is 300 ppi. :samp:`{<RESOLUTION>}` should be
   greater than ``75`` and lower than ``4800``.

.. option:: --password={<PASSWORD>}, -p {<PASSWORD>}

   Password to use for encrypted PDF files.

.. option:: --ocr-lang={<LANGUAGE>}

   Tesseract language code to use for OCR output. Tesseract uses three-letter
   language codes such as ``eng`` for English, not two-letter locale codes.

DESCRIPTION
===========

:program:`Qubes PDF converter` is a Qubes application that utilizes Qubes'
flexible :doc:`qrexec <developer/services/qrexec>` (inter-VM communication)
infrastructure and :term:`disposables <disposable>` to securely convert
potentially untrusted (e.g. maliciously malformed) PDF files into safe-to-view
PDF files.

For other supported file types, use :doc:`qvm-convert-file`. It currently
handles PDF, DOCX, ODT, XLSX, and ODS inputs, with LibreOffice required only
for the Office document and spreadsheet formats.

This is done by having a disposable render each page of a PDF file into a very
simple representation (RGB bitmap) that (presumably) leaves no room for
malicious code. This representation is then sent back to the client app qube
which then constructs an entirely new PDF file out of the received bitmaps.

Of course, the price we pay for this conversion is an increase in file size and 
the loss of any structural information or text-based search in the converted 
PDF.

If :option:`--ocr-lang` is set, the converter adds a searchable text layer to the
trusted PDF after the pages have been rendered to safe bitmaps. OCR requires
PyMuPDF and Tesseract language data in the client qube.

For English OCR, install ``python3-fitz`` and ``tesseract-ocr-eng`` on Debian
templates, or ``python3-PyMuPDF`` and ``tesseract-langpack-eng`` on Fedora
templates. Other languages use the same Tesseract three-letter language code in
the package name.

LibreOffice is required only for LibreOffice-backed input formats handled by
:program:`qvm-convert-file`. Install the ``libreoffice`` package in the relevant
template to enable those formats.

If :option:`--ocr-lang` is not set, the command uses the OCR setting saved by
``qvm-convert-pdf-ocr-settings``. The graphical file manager action asks for
this setting the first time it is used, and the settings tool can be launched
later from the application menu.

AUTHORS
=======
| Joanna Rutkowska <joanna at invisiblethingslab dot com>
| Marek Marczykowski <marmarek at invisiblethingslab dot com>
