% QVM-CONVERT-PDF(1) | User Commands

NAME
===============
qvm-convert-pdf - converts a potentially untrusted file to a safe-to-view pdf

SYNOPSIS
===============
**qvm-convert-pdf** [_OPTION_]... [_FILE_]...

DESCRIPTION
==============
Qubes PDF converter is a [Qubes](https://qubes-os.org) Application, which utilizes Qubes flexible qrexec
(inter-VM communication) infrastructure and Disposable VMs to perform conversion
of potentially untrusted (e.g. maliciously malformed) files into
safe-to-view PDF files.

This is done by having the Disposable VM perform the complex (and potentially
buggy) rendering of the PDF in question) and sending the resulting RGB bitmap
(simple representation) to the client AppVM. The client AppVM can _trivially_
verify the received data are indeed the simple representation, and then
construct a new PDF out of the received bitmap. Of course the price we pay for
this conversion is loosing any structural information and text-based search in
the converted PDF.

More discussion and introduction of the concept has been described in the original article [here](https://blog.invisiblethings.org/2013/02/21/converting-untrusted-pdfs-into-trusted.html).

OPTIONS
=============
**-b** SIZE, **`--`batch**=SIZE
--------------------------------
Maximum number of conversion tasks

**-a** PATH, **`--`archive**=PATH
----------------------------------
Directory for storing archived files

**-i**, **`--`in-place**
-------------------------
Replace original files instead of archiving them

**`--`help**
-------------
Show this message and exit.

CONFIGURATION
===============
To use a custom DisposableVM instead of the default one:

Let’s assume that this custom DisposableVM is called "web".
In dom0, add new line in "/etc/qubes-rpc/policy/qubes.PdfConvert":

**YOUR_CLIENT_VM_NAME @dispvm allow,target=@dispvm:web**

AUTHOR
============
The original idea and implementation has been provided by Joanna Rutkowska. The
project has been subsequently incorporated into [Qubes OS](https://qubes-os.org)
and multiple other developers have contributed various fixes and improvements
(see the commit log for details).
