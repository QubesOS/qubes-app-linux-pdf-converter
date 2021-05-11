Qubes PDF Converter
====================

Qubes PDF Converter is a [Qubes OS](https://www.qubes-os.org) application that
uses DisposableVMs and Qubes' flexible qrexec (inter-VM communication)
infrastructure to securely convert untrusted PDF files into safe-to-view PDF
files.

This is done by using a DisposableVM to render each page of a PDF file into a
very simple representation (RGB bitmap) that (presumably) leaves no room for
malicious code. This representation is then sent back to the client qube which
then constructs an entirely new PDF file out of the received bitmaps.

For more details, please see the article in which this concept was originally
introduced:

<http://blog.invisiblethings.org/2013/02/21/converting-untrusted-pdfs-into-trusted.html>

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

Original idea and implementation by Joanna Rutkowska. This application was
subsequently incorporated into [Qubes OS](https://qubes-os.org), and multiple
other developers have contributed various fixes and improvements (see the commit
log for details).
