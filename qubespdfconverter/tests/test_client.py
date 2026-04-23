#!/usr/bin/python3

import asyncio
import os
import signal
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from qubespdfconverter.client import BadPath, Job, PageError, expand_dir, run, validate_paths


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

        with mock.patch("asyncio.create_subprocess_exec", new=mock.AsyncMock(return_value=proc)):
            job._setup = mock.AsyncMock()
            job._start = mock.AsyncMock(side_effect=asyncio.CancelledError)

            with self.assertRaises(asyncio.CancelledError):
                await job.run(Path("/tmp/archive"), depth=1, in_place=False)

        self.assertTrue(proc.terminated)

    async def test_001_failure_terminates_qrexec_proc(self):
        job = Job(Path("/tmp/test.pdf"), 0)
        proc = DummyProc()

        with mock.patch("asyncio.create_subprocess_exec", new=mock.AsyncMock(return_value=proc)):
            job._setup = mock.AsyncMock(side_effect=PageError)

            with self.assertRaises(PageError):
                await job.run(Path("/tmp/archive"), depth=1, in_place=False)

        self.assertTrue(proc.terminated)

    async def test_002_register_sigterm_handler(self):
        loop = asyncio.get_running_loop()
        add_handler_mock = mock.Mock()

        with mock.patch.object(loop, "add_signal_handler", new=add_handler_mock):
            result = await run({
                "resolution": 300,
                "files": [],
                "archive": Path("/tmp/archive"),
                "batch": 1,
                "in_place": False,
            })

        self.assertFalse(result)
        handled = {call.args[0] for call in add_handler_mock.mock_calls}
        self.assertEqual(handled, {signal.SIGINT, signal.SIGTERM})


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

    @unittest.skipUnless(sys.platform != 'win32', 'symlink creation requires POSIX')
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

    @unittest.skipUnless(sys.platform != 'win32', 'chmod 000 not enforced on Windows')
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

    @unittest.skipUnless(hasattr(os, 'mkfifo'), 'mkfifo not available on this platform')
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


if __name__ == "__main__":
    unittest.main()
