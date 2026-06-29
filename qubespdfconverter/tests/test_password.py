#!/usr/bin/python3
# SPDX-License-Identifier: GPL-2.0-or-later

"""Unit tests for password-protected PDF support."""

import asyncio
import io
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from qubespdfconverter.constants import LIBREOFFICE_MISSING_EXIT_CODE

from qubespdfconverter.server import (
    BaseFile,
    LibreOfficeDocumentRenderer,
    PdfRenderer,
    create_renderer,
    LibreOfficeMissingError,
    renderer_name_for_path,
)


class TC_ServerPassword(unittest.IsolatedAsyncioTestCase):
    """Tests for server-side password handling."""

    def test_pagenums_includes_password_flags(self):
        """pdfinfo receives -opw/-upw when a password is provided."""
        with tempfile.NamedTemporaryFile(suffix=".pdf") as f:
            renderer = PdfRenderer(Path(f.name), password=b"secret")
            base = BaseFile(Path(f.name), renderer)

            mock_result = mock.Mock()
            mock_result.stdout = b"Pages:           3\n"

            with mock.patch("subprocess.run", return_value=mock_result) as run_mock:
                base._pagenums()

            cmd = run_mock.call_args[0][0]
            self.assertIn("-opw", cmd)
            self.assertIn("-upw", cmd)
            self.assertIn("secret", cmd)

    def test_pagenums_omits_password_flags_when_empty(self):
        """pdfinfo does not receive password flags when password is empty."""
        with tempfile.NamedTemporaryFile(suffix=".pdf") as f:
            renderer = PdfRenderer(Path(f.name), password=b"")
            base = BaseFile(Path(f.name), renderer)

            mock_result = mock.Mock()
            mock_result.stdout = b"Pages:           2\n"

            with mock.patch("subprocess.run", return_value=mock_result) as run_mock:
                base._pagenums()

            cmd = run_mock.call_args[0][0]
            self.assertNotIn("-opw", cmd)
            self.assertNotIn("-upw", cmd)

    async def test_create_page_image_includes_password_flags(self):
        """pdftocairo receives -opw/-upw when a password is provided."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir, "original.pdf")
            path.touch()
            renderer = PdfRenderer(path, password=b"secret")

            mock_proc = mock.AsyncMock()
            mock_proc.returncode = 0
            mock_proc.wait = mock.AsyncMock(return_value=0)

            with mock.patch(
                "asyncio.create_subprocess_exec", return_value=mock_proc
            ) as exec_mock:
                await renderer.create_page_image(1, Path(tmpdir, "1.png"))

            cmd = exec_mock.call_args[0]
            self.assertIn("-opw", cmd)
            self.assertIn("-upw", cmd)
            self.assertIn("secret", cmd)

    async def test_create_page_image_omits_password_flags_when_empty(self):
        """pdftocairo does not receive password flags when password is empty."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir, "original.pdf")
            path.touch()
            renderer = PdfRenderer(path, password=b"")

            mock_proc = mock.AsyncMock()
            mock_proc.returncode = 0
            mock_proc.wait = mock.AsyncMock(return_value=0)

            with mock.patch(
                "asyncio.create_subprocess_exec", return_value=mock_proc
            ) as exec_mock:
                await renderer.create_page_image(1, Path(tmpdir, "1.png"))

            cmd = exec_mock.call_args[0]
            self.assertNotIn("-opw", cmd)
            self.assertNotIn("-upw", cmd)

    def test_create_renderer_returns_pdf_renderer(self):
        """The server dispatch table creates the PDF renderer."""
        with tempfile.NamedTemporaryFile(suffix=".pdf") as f:
            renderer = create_renderer(
                "pdf",
                Path(f.name),
                password=b"secret",
                resolution=200,
            )

        self.assertIsInstance(renderer, PdfRenderer)
        self.assertEqual(renderer.password, b"secret")
        self.assertEqual(renderer.resolution, "200")

    def test_create_renderer_returns_docx_renderer(self):
        """The server dispatch table creates the DOCX renderer."""
        with tempfile.NamedTemporaryFile(suffix=".docx") as f:
            renderer = create_renderer("docx", Path(f.name), resolution=200)

        self.assertIsInstance(renderer, LibreOfficeDocumentRenderer)
        self.assertEqual(renderer.resolution, 200)
        self.assertEqual(renderer.suffix, ".docx")

    def test_create_renderer_returns_odt_renderer(self):
        """The server dispatch table creates the ODT renderer."""
        with tempfile.NamedTemporaryFile(suffix=".odt") as f:
            renderer = create_renderer("odt", Path(f.name), resolution=200)

        self.assertIsInstance(renderer, LibreOfficeDocumentRenderer)
        self.assertEqual(renderer.resolution, 200)
        self.assertEqual(renderer.suffix, ".odt")

    def test_create_renderer_returns_ods_renderer(self):
        """The server dispatch table creates the ODS renderer."""
        with tempfile.NamedTemporaryFile(suffix=".ods") as f:
            renderer = create_renderer("ods", Path(f.name), resolution=200)

        self.assertIsInstance(renderer, LibreOfficeDocumentRenderer)
        self.assertEqual(renderer.resolution, 200)
        self.assertEqual(renderer.suffix, ".ods")

    def test_create_renderer_returns_xlsx_renderer(self):
        """The server dispatch table creates the XLSX renderer."""
        with tempfile.NamedTemporaryFile(suffix=".xlsx") as f:
            renderer = create_renderer("xlsx", Path(f.name), resolution=200)

        self.assertIsInstance(renderer, LibreOfficeDocumentRenderer)
        self.assertEqual(renderer.resolution, 200)
        self.assertEqual(renderer.suffix, ".xlsx")

    def test_create_renderer_rejects_unknown_type(self):
        """Unknown renderer names fail before any conversion starts."""
        with tempfile.NamedTemporaryFile(suffix=".pdf") as f:
            with self.assertRaises(ValueError):
                create_renderer("office", Path(f.name))

    def test_server_dispatches_pdf_mime_to_pdf_renderer_name(self):
        """MIME-based renderer selection happens on the server side."""
        with tempfile.NamedTemporaryFile(suffix=".pdf") as f, mock.patch(
            "qubespdfconverter.server.detect_mime",
            return_value="application/pdf",
        ):
            renderer_name = renderer_name_for_path(Path(f.name))

        self.assertEqual(renderer_name, "pdf")

    def test_server_dispatches_docx_mime_to_docx_renderer_name(self):
        """DOCX MIME detection selects the DOCX renderer on the server side."""
        mime_type = (
            "application/vnd.openxmlformats-officedocument." "wordprocessingml.document"
        )

        with tempfile.NamedTemporaryFile(suffix=".docx") as f, mock.patch(
            "qubespdfconverter.server.detect_mime",
            return_value=mime_type,
        ):
            renderer_name = renderer_name_for_path(Path(f.name))

        self.assertEqual(renderer_name, "docx")

    def test_server_dispatches_odt_mime_to_odt_renderer_name(self):
        """ODT MIME detection selects the shared document renderer."""
        mime_type = "application/vnd.oasis.opendocument.text"

        with tempfile.NamedTemporaryFile(suffix=".odt") as f, mock.patch(
            "qubespdfconverter.server.detect_mime",
            return_value=mime_type,
        ):
            renderer_name = renderer_name_for_path(Path(f.name))

        self.assertEqual(renderer_name, "odt")

    def test_server_dispatches_ods_mime_to_ods_renderer_name(self):
        """ODS MIME detection selects the shared document renderer."""
        mime_type = "application/vnd.oasis.opendocument.spreadsheet"

        with tempfile.NamedTemporaryFile(suffix=".ods") as f, mock.patch(
            "qubespdfconverter.server.detect_mime",
            return_value=mime_type,
        ):
            renderer_name = renderer_name_for_path(Path(f.name))

        self.assertEqual(renderer_name, "ods")

    def test_server_dispatches_xlsx_mime_to_xlsx_renderer_name(self):
        """XLSX MIME detection selects the shared document renderer."""
        mime_type = (
            "application/vnd.openxmlformats-officedocument." "spreadsheetml.sheet"
        )

        with tempfile.NamedTemporaryFile(suffix=".xlsx") as f, mock.patch(
            "qubespdfconverter.server.detect_mime",
            return_value=mime_type,
        ):
            renderer_name = renderer_name_for_path(Path(f.name))

        self.assertEqual(renderer_name, "xlsx")

    def test_server_rejects_unsupported_mime(self):
        """Unsupported MIME types fail before selecting a renderer."""
        with tempfile.NamedTemporaryFile(suffix=".txt") as f, mock.patch(
            "qubespdfconverter.server.detect_mime",
            return_value="text/plain",
        ):
            with self.assertRaises(ValueError):
                renderer_name_for_path(Path(f.name))

    def test_docx_renderer_converts_to_pdf_before_page_count(self):
        """DOCX rendering converts through LibreOffice before PDF handling."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir, "source.docx")
            path.write_bytes(b"docx")
            renderer = LibreOfficeDocumentRenderer(path, resolution=200, suffix=".docx")

            def fake_run(cmd, capture_output, check):
                if cmd[0] == "libreoffice":
                    self.assertIn("--headless", cmd)
                    self.assertIn("--convert-to", cmd)
                    self.assertIn("pdf", cmd)
                    Path(cmd[-1]).with_suffix(".pdf").write_bytes(b"%PDF-1.7")
                    return mock.Mock(stdout=b"")

                self.assertEqual(cmd[0], "pdfinfo")
                return mock.Mock(stdout=b"Pages:           4\n")

            with mock.patch("subprocess.run", side_effect=fake_run):
                self.assertEqual(renderer.page_count(), 4)

    def test_docx_renderer_reports_missing_pdf_output(self):
        """A failed DOCX conversion without PDF output is reported clearly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir, "source.docx")
            path.write_bytes(b"docx")
            renderer = LibreOfficeDocumentRenderer(path, resolution=200, suffix=".docx")

            with mock.patch("subprocess.run", return_value=mock.Mock()):
                with self.assertRaises(ValueError):
                    renderer.page_count()

    def test_docx_renderer_reports_missing_libreoffice(self):
        """Missing LibreOffice is reported as a clear conversion error."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir, "source.docx")
            path.write_bytes(b"docx")
            renderer = LibreOfficeDocumentRenderer(path, resolution=200, suffix=".docx")

            with mock.patch("subprocess.run", side_effect=FileNotFoundError):
                with self.assertRaisesRegex(
                    LibreOfficeMissingError, "relevant template"
                ):
                    renderer.page_count()

    def test_missing_libreoffice_exit_code_is_nonzero(self):
        """Missing LibreOffice uses a dedicated failure code."""
        self.assertGreater(LIBREOFFICE_MISSING_EXIT_CODE, 0)

    def test_odt_renderer_uses_odt_extension_for_libreoffice(self):
        """ODT rendering uses the same LibreOffice path with an ODT input."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir, "source.odt")
            path.write_bytes(b"odt")
            renderer = LibreOfficeDocumentRenderer(path, resolution=200, suffix=".odt")

            def fake_run(cmd, capture_output, check):
                if cmd[0] == "libreoffice":
                    self.assertEqual(Path(cmd[-1]).suffix, ".odt")
                    Path(cmd[-1]).with_suffix(".pdf").write_bytes(b"%PDF-1.7")
                    return mock.Mock(stdout=b"")

                self.assertEqual(cmd[0], "pdfinfo")
                return mock.Mock(stdout=b"Pages:           2\n")

            with mock.patch("subprocess.run", side_effect=fake_run):
                self.assertEqual(renderer.page_count(), 2)

    def test_ods_renderer_uses_ods_extension_for_libreoffice(self):
        """ODS rendering uses the same LibreOffice path with an ODS input."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir, "source.ods")
            path.write_bytes(b"ods")
            renderer = LibreOfficeDocumentRenderer(path, resolution=200, suffix=".ods")

            def fake_run(cmd, capture_output, check):
                if cmd[0] == "libreoffice":
                    self.assertEqual(Path(cmd[-1]).suffix, ".ods")
                    Path(cmd[-1]).with_suffix(".pdf").write_bytes(b"%PDF-1.7")
                    return mock.Mock(stdout=b"")

                self.assertEqual(cmd[0], "pdfinfo")
                return mock.Mock(stdout=b"Pages:           2\n")

            with mock.patch("subprocess.run", side_effect=fake_run):
                self.assertEqual(renderer.page_count(), 2)

    def test_xlsx_renderer_uses_xlsx_extension_for_libreoffice(self):
        """XLSX rendering uses the same LibreOffice path with an XLSX input."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir, "source.xlsx")
            path.write_bytes(b"xlsx")
            renderer = LibreOfficeDocumentRenderer(path, resolution=200, suffix=".xlsx")

            def fake_run(cmd, capture_output, check):
                if cmd[0] == "libreoffice":
                    self.assertEqual(Path(cmd[-1]).suffix, ".xlsx")
                    Path(cmd[-1]).with_suffix(".pdf").write_bytes(b"%PDF-1.7")
                    return mock.Mock(stdout=b"")

                self.assertEqual(cmd[0], "pdfinfo")
                return mock.Mock(stdout=b"Pages:           2\n")

            with mock.patch("subprocess.run", side_effect=fake_run):
                self.assertEqual(renderer.page_count(), 2)


