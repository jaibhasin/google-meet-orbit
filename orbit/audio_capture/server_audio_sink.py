from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass

from orbit.core import log


SINK_NAME_PREFIX = "orbit_meet_"
MAX_SINK_NAME_LENGTH = 64


def generate_sink_name(session_id: str) -> str:
    """Return a deterministic, shell-safe sink name with the required prefix."""
    safe_session_id = re.sub(r"[^a-zA-Z0-9_-]", "_", (session_id or "").strip().lower())
    safe_session_id = safe_session_id.strip("-_") or "session"

    max_base_length = max(MAX_SINK_NAME_LENGTH - len(SINK_NAME_PREFIX), 8)
    if len(safe_session_id) > max_base_length:
        safe_session_id = safe_session_id[:max_base_length]

    return f"{SINK_NAME_PREFIX}{safe_session_id}"


def build_ffmpeg_command(sink_name: str) -> list[str]:
    return [
        "ffmpeg",
        "-f",
        "pulse",
        "-i",
        f"{sink_name}.monitor",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-f",
        "s16le",
        "pipe:1",
    ]


def _extract_module_id(output: bytes | str | None) -> str | None:
    if not output:
        return None
    text = output.decode("utf-8", errors="ignore") if isinstance(output, bytes) else str(output)
    match = re.search(r"^(\d+)\s*$", text.strip())
    if match:
        return match.group(1)
    return None


async def _run_pactl_command(*args: str) -> tuple[int | None, bytes, bytes]:
    process = await asyncio.create_subprocess_exec(
        "pactl",
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await process.communicate()
    return process.returncode, stdout, stderr


@dataclass
class ServerAudioSinkHandle:
    session_id: str
    capture_session_id: str
    sink_name: str
    module_id: str | None = None
    ffmpeg_process: asyncio.subprocess.Process | None = None

    async def start(self) -> None:
        if self.ffmpeg_process is not None:
            return

        return_code, module_output, _ = await _run_pactl_command(
            "load-module",
            "module-null-sink",
            f"sink_name={self.sink_name}",
        )
        if return_code != 0:
            raise RuntimeError("Failed to create PulseAudio sink for server capture.")

        self.module_id = _extract_module_id(module_output)
        if not self.module_id:
            raise RuntimeError("Server capture sink module id was not returned by pactl.")

        try:
            self.ffmpeg_process = await asyncio.create_subprocess_exec(
                *build_ffmpeg_command(self.sink_name),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except Exception:
            await self._stop_module_if_needed()
            raise

    async def stop(self) -> None:
        await self._stop_ffmpeg_if_needed()
        await self._stop_module_if_needed()

    async def _stop_ffmpeg_if_needed(self) -> None:
        process = self.ffmpeg_process
        self.ffmpeg_process = None
        if process is None:
            return
        if process.returncode is not None:
            return

        try:
            process.terminate()
            await asyncio.wait_for(process.wait(), timeout=5)
        except asyncio.TimeoutError:
            try:
                process.kill()
                await process.wait()
            except Exception as error:
                log(
                    f"Failed to force-kill ffmpeg process for capture session {self.capture_session_id}: {error}",
                    level="error",
                )
        except Exception as error:
            log(
                f"Error stopping ffmpeg process for capture session {self.capture_session_id}: {error}",
                level="error",
            )

    async def _stop_module_if_needed(self) -> None:
        module_id = self.module_id
        self.module_id = None
        if not module_id:
            return

        try:
            return_code, _, _ = await _run_pactl_command("unload-module", module_id)
            if return_code != 0:
                log(
                    f"Failed to unload sink module {module_id} for capture session {self.capture_session_id}.",
                    level="debug",
                )
        except Exception as error:
            log(
                f"Failed to unload sink module {module_id} for capture session {self.capture_session_id}: {error}",
                level="error",
            )


async def start_server_audio_sink_capture(
    session_id: str,
    capture_session_id: str,
) -> ServerAudioSinkHandle:
    handle = ServerAudioSinkHandle(
        session_id=session_id,
        capture_session_id=capture_session_id,
        sink_name=generate_sink_name(session_id),
    )
    await handle.start()
    return handle
