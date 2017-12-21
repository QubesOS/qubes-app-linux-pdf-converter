#
# This is the SPEC file for creating binary and source RPMs for the VMs.
#
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

%{!?version: %define version %(cat version)}

Name:		qubes-pdf-converter-dom0
Version:	%{version}
Release:	1%{dist}
Summary:    Qubes policy for qpdf-converter

Group:		Qubes
Vendor:		Invisible Things Lab
License:	GPL
URL:		http://www.qubes-os.org

BuildRequires: python2-devel
BuildRequires: python3-devel

%define _builddir %(pwd)

%description
Qubes policy for qpdf-converter

%prep
# we operate on the current directory, so no need to unpack anything

%build

%install
rm -rf $RPM_BUILD_ROOT
install -D qubes.PdfConvert.policy $RPM_BUILD_ROOT/etc/qubes-rpc/policy/qubes.PdfConvert
make install-dom0 DESTDIR=$RPM_BUILD_ROOT

%clean
rm -rf $RPM_BUILD_ROOT

%files
%config(noreplace) %attr(0664,root,qubes) /etc/qubes-rpc/policy/qubes.PdfConvert
%dir %{python_sitelib}/qubespdfconverter-*.egg-info
%{python_sitelib}/qubespdfconverter-*.egg-info/*
%{python_sitelib}/qubespdfconverter
%dir %{python3_sitelib}/qubespdfconverter-*.egg-info
%{python3_sitelib}/qubespdfconverter-*.egg-info/*
%{python3_sitelib}/qubespdfconverter
