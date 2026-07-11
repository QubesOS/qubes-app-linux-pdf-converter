# vim: fileencoding=utf-8

#
# The Qubes OS Project, https://www.qubes-os.org/
#
# Copyright (C) 2016
#                   Marek Marczykowski-Górecki <marmarek@invisiblethingslab.com>
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program; if not, write to the Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.
#
import asyncio
import os
import unittest

import itertools
import qubes.tests.extra


# noinspection PyPep8Naming
class TC_00_PDFConverter(qubes.tests.extra.ExtraTestCase):
    circle_svg = """<?xml version="1.0" encoding="UTF-8" standalone="no"?>
<!DOCTYPE svg PUBLIC "-//W3C//DTD SVG 1.0//EN" "http://www.w3.org/TR/2001/PR-SVG-20010719/DTD/svg10.dtd">
<svg width="9cm" height="11cm" viewBox="33 27 179 210" xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink">
  <g>
    <ellipse style="fill: #ffffff" cx="133" cy="107" rx="78.0001" ry="78.0001"/>
    <ellipse style="fill: none; fill-opacity:0; stroke-width: 2; stroke: #000000" cx="133" cy="107" rx="78.0001" ry="78.0001"/>
  </g>
  <text font-size="12" style="fill: #000000;text-anchor:start;font-family:sans-serif;font-style:normal;font-weight:normal" x="34" y="234">
    <tspan x="34" y="234">{text}</tspan>
  </text>
</svg>
    """

    def setUp(self):
        if 'whonix' in self.template:
            self.skipTest('whonix do not have pdf converter installed')
        super(TC_00_PDFConverter, self).setUp()
        # noinspection PyAttributeOutsideInit
        self.vm = self.create_vms(["vm"])[0]
        self.vm.start()

    def create_pdf(self, filename, content):
        '''Create PDF file with given (textual) content

        :param filename: output filename
        :param content: content to be placed on each page (list of str)
        '''
        for (page_content, page_no) in zip(content, itertools.count()):
            p = self.vm.run(
                'cat > /tmp/page{no:04}.svg && '
                'gm convert /tmp/page{no:04}.svg /tmp/page{no:04}.pdf 2>&1'.format(
                    no=page_no), passio_popen=True)
            (stdout, _) = p.communicate(self.circle_svg.format(
                text=page_content).encode())
            if p.returncode != 0:
                self.skipTest('failed to create test page: {}'.format(stdout))

        p = self.vm.run('pdfunite /tmp/page*.pdf "{}" 2>&1'.format(filename),
            passio_popen=True)
        (stdout, _) = p.communicate()
        if p.returncode != 0:
            self.skipTest('failed to create test pdf: {}'.format(stdout))

    def create_docx(self, filename, text):
        '''Create DOCX file with given (textual) content

        :param filename: output filename
        :param text: text to be placed in the document
        '''
        script = r'''
import sys
import zipfile

filename = sys.argv[1]
text = sys.argv[2]

content_types = ''' + repr("""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>
""") + r'''
rels = ''' + repr("""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>
""") + r'''
document = f''' + repr("""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
    <w:p><w:r><w:t>{text}</w:t></w:r></w:p>
    <w:sectPr/>
  </w:body>
</w:document>
""") + r'''.format(text=text)

with zipfile.ZipFile(filename, "w") as docx:
    docx.writestr("[Content_Types].xml", content_types)
    docx.writestr("_rels/.rels", rels)
    docx.writestr("word/document.xml", document)
'''
        p = self.vm.run(
            'python3 - "{}" "{}"'.format(filename, text),
            passio_popen=True)
        (stdout, _) = p.communicate(script.encode())
        if p.returncode != 0:
            self.skipTest('failed to create test docx: {}'.format(stdout))

    def create_odt(self, filename, text):
        '''Create ODT file with given (textual) content

        :param filename: output filename
        :param text: text to be placed in the document
        '''
        script = r'''
import sys
import zipfile

filename = sys.argv[1]
text = sys.argv[2]

manifest = ''' + repr("""<?xml version="1.0" encoding="UTF-8"?>
<manifest:manifest
  xmlns:manifest="urn:oasis:names:tc:opendocument:xmlns:manifest:1.0"
  manifest:version="1.2">
  <manifest:file-entry manifest:media-type="application/vnd.oasis.opendocument.text" manifest:full-path="/"/>
  <manifest:file-entry manifest:media-type="text/xml" manifest:full-path="content.xml"/>
</manifest:manifest>
""") + r'''
content = f''' + repr("""<?xml version="1.0" encoding="UTF-8"?>
<office:document-content
  xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0"
  xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0"
  office:version="1.2">
  <office:body>
    <office:text>
      <text:p>{text}</text:p>
    </office:text>
  </office:body>
</office:document-content>
""") + r'''.format(text=text)

with zipfile.ZipFile(filename, "w") as odt:
    odt.writestr("mimetype", "application/vnd.oasis.opendocument.text")
    odt.writestr("META-INF/manifest.xml", manifest)
    odt.writestr("content.xml", content)
'''
        p = self.vm.run(
            'python3 - "{}" "{}"'.format(filename, text),
            passio_popen=True)
        (stdout, _) = p.communicate(script.encode())
        if p.returncode != 0:
            self.skipTest('failed to create test odt: {}'.format(stdout))

    def create_xlsx(self, filename, text):
        '''Create XLSX file with given (textual) content

        :param filename: output filename
        :param text: text to be placed in the spreadsheet
        '''
        script = r'''
import sys
import zipfile

filename = sys.argv[1]
text = sys.argv[2]

content_types = ''' + repr("""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
  <Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
</Types>
""") + r'''
rels = ''' + repr("""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>
""") + r'''
workbook_rels = ''' + repr("""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
</Relationships>
""") + r'''
workbook = ''' + repr("""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
  xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheets>
    <sheet name="Sheet1" sheetId="1" r:id="rId1"/>
  </sheets>
</workbook>
""") + r'''
sheet = f''' + repr("""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <sheetData>
    <row r="1">
      <c r="A1" t="inlineStr"><is><t>{text}</t></is></c>
    </row>
  </sheetData>
</worksheet>
""") + r'''.format(text=text)

with zipfile.ZipFile(filename, "w") as xlsx:
    xlsx.writestr("[Content_Types].xml", content_types)
    xlsx.writestr("_rels/.rels", rels)
    xlsx.writestr("xl/_rels/workbook.xml.rels", workbook_rels)
    xlsx.writestr("xl/workbook.xml", workbook)
    xlsx.writestr("xl/worksheets/sheet1.xml", sheet)
'''
        p = self.vm.run(
            'python3 - "{}" "{}"'.format(filename, text),
            passio_popen=True)
        (stdout, _) = p.communicate(script.encode())
        if p.returncode != 0:
            self.skipTest('failed to create test xlsx: {}'.format(stdout))

    def create_ods(self, filename, text):
        '''Create ODS file with given (textual) content

        :param filename: output filename
        :param text: text to be placed in the spreadsheet
        '''
        script = r'''
import sys
import zipfile

filename = sys.argv[1]
text = sys.argv[2]

manifest = ''' + repr("""<?xml version="1.0" encoding="UTF-8"?>
<manifest:manifest
  xmlns:manifest="urn:oasis:names:tc:opendocument:xmlns:manifest:1.0"
  manifest:version="1.2">
  <manifest:file-entry manifest:media-type="application/vnd.oasis.opendocument.spreadsheet" manifest:full-path="/"/>
  <manifest:file-entry manifest:media-type="text/xml" manifest:full-path="content.xml"/>
</manifest:manifest>
""") + r'''
content = f''' + repr("""<?xml version="1.0" encoding="UTF-8"?>
<office:document-content
  xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0"
  xmlns:table="urn:oasis:names:tc:opendocument:xmlns:table:1.0"
  xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0"
  office:version="1.2">
  <office:body>
    <office:spreadsheet>
      <table:table table:name="Sheet1">
        <table:table-row>
          <table:table-cell office:value-type="string">
            <text:p>{text}</text:p>
          </table:table-cell>
        </table:table-row>
      </table:table>
    </office:spreadsheet>
  </office:body>
</office:document-content>
""") + r'''.format(text=text)

with zipfile.ZipFile(filename, "w") as ods:
    ods.writestr("mimetype", "application/vnd.oasis.opendocument.spreadsheet")
    ods.writestr("META-INF/manifest.xml", manifest)
    ods.writestr("content.xml", content)
'''
        p = self.vm.run(
            'python3 - "{}" "{}"'.format(filename, text),
            passio_popen=True)
        (stdout, _) = p.communicate(script.encode())
        if p.returncode != 0:
            self.skipTest('failed to create test ods: {}'.format(stdout))

    def get_pdfinfo(self, filename):
        p = self.vm.run('pdfinfo "{}"'.format(filename), passio_popen=True)
        (stdout, _) = p.communicate()
        self.assertEqual(p.returncode, 0,
            "Failed to get pdfinfo of {}".format(filename))
        pdfinfo = {}
        for line in stdout.decode().splitlines():
            k, v = str(line).split(':', 1)
            pdfinfo[k] = v.strip()
        return pdfinfo

    def assertCorrectlyTransformed(self, orig_filename, trusted_filename):
        self.assertEqual(
            self.vm.run('test -r "{}"'.format(trusted_filename), wait=True), 0)
        # TODO: somehow verify content of generated file, for now perform
        # some heuristics
        orig_info = self.get_pdfinfo(orig_filename)
        trusted_info = self.get_pdfinfo(trusted_filename)
        # 1. check number of pages
        self.assertEqual(trusted_info['Pages'], orig_info['Pages'])

        untrusted_backup = 'QubesUntrustedPDFs/{}'.format(os.path.basename(
            trusted_filename.replace('.trusted', '')))
        self.assertEqual(
            self.vm.run('test -r "{}"'.format(untrusted_backup), wait=True), 0)
        self.assertEqual(self.vm.run(
            'diff "{}" "{}"'.format(orig_filename, untrusted_backup), wait=True), 0)

    def test_000_one_page(self):
        self.create_pdf('test.pdf', ['This is test'])
        p = self.vm.run('cp test.pdf orig.pdf; qvm-convert-pdf test.pdf 2>&1',
            passio_popen=True)
        (stdout, _) = p.communicate()
        self.assertEqual(p.returncode, 0, 'qvm-convert-pdf failed: {}'.format(stdout))
        self.assertCorrectlyTransformed('orig.pdf', 'test.trusted.pdf')

    def test_001_two_pages(self):
        self.create_pdf('test.pdf', ['This is test', 'Second page'])
        p = self.vm.run('cp test.pdf orig.pdf; qvm-convert-pdf test.pdf 2>&1',
            passio_popen=True)
        (stdout, _) = p.communicate()
        self.assertEqual(p.returncode, 0, 'qvm-convert-pdf failed: {}'.format(stdout))
        self.assertCorrectlyTransformed('orig.pdf', 'test.trusted.pdf')

    def test_002_500_pages(self):
        self.create_pdf('test.pdf', ['This is test'] * 500)
        p = self.vm.run('cp test.pdf orig.pdf; qvm-convert-pdf test.pdf 2>&1',
            passio_popen=True)
        (stdout, _) = p.communicate()
        self.assertEqual(p.returncode, 0, 'qvm-convert-pdf failed: {}'.format(stdout))
        self.assertCorrectlyTransformed('orig.pdf', 'test.trusted.pdf')

    def test_003_filename_with_spaces(self):
        self.create_pdf('test with spaces.pdf', ['This is test'])
        p = self.vm.run(
            'cp "test with spaces.pdf" orig.pdf; '
            'qvm-convert-pdf "test with spaces.pdf" 2>&1',
            passio_popen=True)
        (stdout, _) = p.communicate()
        self.assertEqual(p.returncode, 0, 'qvm-convert-pdf failed: {}'.format(stdout))
        self.assertCorrectlyTransformed('orig.pdf',
            'test with spaces.trusted.pdf')

    def test_004_cancel_stops_conversion(self):
        self.create_pdf('test.pdf', ['This is test'] * 500)
        domains_before = set(self.app.domains)
        p = self.vm.run(
            'cp test.pdf orig.pdf; '
            'timeout --signal=INT 20 qvm-convert-pdf test.pdf 2>&1',
            passio_popen=True)
        (stdout, _) = p.communicate()
        self.assertNotEqual(p.returncode, 0,
            'Expected non-zero exit from interrupted conversion: {}'.format(stdout))
        self.assertNotEqual(
            self.vm.run('test -r test.trusted.pdf', wait=True), 0,
            'trusted pdf should not exist after cancel')
        # DispVM cleanup is asynchronous; poll until it disappears from the
        # collection. The timeout must be shorter than the conversion time, to
        # be sure it was canceled.
        timeout = 20
        orig_timeout = timeout
        while True:
            domains_after = set(self.app.domains)
            if domains_after == domains_before:
                break
            self.loop.run_until_complete(asyncio.sleep(1))
            timeout -= 1
            if timeout <= 0:
                rest = [domain.name for domain in domains_after - domains_before]
                self.fail(
                    'DispVM not cleaned up {}s after cancel: {}'.format(
                        orig_timeout, rest))

    def test_005_docx(self):
        if self.vm.run('command -v libreoffice >/dev/null', wait=True) != 0:
            self.skipTest('libreoffice not installed')
        self.create_docx('test.docx', 'This is test')
        p = self.vm.run(
            'cp test.docx orig.docx; qvm-convert-file test.docx 2>&1',
            passio_popen=True)
        (stdout, _) = p.communicate()
        self.assertEqual(
            p.returncode, 0, 'qvm-convert-file failed: {}'.format(stdout))
        self.assertEqual(
            self.vm.run('test -r "test.trusted.pdf"', wait=True), 0)
        trusted_info = self.get_pdfinfo('test.trusted.pdf')
        self.assertGreaterEqual(int(trusted_info['Pages']), 1)

        self.assertEqual(
            self.vm.run('test -r "QubesUntrustedPDFs/test.docx"', wait=True), 0)
        self.assertEqual(self.vm.run(
            'diff "orig.docx" "QubesUntrustedPDFs/test.docx"', wait=True), 0)

    def test_006_odt(self):
        if self.vm.run('command -v libreoffice >/dev/null', wait=True) != 0:
            self.skipTest('libreoffice not installed')
        self.create_odt('test.odt', 'This is test')
        p = self.vm.run(
            'cp test.odt orig.odt; qvm-convert-file test.odt 2>&1',
            passio_popen=True)
        (stdout, _) = p.communicate()
        self.assertEqual(
            p.returncode, 0, 'qvm-convert-file failed: {}'.format(stdout))
        self.assertEqual(
            self.vm.run('test -r "test.trusted.pdf"', wait=True), 0)
        trusted_info = self.get_pdfinfo('test.trusted.pdf')
        self.assertGreaterEqual(int(trusted_info['Pages']), 1)

        self.assertEqual(
            self.vm.run('test -r "QubesUntrustedPDFs/test.odt"', wait=True), 0)
        self.assertEqual(self.vm.run(
            'diff "orig.odt" "QubesUntrustedPDFs/test.odt"', wait=True), 0)

    def test_007_xlsx(self):
        if self.vm.run('command -v libreoffice >/dev/null', wait=True) != 0:
            self.skipTest('libreoffice not installed')
        self.create_xlsx('test.xlsx', 'This is test')
        p = self.vm.run(
            'cp test.xlsx orig.xlsx; qvm-convert-file test.xlsx 2>&1',
            passio_popen=True)
        (stdout, _) = p.communicate()
        self.assertEqual(
            p.returncode, 0, 'qvm-convert-file failed: {}'.format(stdout))
        self.assertEqual(
            self.vm.run('test -r "test.trusted.pdf"', wait=True), 0)
        trusted_info = self.get_pdfinfo('test.trusted.pdf')
        self.assertGreaterEqual(int(trusted_info['Pages']), 1)

        self.assertEqual(
            self.vm.run('test -r "QubesUntrustedPDFs/test.xlsx"', wait=True), 0)
        self.assertEqual(self.vm.run(
            'diff "orig.xlsx" "QubesUntrustedPDFs/test.xlsx"', wait=True), 0)

    def test_008_ods(self):
        if self.vm.run('command -v libreoffice >/dev/null', wait=True) != 0:
            self.skipTest('libreoffice not installed')
        self.create_ods('test.ods', 'This is test')
        p = self.vm.run(
            'cp test.ods orig.ods; qvm-convert-file test.ods 2>&1',
            passio_popen=True)
        (stdout, _) = p.communicate()
        self.assertEqual(
            p.returncode, 0, 'qvm-convert-file failed: {}'.format(stdout))
        self.assertEqual(
            self.vm.run('test -r "test.trusted.pdf"', wait=True), 0)
        trusted_info = self.get_pdfinfo('test.trusted.pdf')
        self.assertGreaterEqual(int(trusted_info['Pages']), 1)

        self.assertEqual(
            self.vm.run('test -r "QubesUntrustedPDFs/test.ods"', wait=True), 0)
        self.assertEqual(self.vm.run(
            'diff "orig.ods" "QubesUntrustedPDFs/test.ods"', wait=True), 0)


def list_tests():
    tests = [TC_00_PDFConverter]
    return tests