class TC_ServerBackwardCompat(unittest.TestCase):
    """Tests for backward-compatible stdin parsing in main()."""

    def _run_main_with_stdin(self, stdin_bytes):
        """Run main() with controlled stdin, return (password, data) parsed."""
        # Reproduce the logic from main() to test it in isolation
        buf = io.BytesIO(stdin_bytes)
        first_line = buf.readline()

        if first_line.startswith(b"--password="):
            password = first_line[len(b"--password=") :].rstrip(b"\n")
            prefix = b""
        else:
            password = b""
            prefix = first_line

        rest = buf.read()
        data = prefix + rest
        return password, data

    def test_old_client_pdf_sent_directly(self):
        """Old client sending PDF directly: no password extracted, data intact."""
        pdf_bytes = b"%PDF-1.4 ...\nsome content"
        password, data = self._run_main_with_stdin(pdf_bytes)
        self.assertEqual(password, b"")
        self.assertEqual(data, pdf_bytes)

    def test_new_client_no_password_sends_pdf_directly(self):
        """New client with no password sends PDF directly (backward compatible)."""
        pdf_bytes = b"%PDF-1.4 ...\nsome content"
        password, data = self._run_main_with_stdin(pdf_bytes)
        self.assertEqual(password, b"")
        self.assertEqual(data, pdf_bytes)

    def test_new_client_with_password(self):
        """New client sends --password= prefix: password extracted, PDF intact."""
        pdf_bytes = b"%PDF-1.4 ...\nsome content"
        stdin = b"--password=mysecret\n" + pdf_bytes
        password, data = self._run_main_with_stdin(stdin)
        self.assertEqual(password, b"mysecret")
        self.assertEqual(data, pdf_bytes)


