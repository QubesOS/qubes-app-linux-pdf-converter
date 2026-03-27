#!/usr/bin/python3

import asyncio
import signal
import unittest
from pathlib import Path
from unittest import mock

from qubespdfconverter.client import Job, PageError, run


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


if __name__ == "__main__":
    unittest.main()
