Qubes PDF Converter
====================

Qubes PDF converter is a [Qubes](https://qubes-os.org) Application, which
utilizes Qubes flexible qrexec (inter-VM communication) infrastructure and
Disposable VMs to perform conversion of potentially untrusted (e.g. maliciously
malformed) PDF files into safe-to-view PDF files.

This is done by having the Disposable VM perform the complex (and potentially
buggy) rendering of the PDF in question and sending the resulting RGB bitmap
(simple representation) to the client AppVM. The client AppVM can _trivially_
verify the received data are indeed the simple representation, and then
construct a new PDF out of the received bitmap. Of course the price we pay for
this conversion is loosing any structural information and text-based search in
the converted PDF.

More discussion and introduction of the concept has been described in the
original article
[here](http://blog.invisiblethings.org/2013/02/21/converting-untrusted-pdfs-into-trusted.html).

Usage
------

    [user@varia ~]$ qvm-convert-pdf test.pdf
    -> Sending file to remote VM...
    -> Waiting for converted samples...
    -> Receving page 8 out of 8...
    -> Converted PDF saved as: ./test.trusted.pdf
    -> Original file saved as /home/user/QubesUntrustedPDFs/test.pdf

Authors
---------

The original idea and implementation has been provided by Joanna Rutkowska. The
project has been subsequently incorporated into [Qubes OS](https://qubes-os.org)
and multiple other developers have contributed various fixes and improvements
(see the commit log for details).
