from __future__ import annotations

import asyncio
import io
import runpy
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import AsyncMock, patch
import unittest

from orbit import server_audio_sink_check


class FakeSubprocess:
    def __init__(self, return_code: int | None = 0, stdout: bytes = b"", stderr: bytes = b""):
        self.returncode = return_code
        self._stdout = stdout
        self._stderr = stderr
        self.terminated = False
        self.killed = False
        self.wait_calls = 0
        self.communicate_calls = 0

    async def communicate(self):
        self.communicate_calls += 1
        if self.returncode is None:
            self.returncode = 0
        return self._stdout, self._stderr

    def terminate(self):
        self.terminated = True

    def kill(self):
        self.killed = True

    async def wait(self):
        self.wait_calls += 1
        if self.returncode is None:
            self.returncode = 0
        return self.returncode


class ServerAudioSinkCheckTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self._orig_which = server_audio_sink_check.shutil.which
        self._platform_patcher = patch.object(server_audio_sink_check.platform, "system", return_value="Linux")
        self._platform_patcher.start()

    async def asyncTearDown(self):
        self._platform_patcher.stop()
        server_audio_sink_check.shutil.which = self._orig_which

    async def test_darwin_reports_linux_only_message_without_binary_checks(self):
        with patch.object(server_audio_sink_check.platform, "system", return_value="Darwin"):
            with patch.object(server_audio_sink_check.shutil, "which") as which:
                with patch("orbit.server_audio_sink_check._run_command", new_callable=AsyncMock) as run_command:
                    report = await server_audio_sink_check.check_server_audio_sink_runtime(
                        sink_name="orbit_meet_test"
                    )

        self.assertFalse(report.ok)
        self.assertEqual(len(report.steps), 1)
        self.assertEqual(report.steps[0].name, "platform")
        self.assertEqual(report.steps[0].detail, server_audio_sink_check.DARWIN_UNSUPPORTED_MESSAGE)
        self.assertIsNone(report.steps[0].suggestion)
        which.assert_not_called()
        run_command.assert_not_awaited()

    async def test_darwin_wrapper_prints_linux_only_message(self):
        stdout = io.StringIO()
        script_path = Path(__file__).resolve().parents[1] / "scripts" / "check_server_audio_sink.py"

        with patch("platform.system", return_value="Darwin"):
            with redirect_stdout(stdout):
                with self.assertRaises(SystemExit) as exc_info:
                    runpy.run_path(str(script_path), run_name="__main__")

        self.assertEqual(exc_info.exception.code, 1)
        self.assertEqual(stdout.getvalue().strip(), server_audio_sink_check.DARWIN_UNSUPPORTED_MESSAGE)

    async def test_missing_ffmpeg_reports_failure(self):
        with patch.dict("os.environ", {}, clear=False):
            with patch.object(server_audio_sink_check.shutil, "which") as which:
                which.side_effect = lambda command: None if command == "ffmpeg" else "/usr/bin/pactl"
                report = await server_audio_sink_check.check_server_audio_sink_runtime(sink_name="orbit_meet_test")

        self.assertFalse(report.ok)
        self.assertEqual(report.steps[0].name, "ffmpeg")
        self.assertFalse(report.steps[0].ok)
        self.assertIn("not found", (report.steps[0].detail or ""))

    async def test_missing_pactl_reports_failure(self):
        with patch.object(server_audio_sink_check.shutil, "which") as which:
            which.side_effect = lambda command: "/usr/bin/ffmpeg" if command == "ffmpeg" else None
            report = await server_audio_sink_check.check_server_audio_sink_runtime(sink_name="orbit_meet_test")

        self.assertFalse(report.ok)
        self.assertEqual(report.steps[1].name, "pactl")
        self.assertFalse(report.steps[1].ok)
        self.assertIn("not found", report.steps[1].detail or "")

    async def test_sink_creation_failure_reports_error(self):
        with patch.object(server_audio_sink_check.shutil, "which", return_value="/usr/bin/test-bin"):
            with patch(
                "orbit.server_audio_sink_check._run_command",
                new_callable=AsyncMock,
            ) as run_command:
                run_command.side_effect = [
                    (0, b"Server Name: PipeWire", b""),  # pactl info
                    (1, b"", b"module load failed"),       # load-module
                ]
                report = await server_audio_sink_check.check_server_audio_sink_runtime(sink_name="orbit_meet_test")

        self.assertFalse(report.ok)
        self.assertEqual(report.steps[3].name, "null_sink_create")
        self.assertFalse(report.steps[3].ok)
        self.assertIn("module load failed", report.steps[3].detail or "")

    async def test_ffmpeg_open_failure_marks_cleanup_and_reports_error(self):
        ffmpeg_process = FakeSubprocess(1, b"", b"could not open monitor")

        async def run_command_side_effect(*args):
            if args[0] == "pactl" and args[1] == "info":
                return 0, b"Server Name: PipeWire", b""
            if args[0] == "pactl" and args[1] == "load-module":
                return 0, b"17\n", b""
            if args[0] == "pactl" and args[1] == "list":
                return 0, b"1\torbit_meet_test\tmodule-null-sink\tpipewire\t\n", b""
            if args[0] == "pactl" and args[1] == "unload-module":
                return 0, b"", b""
            raise AssertionError(f"unexpected command {args}")

        with patch.object(server_audio_sink_check.shutil, "which", return_value="/usr/bin/test-bin"):
            with patch.object(asyncio, "create_subprocess_exec") as create_subprocess:
                with patch("orbit.server_audio_sink_check._run_command", side_effect=run_command_side_effect):
                    create_subprocess.return_value = ffmpeg_process
                    report = await server_audio_sink_check.check_server_audio_sink_runtime(sink_name="orbit_meet_test")

        self.assertFalse(report.ok)
        self.assertEqual(report.steps[5].name, "ffmpeg_monitor_open")
        self.assertFalse(report.steps[5].ok)
        cleanup_steps = [step for step in report.steps if step.name == "cleanup"]
        self.assertEqual(len(cleanup_steps), 1)
        self.assertTrue(cleanup_steps[0].ok)

    async def test_sink_creation_success_path_cleans_up(self):
        with patch.object(server_audio_sink_check.shutil, "which", return_value="/usr/bin/test-bin"):
            with patch(
                "orbit.server_audio_sink_check._run_command",
                new_callable=AsyncMock,
            ) as run_command:
                run_command.side_effect = [
                    (0, b"Server Name: PipeWire", b""),  # pactl info
                    (0, b"17\n", b""),                  # load-module
                    (0, b"1\torbit_meet_test\tmodule-null-sink\tpipewire\t\n", b""),  # list sinks
                    (0, b"", b""),                      # unload module
                ]
                with patch.object(asyncio, "create_subprocess_exec") as create_subprocess:
                    ffmpeg_process = FakeSubprocess(None, b"", b"")
                    create_subprocess.return_value = ffmpeg_process
                    report = await server_audio_sink_check.check_server_audio_sink_runtime(sink_name="orbit_meet_test")

        self.assertTrue(ffmpeg_process.terminated)
        self.assertTrue(any(step.name == "cleanup" and step.ok for step in report.steps))
        self.assertTrue(report.ok)

    async def test_cleanup_reports_failure_when_unload_fails(self):
        with patch.object(server_audio_sink_check.shutil, "which", return_value="/usr/bin/test-bin"):
            with patch(
                "orbit.server_audio_sink_check._run_command",
                new_callable=AsyncMock,
            ) as run_command:
                unload_failed = (1, b"", b"unload failed")
                run_command.side_effect = [
                    (0, b"Server Name: PipeWire", b""),  # pactl info
                    (0, b"17\n", b""),                  # load-module
                    (0, b"1\torbit_meet_test\tmodule-null-sink\tpipewire\t\n", b""),  # list sinks
                    unload_failed,                            # unload-module
                ]
                with patch.object(asyncio, "create_subprocess_exec") as create_subprocess:
                    ffmpeg_process = FakeSubprocess(None, b"", b"")
                    create_subprocess.return_value = ffmpeg_process
                    report = await server_audio_sink_check.check_server_audio_sink_runtime(sink_name="orbit_meet_test")

        self.assertFalse(report.ok)
        cleanup_steps = [step for step in report.steps if step.name == "cleanup"]
        self.assertEqual(len(cleanup_steps), 1)
        self.assertFalse(cleanup_steps[0].ok)
        self.assertIn("unload failed", cleanup_steps[0].detail or "")
