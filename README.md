Qubes PDF Converter
====================

Qubes PDF converter is a [Qubes](https://qubes-os.org) Application that
utilizes Disposable VMs and Qubes' flexible qrexec (inter-VM communication)
infrastructure to securely convert potentially untrusted PDF files into
safe-to-view PDF files.

This is done by having a Disposable VM render each page of a PDF file into a
very simple representation (RGB bitmap) that (presumably) leaves no room for
malicious code. This representation is then sent back to the client AppVM which
then constructs an entirely new PDF file out of the received bitmaps.

More discussion of the concept has been described in the original article
[here](http://blog.invisiblethings.org/2013/02/21/converting-untrusted-pdfs-into-trusted.html).

Usage
------

    [user@domU ~]$ qvm-convert-pdf file1.pdf file2.pdf file3.pdf
    :: Sending files to Disposable VMs...

     file1.pdf...done
     file2.pdf...fail
     file3.pdf...done

    Total Sanitized Files: 2/3

Authors
---------

The original idea and implementation has been provided by Joanna Rutkowska. The
project has been subsequently incorporated into [Qubes OS](https://qubes-os.org)
and multiple other developers have contributed various fixes and improvements
(see the commit log for details).
