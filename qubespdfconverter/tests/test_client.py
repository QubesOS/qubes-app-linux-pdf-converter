#!/usr/bin/python3

import asyncio
import os
import signal
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import click

from qubespdfconverter.constants import (
    FFMPEG_MISSING_EXIT_CODE,
    LIBREOFFICE_MISSING_EXIT_CODE,
)
from qubespdfconverter import ocr_config

from qubespdfconverter.client import (
    BadPath,
    BaseFile,
    ERROR_LOGS,
    Job,
    QrexecError,
    apply_ocr_default,
    expand_dir,
    run,
    validate_ocr_lang,
    validate_paths,
)
from qubespdfconverter.ocr import OcrDependencyError
from qubespdfconverter.protocol import (
    OutputFileError,
    PageError,
    TrustedOutput,
    parse_output_header,
)


class DummyProc:
    def __init__(self):
        self.returncode = None
        self.terminated = False
        self.stdin = mock.Mock()
        self.stdout = mock.Mock()

    def terminate(self):
        self.terminated = True
        self.returncode = -signal.SIGTERM

    async def wait(self):
        if self.returncode is None:
            self.returncode = 0


class TC_ClientCancel(unittest.IsolatedAsyncioTestCase):
    async def test_000_cancel_terminates_qrexec_proc(self):
        job = Job(Path("/tmp/test.pdf"), 0)
        proc = DummyProc()

        with mock.patch(
            "asyncio.create_subprocess_exec", new=mock.AsyncMock(return_value=proc)
        ):
            job._setup = mock.AsyncMock()
            job._start = mock.AsyncMock(side_effect=asyncio.CancelledError)

            with self.assertRaises(asyncio.CancelledError):
                await job.run(Path("/tmp/archive"), depth=1, in_place=False)

        self.assertTrue(proc.terminated)

    async def test_001_failure_terminates_qrexec_proc(self):
        job = Job(Path("/tmp/test.pdf"), 0)
        proc = DummyProc()

        with mock.patch(
            "asyncio.create_subprocess_exec", new=mock.AsyncMock(return_value=proc)
        ):
            job._setup = mock.AsyncMock(side_effect=PageError)

            with self.assertRaises(PageError):
                await job.run(Path("/tmp/archive"), depth=1, in_place=False)

        self.assertTrue(proc.terminated)

    async def test_002_register_sigterm_handler(self):
        loop = asyncio.get_running_loop()
        add_handler_mock = mock.Mock()

        with mock.patch.object(loop, "add_signal_handler", new=add_handler_mock):
            result = await run(
                {
                    "resolution": 300,
                    "files": [],
                    "archive": Path("/tmp/archive"),
                    "batch": 1,
                    "in_place": False,
                    "ocr_lang": None,
                }
            )

        self.assertFalse(result)
        handled = {call.args[0] for call in add_handler_mock.mock_calls}
        self.assertEqual(handled, {signal.SIGINT, signal.SIGTERM})

    async def test_003_output_info_propagates_missing_libreoffice_exit_code(self):
        job = Job(Path("/tmp/test.docx"), 0)
        proc = DummyProc()
        proc.returncode = LIBREOFFICE_MISSING_EXIT_CODE
        proc.stdout.readline = mock.AsyncMock(return_value=b"")
        job.proc = proc

        with self.assertRaises(subprocess.CalledProcessError) as exc:
            await job._output_info()

        self.assertEqual(exc.exception.returncode, LIBREOFFICE_MISSING_EXIT_CODE)

    async def test_004_ocr_dependency_error_stops_before_qrexec(self):
        with mock.patch(
            "qubespdfconverter.client.ocr.check_available",
            side_effect=OcrDependencyError("missing OCR dependency"),
        ), mock.patch("asyncio.create_subprocess_exec") as create_mock:
            result = await run(
                {
                    "resolution": 300,
                    "files": [Path("/tmp/test.pdf")],
                    "archive": Path("/tmp/archive"),
                    "batch": 1,
                    "in_place": False,
                    "ocr_lang": "eng",
                }
            )

        self.assertEqual(result, 1)
        create_mock.assert_not_called()

    async def test_005_ocr_reps_insert_pages_into_ocr_document(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            pdf = Path(tmpdir, "out.pdf")
            png = Path(tmpdir, "1.png")
            png.write_bytes(b"png")
            base = BaseFile(Path("/tmp/test.pdf"), 1, pdf, ocr_lang="eng")
            base.ocr_doc = mock.Mock()
            base.ocr_tessdata_dir = Path("/tmp/tessdata")
            page_doc = mock.Mock()

            with mock.patch(
                "qubespdfconverter.client.ocr.png_to_pdf_page",
                return_value=page_doc,
            ) as ocr_mock:
                await base._save_ocr_reps([1])

        ocr_mock.assert_called_once_with(png, "eng", Path("/tmp/tessdata"), 300)
        base.ocr_doc.insert_pdf.assert_called_once_with(page_doc)
        page_doc.close.assert_called_once()
        self.assertFalse(png.exists())

    async def test_006_cli_uses_configured_ocr_default(self):
        params = {"ocr_lang": None}

        with mock.patch(
            "qubespdfconverter.client.ocr_config.get_default_ocr_lang",
            return_value="eng",
        ), mock.patch(
            "qubespdfconverter.client.ocr.check_available"
        ) as check_mock:
            result = apply_ocr_default(params)

        self.assertTrue(result)
        self.assertEqual(params["ocr_lang"], "eng")
        check_mock.assert_called_once_with("eng")

    async def test_007_ffmpeg_error_logs_fixed_message(self):
        while not ERROR_LOGS.empty():
            ERROR_LOGS.get_nowait()
            ERROR_LOGS.task_done()

        job = Job(Path("/tmp/test.mp4"), 0)
        proc = DummyProc()

        with mock.patch(
            "asyncio.create_subprocess_exec", new=mock.AsyncMock(return_value=proc)
        ):
            job._setup = mock.AsyncMock(
                side_effect=subprocess.CalledProcessError(
                    FFMPEG_MISSING_EXIT_CODE,
                    "qrexec-client-vm",
                )
            )

            with self.assertRaises(subprocess.CalledProcessError):
                await job.run(Path("/tmp/archive"), depth=1, in_place=False)

        self.assertTrue(proc.terminated)
        error = await ERROR_LOGS.get()
        ERROR_LOGS.task_done()
        self.assertIn("FFmpeg is required for this file type", error)
        self.assertIn("relevant template", error)

    async def test_008_setup_accepts_trusted_output_header(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            job = Job(Path(tmpdir, "source.mp4"), 0)
            job.bar = mock.Mock()
            job._send = mock.AsyncMock()
            job._output_info = mock.AsyncMock(return_value=TrustedOutput("ogv", 3))

            await job._setup(tmpdir)

        self.assertEqual(job.base, TrustedOutput("ogv", 3))
        self.assertEqual(job.pdf.name, "source.trusted.ogv")
        job.bar.reset.assert_called_once_with(total=1)

    async def test_009_receive_trusted_output_writes_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            job = Job(Path(tmpdir, "source.mp4"), 0)
            job.base = TrustedOutput("ogv", 3)
            job.proc = mock.Mock()
            job.pdf = Path(tmpdir, "source.trusted.ogv")
            job.bar = mock.Mock()

            with mock.patch(
                "qubespdfconverter.client.recv_b",
                new=mock.AsyncMock(return_value=b"ogv"),
            ) as recv_mock:
                await job._receive_trusted_output()

            recv_mock.assert_awaited_once_with(job.proc, 3)
            self.assertEqual(job.pdf.read_bytes(), b"ogv")
            job.bar.update.assert_called_once_with(1)
            job.bar.set_status.assert_called_once_with("1/1")

    async def test_010_receive_trusted_output_rejects_short_read(self):
        job = Job(Path("/tmp/source.mp4"), 0)
        job.base = TrustedOutput("ogv", 3)
        job.proc = mock.Mock()

        with mock.patch(
            "qubespdfconverter.client.recv_b",
            new=mock.AsyncMock(
                side_effect=asyncio.IncompleteReadError(b"o", 3)
            ),
        ):
            with self.assertRaises(QrexecError):
                await job._receive_trusted_output()

    async def test_011_run_propagates_missing_ffmpeg_exit_code(self):
        loop = asyncio.get_running_loop()

        async def failed_task():
            raise subprocess.CalledProcessError(
                FFMPEG_MISSING_EXIT_CODE,
                "qrexec-client-vm",
            )

        with mock.patch(
            "qubespdfconverter.client.collect_jobs",
            new=mock.AsyncMock(
                return_value=([], [asyncio.create_task(failed_task())], 0)
            ),
        ), mock.patch(
            "qubespdfconverter.client.apply_ocr_default",
            return_value=True,
        ), mock.patch.object(loop, "add_signal_handler"):
            result = await run(
                {
                    "resolution": 300,
                    "files": [Path("/tmp/test.mp4")],
                    "archive": Path("/tmp/archive"),
                    "batch": 1,
                    "in_place": False,
                    "ocr_lang": None,
                }
            )

        self.assertEqual(result, FFMPEG_MISSING_EXIT_CODE)


class TC_ExpandDir(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.d = Path(self.tmpdir.name)

    def tearDown(self):
        self.tmpdir.cleanup()

    def _touch(self, name):
        p = self.d / name
        p.touch()
        return p

    def test_000_returns_pdf_files_sorted(self):
        self._touch("b.pdf")
        self._touch("a.pdf")
        result = expand_dir(self.d)
        self.assertEqual([p.name for p in result], ["a.pdf", "b.pdf"])

    def test_001_ignores_non_pdf_files(self):
        self._touch("doc.pdf")
        self._touch("image.png")
        self._touch("notes.txt")
        result = expand_dir(self.d)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].name, "doc.pdf")

    def test_002_ignores_symlinks(self):
        real = self._touch("real.pdf")
        link = self.d / "link.pdf"
        link.symlink_to(real)
        result = expand_dir(self.d)
        names = [p.name for p in result]
        self.assertIn("real.pdf", names)
        self.assertNotIn("link.pdf", names)

    def test_003_empty_directory_returns_empty_list(self):
        result = expand_dir(self.d)
        self.assertEqual(result, [])

    def test_004_case_insensitive_pdf_extension(self):
        self._touch("doc.PDF")
        self._touch("other.Pdf")
        result = expand_dir(self.d)
        self.assertEqual(len(result), 2)

    def test_005_unreadable_directory_raises_badpath(self):
        self.d.chmod(0o000)
        try:
            with self.assertRaises(BadPath):
                expand_dir(self.d)
        finally:
            self.d.chmod(0o755)


class TC_ValidatePaths(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.d = Path(self.tmpdir.name)

    def tearDown(self):
        self.tmpdir.cleanup()

    def _touch(self, name):
        p = self.d / name
        p.touch()
        return p

    def test_000_valid_pdf_file_returned(self):
        pdf = self._touch("doc.pdf")
        result = validate_paths(None, None, [pdf])
        self.assertIn(pdf.resolve(), result)

    def test_001_nonexistent_file_raises_badpath(self):
        with self.assertRaises(BadPath):
            validate_paths(None, None, [self.d / "missing.pdf"])

    def test_002_directory_expands_to_pdf_files(self):
        (self.d / "a.pdf").touch()
        (self.d / "b.pdf").touch()
        result = validate_paths(None, None, [self.d])
        self.assertEqual(len(result), 2)

    def test_003_empty_directory_produces_no_paths(self):
        result = validate_paths(None, None, [self.d])
        self.assertEqual(result, ())

    @unittest.skipUnless(hasattr(os, "mkfifo"), "mkfifo not available on this platform")
    def test_004_non_file_non_dir_raises_badpath(self):
        fifo = self.d / "pipe"
        os.mkfifo(fifo)
        with self.assertRaises(BadPath):
            validate_paths(None, None, [fifo])

    def test_005_multiple_files_all_returned(self):
        a = self._touch("a.pdf")
        b = self._touch("b.pdf")
        result = validate_paths(None, None, [a, b])
        self.assertEqual(set(result), {a.resolve(), b.resolve()})


class TC_OutputHeader(unittest.TestCase):
    def test_000_parse_page_count_header(self):
        self.assertEqual(parse_output_header("3"), 3)

    def test_001_parse_trusted_file_header(self):
        output = parse_output_header("FILE ogv 123")

        self.assertEqual(output, TrustedOutput("ogv", 123))

    def test_002_reject_invalid_trusted_file_suffix(self):
        with self.assertRaises(OutputFileError):
            parse_output_header("FILE ../bad 123")

    def test_003_reject_invalid_trusted_file_size(self):
        with self.assertRaises(OutputFileError):
            parse_output_header("FILE ogv 0")

    def test_004_reject_malformed_trusted_file_header(self):
        with self.assertRaises(OutputFileError):
            parse_output_header("FILE ogv")

    def test_005_reject_invalid_page_count(self):
        with self.assertRaises(PageError):
            parse_output_header("0")

    def test_006_reject_nonnumeric_page_count(self):
        with self.assertRaises(ValueError):
            parse_output_header("not-a-page-count")

    def test_007_ffmpeg_exit_code_is_nonzero(self):
        self.assertGreater(FFMPEG_MISSING_EXIT_CODE, 0)


class TC_OcrLang(unittest.TestCase):
    def test_000_empty_language_returns_none(self):
        self.assertIsNone(validate_ocr_lang(None, None, None))

    def test_001_valid_language_returned(self):
        self.assertEqual(validate_ocr_lang(None, None, "eng"), "eng")

    def test_002_multiple_languages_returned(self):
        self.assertEqual(validate_ocr_lang(None, None, "eng+hin"), "eng+hin")

    def test_003_invalid_language_raises_bad_parameter(self):
        with self.assertRaises(click.BadParameter):
            validate_ocr_lang(None, None, "eng;rm")


class TC_OcrConfig(unittest.TestCase):
    def test_000_missing_config_disables_ocr(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir, "missing.conf")
            self.assertIsNone(ocr_config.read_config(path))
            self.assertIsNone(ocr_config.get_default_ocr_lang(path))

    def test_001_write_enabled_config(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir, "ocr.conf")
            ocr_config.write_config(True, "eng", path)

            self.assertEqual(ocr_config.read_config(path), (True, "eng"))
            self.assertEqual(ocr_config.get_default_ocr_lang(path), "eng")

    def test_002_write_disabled_config(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir, "ocr.conf")
            ocr_config.write_config(False, "eng", path)

            self.assertEqual(ocr_config.read_config(path), (False, "eng"))
            self.assertIsNone(ocr_config.get_default_ocr_lang(path))


if __name__ == "__main__":
    unittest.main()