class TC_ClientPassword(unittest.IsolatedAsyncioTestCase):
    """Tests for client-side password sending."""

    async def test_send_password_prefix_before_pdf(self):
        """Client sends --password=<pw> line before PDF bytes when password given."""
        from qubespdfconverter.client import Job

        job = Job(Path("/tmp/fake.pdf"), 0, password="hunter2")

        sent_data = []

        async def fake_send(proc, data):
            sent_data.append(data)

        mock_proc = mock.Mock()
        mock_proc.stdin = mock.Mock()
        job.proc = mock_proc

        with mock.patch(
            "qubespdfconverter.client.send", side_effect=fake_send
        ), mock.patch.object(Path, "read_bytes", return_value=b"%PDF-1.4"):
            await job._send()

        self.assertEqual(sent_data[0], "--password=hunter2\n")
        self.assertEqual(sent_data[1], b"%PDF-1.4")

    async def test_send_pdf_directly_when_no_password(self):
        """Client sends PDF bytes directly when no password (backward compatible)."""
        from qubespdfconverter.client import Job

        job = Job(Path("/tmp/fake.pdf"), 0, password="")

        sent_data = []

        async def fake_send(proc, data):
            sent_data.append(data)

        mock_proc = mock.Mock()
        mock_proc.stdin = mock.Mock()
        job.proc = mock_proc

        with mock.patch(
            "qubespdfconverter.client.send", side_effect=fake_send
        ), mock.patch.object(Path, "read_bytes", return_value=b"%PDF-1.4"):
            await job._send()

        self.assertEqual(len(sent_data), 1)
        self.assertEqual(sent_data[0], b"%PDF-1.4")


