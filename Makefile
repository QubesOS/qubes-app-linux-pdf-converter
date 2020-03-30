#
# The Qubes OS Project, http://www.qubes-os.org
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

RPMS_DIR=rpm/
VERSION := $(shell cat version)

help:
	@echo "Qubes addons main Makefile:" ;\
	    echo "make rpms                 <--- make rpms and sign them";\
	    echo; \
	    echo "make clean                <--- clean all the binary files";\
	    echo "make update-repo-current  <-- copy newly generated rpms to qubes yum repo";\
	    echo "make update-repo-current-testing <-- same, but for -current-testing repo";\
	    echo "make update-repo-unstable <-- same, but to -testing repo";\
	    echo "make update-repo-installer -- copy dom0 rpms to installer repo"
	    @exit 0;

rpms: rpms-vm

rpms-dom0:
	rpmbuild --define "_rpmdir rpm/" -bb rpm_spec/qpdf-converter-dom0.spec
	rpm --addsign rpm/x86_64/qubes-pdf-converter-dom0*$(VERSION)*.rpm

rpms-vm:
	rpmbuild --define "_rpmdir rpm/" -bb rpm_spec/qpdf-converter.spec
	rpm --addsign rpm/x86_64/qubes-pdf-converter*$(VERSION)*.rpm

update-repo-current:
	for vmrepo in ../yum/current-release/current/vm/* ; do \
		dist=$$(basename $$vmrepo) ;\
		ln -f $(RPMS_DIR)/x86_64/qubes-pdf-converter*$(VERSION)*$$dist*.rpm $$vmrepo/rpm/ ;\
	done
	ln -f $(RPMS_DIR)/x86_64/qubes-pdf-converter-dom0-*$(VERSION)*.rpm ../yum/current-release/current/dom0/rpm/

update-repo-current-testing:
	for vmrepo in ../yum/current-release/current-testing/vm/* ; do \
		dist=$$(basename $$vmrepo) ;\
		ln -f $(RPMS_DIR)/x86_64/qubes-pdf-converter*$(VERSION)*$$dist*.rpm $$vmrepo/rpm/ ;\
	done
	ln -f $(RPMS_DIR)/x86_64/qubes-pdf-converter-dom0-*$(VERSION)*.rpm ../yum/current-release/current-testing/dom0/rpm/

update-repo-unstable:
	for vmrepo in ../yum/current-release/unstable/vm/* ; do \
		dist=$$(basename $$vmrepo) ;\
		ln -f $(RPMS_DIR)/x86_64/qubes-pdf-converter*$(VERSION)*$$dist*.rpm $$vmrepo/rpm/ ;\
	done
	ln -f $(RPMS_DIR)/x86_64/qubes-pdf-converter-dom0-*$(VERSION)*.rpm ../yum/current-release/unstable/dom0/rpm/

update-repo-template:
	for vmrepo in ../template-builder/yum_repo_qubes/* ; do \
		dist=$$(basename $$vmrepo) ;\
		ln -f $(RPMS_DIR)/x86_64/qubes-pdf-converter*$(VERSION)*$$dist*.rpm $$vmrepo/rpm/ ;\
	done

update-repo-installer:
	ln -f $(RPMS_DIR)/x86_64/qubes-pdf-converter-dom0-*$(VERSION)*.rpm ../installer/yum/qubes-dom0/rpm/

build:
	make manpages -C doc

install-vm:
	make install -C doc
	install -D qvm-convert-pdf.py $(DESTDIR)/usr/bin/qvm-convert-pdf
	install -D qpdf-convert-client.py $(DESTDIR)/usr/lib/qubes/qpdf-convert-client
	install -D qpdf-convert-server.py $(DESTDIR)/usr/lib/qubes/qpdf-convert-server
	install -d $(DESTDIR)/etc/qubes-rpc
	ln -s ../../usr/lib/qubes/qpdf-convert-server $(DESTDIR)/etc/qubes-rpc/qubes.PdfConvert
	install -D qvm-convert-pdf.gnome $(DESTDIR)/usr/lib/qubes/qvm-convert-pdf.gnome
	install -d $(DESTDIR)/usr/share/nautilus-python/extensions
	install -m 0755 qvm_convert_pdf_nautilus.py $(DESTDIR)/usr/share/nautilus-python/extensions
	install -d $(DESTDIR)/usr/share/kde4/services
	install -m 0644 qvm-convert-pdf.desktop $(DESTDIR)/usr/share/kde4/services

install-dom0:
	python2 setup.py install -O1 --root $(DESTDIR)
	python3 setup.py install -O1 --root $(DESTDIR)

clean:
