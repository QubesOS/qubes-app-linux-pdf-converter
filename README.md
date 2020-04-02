Qubes PDF Converter
====================

Qubes PDF converter is a [Qubes](https://qubes-os.org) Application that
utilizes Qubes' flexible qrexec (inter-VM communication) infrastructure and
Disposable VMs to securely convert potentially untrusted (e.g. maliciously
malformed) PDF files into safe-to-view PDF files.

This is done by having a Disposable VM render each page of a PDF file into a 
very simple representation (RGB bitmap) that (presumably) leaves no room for 
malicious code. This representation is then sent back to the client AppVM which 
then constructs an entirely new PDF file out of the received bitmaps.

Of course, the price we pay for this conversion is an increase in file size and 
the loss of any structural information or text-based search in the converted 
PDF.

More discussion of the concept has been described in the original article
[here](http://blog.invisiblethings.org/2013/02/21/converting-untrusted-pdfs-into-trusted.html).

Usage
------

    [user@varia ~]$ qvm-convert-pdf test.pdf
    Sending file to a Disposable VM...
    Waiting for converted samples...
    Receving page 8/8...
    Converted PDF saved as: /home/user/test.trusted.pdf
    Original file saved as /home/user/QubesUntrustedPDFs/test.pdf

Authors
---------

The original idea and implementation has been provided by Joanna Rutkowska. The
project has been subsequently incorporated into [Qubes OS](https://qubes-os.org)
and multiple other developers have contributed various fixes and improvements
(see the commit log for details).
