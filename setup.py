#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# The Qubes OS Project, https://www.qubes-os.org
#
# Copyright (C) 2016 Marek Marczykowski-Górecki
#                                   <marmarek@invisiblethingslab.com>
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
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301,
# USA.
#

import sys
import os
import setuptools.command.install
from setuptools import setup

if sys.version_info[0:2] < (3, 7):
    # on older python install just tests (dom0 package)
    packages = ['qubespdfconverter.tests']
else:
    packages = ['qubespdfconverter', 'qubespdfconverter.tests']

# create simple scripts that run much faster than "console entry points"
class CustomInstall(setuptools.command.install.install):
    def run(self):
        super().run()
        if 'qubespdfconverter' not in packages:
            return
        scripts = [
            ('usr/lib/qubes/qpdf-convert-server', 'qubespdfconverter.server'),
            ('usr/bin/qvm-convert-pdf', 'qubespdfconverter.client'),
        ]
        for file, pkg in scripts:
            path = os.path.join(self.root, file)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w") as f:
                f.write(
"""#!/usr/bin/python3
from {} import main
import sys
if __name__ == '__main__':
	sys.exit(main())
""".format(pkg))

            os.chmod(path, 0o755)

setup(
    name='qubespdfconverter',
    version=open('version').read().strip(),
    packages=packages,
    install_requires=[
        'Click',
        'Pillow',
        'tqdm'
    ],
    entry_points={
        'qubes.tests.extra.for_template':
            'qubespdfconverter = qubespdfconverter.tests:list_tests',
    },
    cmdclass={
       'install': CustomInstall
    },
)
