from __future__ import annotations

import argparse
import asyncio
import os
import re
import shutil
import secrets
from dataclasses import dataclass

from orbit.audio_capture import build_ffmpeg_command, generate_sink_name


@dataclass
class CheckStep:
    name: str
    ok: bool
    detail: str | None = None
    suggestion: str | None = None


@dataclass
class CheckReport:
    sink_name: str
    module_id: str | None
    steps: list[CheckStep]

    @property
    def ok(self) -> bool:
        return all(step.ok for step in self.steps)


def _extract_module_id(output: bytes | str | None) -> str | None:
    if not output:
        return None
    text = output.decode("utf-8", errors="ignore") if isinstance(output, bytes) else str(output)
    match = re.search(r"^(\d+)\s*$", text.strip())
    if match:
        return match.group(1)
    return None


def _decode_bytes(value: bytes | None) -> str:
    if not value:
        return ""
    return value.decode("utf-8", errors="ignore").strip()


async def _run_command(*args: str) -> tuple[int, bytes, bytes]:
    process = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await process.communicate()
    return process.returncode or 0, stdout, stderr


async def _stop_process(process) -> bool:
    if process is None:
        return True

    if process.returncode is not None:
        return True

    try:
        process.terminate()
        await asyncio.wait_for(process.wait(), timeout=3)
        return True
    except asyncio.TimeoutError:
        try:
            process.kill()
            await process.wait()
            return True
        except Exception:
            return False
    except Exception:
        return False


async def _check_binary(name: str, fix: str) -> CheckStep:
    if shutil.which(name):
        return CheckStep(name=name, ok=True, detail="ok")
    return CheckStep(name=name, ok=False, detail=f"{name} not found on PATH", suggestion=fix)


async def _check_pulse_compatibility() -> CheckStep:
    returncode, stdout, stderr = await _run_command("pactl", "info")
    if returncode != 0:
        return CheckStep(
            name="pulse_compatibility",
            ok=False,
            detail=_decode_bytes(stderr) or _decode_bytes(stdout) or f"pactl info exited with code {returncode}",
            suggestion="Start PulseAudio/PipeWire and ensure pactl can read server info.",
        )

    info_text = _decode_bytes(stdout)
    if "Server Name" not in info_text:
        return CheckStep(
            name="pulse_compatibility",
            ok=False,
            detail="pactl info output did not contain a server name.",
            suggestion="Verify a PulseAudio/PipeWire-compatible server is running.",
        )
    return CheckStep(name="pulse_compatibility", ok=True, detail="ok")


async def _check_sink_registration(sink_name: str) -> CheckStep:
    returncode, stdout, stderr = await _run_command("pactl", "list", "short", "sinks")
    if returncode != 0:
        return CheckStep(
            name="sink_listed",
            ok=False,
            detail=_decode_bytes(stderr) or _decode_bytes(stdout) or f"pactl list short sinks exited with code {returncode}",
            suggestion="Ensure the generated sink is loaded in your PulseAudio/PipeWire session.",
        )

    sink_lines = [
        line.strip() for line in _decode_bytes(stdout).splitlines() if line.strip()
    ]
    sink_exists = any(
        fields[1] == sink_name
        for fields in (line.split(maxsplit=2) for line in sink_lines)
        if len(fields) >= 2
    )
    if not sink_exists:
        return CheckStep(
            name="sink_listed",
            ok=False,
            detail=f"Sink {sink_name} is not present in pactl sink list.",
            suggestion="Verify the sink was created and load-module did not fail.",
        )
    return CheckStep(name="sink_listed", ok=True, detail="ok")


