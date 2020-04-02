==================
QVM-CONVERT-PDF(1)
==================

NAME
====
qvm-convert-pdf - converts potentially untrusted PDFs to a safe-to-view PDF

SYNOPSIS
========
| qvm-convert-pdf <PDF to convert ...>

DESCRIPTION
===========

Qubes PDF converter is a Qubes Application that utilizes Qubes' flexible qrexec
(inter-VM communication) infrastructure and Disposable VMs to securely convert
potentially untrusted (e.g. maliciously malformed) PDF files into safe-to-view
PDF files.

This is done by having a Disposable VM render each page of a PDF file into a 
very simple representation (RGB bitmap) that (presumably) leaves no room for 
malicious code. This representation is then sent back to the client AppVM which 
then constructs an entirely new PDF file out of the received bitmaps.

Of course, the price we pay for this conversion is an increase in file size and 
the loss of any structural information or text-based search in the converted 
PDF.

AUTHORS
=======
| Joanna Rutkowska <joanna at invisiblethingslab dot com>
| Marek Marczykowski <marmarek at invisiblethingslab dot com>
