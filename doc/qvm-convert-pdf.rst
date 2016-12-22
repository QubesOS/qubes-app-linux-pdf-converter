==================
QVM-CONVERT-PDF(1)
==================

NAME
====
qvm-convert-pdf - converts a potentially untrusted pdf to a safe-to-view pdf

SYNOPSIS
========
| qvm-convert-pdf <pdf to convert>

DESCRIPTION
===========

Qubes PDF converter is a Qubes Application, which utilizes Qubes flexible qrexec
(inter-VM communication) infrastructure and Disposable VMs to perform conversion
of potentially untrusted (e.g. maliciously malformed) PDF files into
safe-to-view PDF files.

This is done by having the Disposable VM perform the complex (and potentially
buggy) rendering of the PDF in question) and sending the resulting RGB bitmap
(simple representation) to the client AppVM. The client AppVM can _trivially_
verify the received data are indeed the simple representation, and then
construct a new PDF out of the received bitmap. Of course the price we pay for
this conversion is loosing any structural information and text-based search in
the converted PDF.

AUTHORS
=======
| Joanna Rutkowska <joanna at invisiblethingslab dot com>
| Marek Marczykowski <marmarek at invisiblethingslab dot com>