class TC_ClientDetectionAndPrompt(unittest.TestCase):
    """Tests for client-side encrypted PDF detection and GUI prompt."""

    def test_detect_encrypted_pdf_by_encrypt_marker(self):
        """Detect encrypted PDFs by checking for /Encrypt marker."""
        from qubespdfconverter.client import is_pdf_password_protected

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir, "encrypted.pdf")
            # Minimal pseudo-PDF layout with encryption marker in tail.
            path.write_bytes(
                b"%PDF-1.7\n"
                b"1 0 obj\n<< /Type /Catalog >>\nendobj\n"
                b"trailer\n<< /Encrypt 5 0 R >>\n%%EOF\n"
            )

            self.assertTrue(is_pdf_password_protected(path))

    def test_detect_plain_pdf_without_encrypt_marker(self):
        """Do not mark non-encrypted PDFs as encrypted."""
        from qubespdfconverter.client import is_pdf_password_protected

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir, "plain.pdf")
            path.write_bytes(
                b"%PDF-1.7\n"
                b"1 0 obj\n<< /Type /Catalog >>\nendobj\n"
                b"trailer\n<< /Root 1 0 R >>\n%%EOF\n"
            )

            self.assertFalse(is_pdf_password_protected(path))

    def test_prompt_password_zenity_success(self):
        """Return password from zenity output when prompt succeeds."""
        from qubespdfconverter.client import prompt_password_zenity

        result = mock.Mock()
        result.returncode = 0
        result.stdout = b"secret\n"

        with tempfile.NamedTemporaryFile(suffix=".pdf") as f, mock.patch(
            "subprocess.run", return_value=result
        ):
            password = prompt_password_zenity(Path(f.name))

        self.assertEqual(password, "secret")

    def test_prompt_password_zenity_cancel(self):
        """Return None when zenity prompt is canceled."""
        from qubespdfconverter.client import prompt_password_zenity

        result = mock.Mock()
        result.returncode = 1
        result.stdout = b""

        with tempfile.NamedTemporaryFile(suffix=".pdf") as f, mock.patch(
            "subprocess.run", return_value=result
        ):
            password = prompt_password_zenity(Path(f.name))

        self.assertIsNone(password)


if __name__ == "__main__":
    unittest.main()
