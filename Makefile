#
# The Qubes OS Project, https://www.qubes-os.org
#
# Copyright (C) 2013  Joanna Rutkowska <joanna@invisiblethingslab.com>
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.
#
#

PYTHON ?= python3
PANDOC=pandoc -s -f markdown -t man
NAME := convert-pdf

install-vm: build
	install -d $(DESTDIR)/usr/share/man/man1
	install -D qvm-$(NAME).1.gz $(DESTDIR)/usr/share/man/man1/
	$(PYTHON) setup.py install -O1 $(PYTHON_PREFIX_ARG) --root $(DESTDIR)
	install -d $(DESTDIR)/etc/qubes-rpc
	ln -s ../../usr/lib/qubes/qpdf-convert-server $(DESTDIR)/etc/qubes-rpc/qubes.PdfConvert
	install -D qvm-convert-pdf.gnome $(DESTDIR)/usr/lib/qubes/qvm-convert-pdf.gnome
	install -d $(DESTDIR)/usr/share/nautilus-python/extensions
	install -m 0644 qvm_convert_pdf_nautilus.py $(DESTDIR)/usr/share/nautilus-python/extensions
	install -d $(DESTDIR)/usr/share/kde4/services
	install -m 0644 qvm-convert-pdf.desktop $(DESTDIR)/usr/share/kde4/services

install-dom0:
	$(PYTHON) setup.py install -O1 --root $(DESTDIR)
	# not needed in dom0
	rm -f $(DESTDIR)/usr/bin/qvm-convert-pdf
	rm -f $(DESTDIR)/usr/lib/qubes/qpdf-convert-server

qvm-$(NAME).1: README.md
	$(PANDOC) $< > $@

qvm-$(NAME).1.gz: qvm-$(NAME).1
	gzip -f $<

build: qvm-$(NAME).1.gz

clean:
	rm -rf debian/changelog.*
	rm -rf pkgs
	rm -f qvm-$(NAME).1.gz