async def _check_ffmpeg_monitor_open(sink_name: str) -> tuple[CheckStep, object | None]:
    process = None
    try:
        process = await asyncio.create_subprocess_exec(
            *build_ffmpeg_command(sink_name),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await asyncio.sleep(0.75)
        if process.returncode is not None and process.returncode != 0:
            _, stderr = await process.communicate()
            return CheckStep(
                name="ffmpeg_monitor_open",
                ok=False,
                detail=_decode_bytes(stderr) or f"ffmpeg exited with code {process.returncode}",
                suggestion="Verify ffmpeg supports PulseAudio/PipeWire monitor capture and the sink exists.",
            ), process
        return CheckStep(name="ffmpeg_monitor_open", ok=True, detail="ok"), process
    except Exception as error:
        return CheckStep(
            name="ffmpeg_monitor_open",
            ok=False,
            detail=str(error),
            suggestion="Check ffmpeg install and sink monitor availability.",
        ), process


def run_server_audio_sink_check(sink_name: str | None = None) -> CheckReport:
    return asyncio.run(check_server_audio_sink_runtime(sink_name=sink_name))


async def check_server_audio_sink_runtime(
    sink_name: str | None = None,
) -> CheckReport:
    sink_name = sink_name or generate_sink_name(
        f"check-{os.getpid()}-{secrets.token_hex(2)}"
    )
    module_id: str | None = None
    ffmpeg_process = None

    steps: list[CheckStep] = []
    steps.append(
        await _check_binary(
            "ffmpeg",
            "Install ffmpeg and ensure it is on PATH (for example: `apt install ffmpeg` or `brew install ffmpeg`).",
        )
    )
    if not steps[-1].ok:
        return CheckReport(sink_name=sink_name, module_id=None, steps=steps)

    steps.append(
        await _check_binary(
            "pactl",
            (
                "Install PulseAudio/PipeWire CLI tools and ensure the `pactl` binary is on PATH "
                "(for example: `apt install pulseaudio-utils` or `pacman -S pulseaudio`)."
            ),
        )
    )
    if not steps[-1].ok:
        return CheckReport(sink_name=sink_name, module_id=None, steps=steps)

    steps.append(await _check_pulse_compatibility())
    if not steps[-1].ok:
        return CheckReport(sink_name=sink_name, module_id=None, steps=steps)

    returncode, stdout, stderr = await _run_command(
        "pactl",
        "load-module",
        "module-null-sink",
        f"sink_name={sink_name}",
    )
    if returncode != 0:
        steps.append(
            CheckStep(
                name="null_sink_create",
                ok=False,
                detail=_decode_bytes(stderr) or _decode_bytes(stdout) or f"pactl load-module exited with code {returncode}",
                suggestion=(
                    "Verify module-null-sink is available in your sound server. "
                    "Try restarting PulseAudio/PipeWire and re-running this check."
                ),
            )
        )
        return CheckReport(sink_name=sink_name, module_id=None, steps=steps)

    module_id = _extract_module_id(stdout)
    if not module_id:
        steps.append(
            CheckStep(
                name="null_sink_create",
                ok=False,
                detail="pactl load-module did not return a module id.",
                suggestion=(
                    "Make sure pactl output is available and module-null-sink is loaded in the same process session."
                ),
            )
        )
        return CheckReport(sink_name=sink_name, module_id=None, steps=steps)

    steps.append(CheckStep(name="null_sink_create", ok=True, detail="ok"))

    try:
        steps.append(await _check_sink_registration(sink_name))
        if steps[-1].ok:
            ffmpeg_step, process = await _check_ffmpeg_monitor_open(sink_name)
            ffmpeg_process = process
            steps.append(ffmpeg_step)
    finally:
        ffmpeg_stop_ok = await _stop_process(ffmpeg_process)
        if module_id:
            unload_returncode, _, unload_stderr = await _run_command("pactl", "unload-module", module_id)
            cleanup_ok = unload_returncode == 0
            if not cleanup_ok:
                steps.append(
                    CheckStep(
                        name="cleanup",
                        ok=False,
                        detail=_decode_bytes(unload_stderr) or f"pactl unload-module exited with code {unload_returncode}",
                        suggestion=f"Run `pactl unload-module {module_id}` manually if needed.",
                    )
                )
            else:
                steps.append(CheckStep(name="cleanup", ok=True, detail="ok"))
            if not ffmpeg_stop_ok:
                for existing in steps:
                    if existing.name == "cleanup":
                        existing.ok = False
                        existing.detail = (existing.detail or "") + " ffmpeg process cleanup also failed."
                        break
                else:
                    steps.append(
                        CheckStep(
                            name="cleanup",
                            ok=False,
                            detail="ffmpeg cleanup failed.",
                            suggestion="Kill leftover ffmpeg processes started by this check.",
                        )
                    )
        else:
            steps.append(
                CheckStep(
                    name="cleanup",
                    ok=True,
                    detail="skipped (no module loaded).",
                )
            )

    return CheckReport(sink_name=sink_name, module_id=module_id, steps=steps)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Verify server_audio_sink runtime prerequisites for Orbit."
    )
    parser.add_argument(
        "--sink-name",
        help="Optional sink name to validate. Defaults to a unique Orbit test name.",
    )
    return parser


def _format_report(report: CheckReport) -> list[str]:
    lines: list[str] = []
    seen: set[str] = set()
    for step in report.steps:
        status = "ok" if step.ok else "fail"
        label = step.name
        if label in seen:
            label = f"{label} (final)"
        seen.add(label)
        lines.append(f"{label}: {status}")
        if step.detail and step.detail != status:
            lines.append(f"  {step.detail}")
        if (not step.ok) and step.suggestion:
            lines.append(f"  suggested fix: {step.suggestion}")
    return lines


async def main() -> int:
    args = build_parser().parse_args()
    report = await check_server_audio_sink_runtime(sink_name=args.sink_name)
    for line in _format_report(report):
        print(line)
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
