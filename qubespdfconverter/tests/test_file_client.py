#!/usr/bin/python3

import unittest
from pathlib import Path
from unittest import mock

from click.testing import CliRunner

from qubespdfconverter import file_client


class TC_FileClient(unittest.TestCase):
    def test_uses_pdf_converter_without_client_mime_check(self):
        runner = CliRunner()

        with runner.isolated_filesystem():
            Path("report.pdf").write_bytes(b"%PDF-1.7\n")

            with mock.patch(
                "qubespdfconverter.file_client.pdf_client.run",
                new=mock.AsyncMock(return_value=False),
            ) as run_mock:
                result = runner.invoke(file_client.main, ["report.pdf"])

        self.assertEqual(result.exit_code, 0)
        run_mock.assert_awaited_once()
        params = run_mock.await_args.args[0]
        self.assertEqual(params["files"], (Path("report.pdf"),))

    def test_extension_is_not_checked_on_client(self):
        runner = CliRunner()

        with runner.isolated_filesystem():
            Path("report.docx").write_bytes(b"not a pdf")

            with mock.patch(
                "qubespdfconverter.file_client.pdf_client.run",
                new=mock.AsyncMock(return_value=False),
            ) as run_mock:
                result = runner.invoke(file_client.main, ["report.docx"])

        self.assertEqual(result.exit_code, 0)
        run_mock.assert_awaited_once()
        params = run_mock.await_args.args[0]
        self.assertEqual(params["files"], (Path("report.docx"),))

    def test_failed_server_conversion_is_reported(self):
        runner = CliRunner()

        with runner.isolated_filesystem():
            Path("fake.pdf").write_bytes(b"not a pdf")

            with mock.patch(
                "qubespdfconverter.file_client.pdf_client.run",
                new=mock.AsyncMock(return_value=True),
            ):
                result = runner.invoke(file_client.main, ["fake.pdf"])

        self.assertNotEqual(result.exit_code, 0)

    def test_ocr_lang_is_forwarded(self):
        runner = CliRunner()

        with runner.isolated_filesystem():
            Path("report.pdf").write_bytes(b"%PDF-1.7\n")

            with mock.patch(
                "qubespdfconverter.file_client.pdf_client.run",
                new=mock.AsyncMock(return_value=False),
            ) as run_mock:
                result = runner.invoke(
                    file_client.main,
                    ["--ocr-lang", "eng", "report.pdf"]
                )

        self.assertEqual(result.exit_code, 0)
        params = run_mock.await_args.args[0]
        self.assertEqual(params["ocr_lang"], "eng")


if __name__ == "__main__":
    unittest.main()
