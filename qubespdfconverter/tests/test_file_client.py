#!/usr/bin/python3

import unittest
from pathlib import Path
from unittest import mock

from click.testing import CliRunner

from qubespdfconverter import file_client


class TC_FileClient(unittest.TestCase):
    def test_pdf_mime_uses_pdf_converter(self):
        runner = CliRunner()

        with runner.isolated_filesystem():
            Path("report.pdf").write_bytes(b"%PDF-1.7\n")

            with mock.patch(
                "qubespdfconverter.file_client.detect_mime",
                return_value="application/pdf",
            ), mock.patch(
                "qubespdfconverter.file_client.pdf_client.run",
                new=mock.AsyncMock(return_value=False),
            ) as run_mock:
                result = runner.invoke(file_client.main, ["report.pdf"])

        self.assertEqual(result.exit_code, 0)
        run_mock.assert_awaited_once()
        params = run_mock.await_args.args[0]
        self.assertEqual(params["files"], (Path("report.pdf"),))

    def test_unsupported_mime_is_rejected(self):
        runner = CliRunner()

        with runner.isolated_filesystem():
            Path("report.docx").write_bytes(b"not a pdf")

            with mock.patch(
                "qubespdfconverter.file_client.detect_mime",
                return_value=(
                    "application/vnd.openxmlformats-officedocument."
                    "wordprocessingml.document"
                ),
            ), mock.patch(
                "qubespdfconverter.file_client.pdf_client.run",
                new=mock.AsyncMock(),
            ) as run_mock:
                result = runner.invoke(file_client.main, ["report.docx"])

        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("unsupported file type", result.output)
        run_mock.assert_not_called()

    def test_extension_does_not_override_mime(self):
        runner = CliRunner()

        with runner.isolated_filesystem():
            Path("fake.pdf").write_text("plain text", encoding="utf-8")

            with mock.patch(
                "qubespdfconverter.file_client.detect_mime",
                return_value="text/plain",
            ), mock.patch(
                "qubespdfconverter.file_client.pdf_client.run",
                new=mock.AsyncMock(),
            ) as run_mock:
                result = runner.invoke(file_client.main, ["fake.pdf"])

        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("text/plain", result.output)
        run_mock.assert_not_called()


if __name__ == "__main__":
    unittest.main()
