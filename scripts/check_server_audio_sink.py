#!/usr/bin/env python3

from __future__ import annotations

import asyncio
import platform
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from orbit.server_audio_sink_check import DARWIN_UNSUPPORTED_MESSAGE, main


if __name__ == "__main__":
    if platform.system() == "Darwin":
        print(DARWIN_UNSUPPORTED_MESSAGE)
        sys.exit(1)
    sys.exit(asyncio.run(main()))
