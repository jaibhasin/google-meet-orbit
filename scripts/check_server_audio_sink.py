#!/usr/bin/env python3

from __future__ import annotations

import asyncio
import sys

from orbit.server_audio_sink_check import main


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
