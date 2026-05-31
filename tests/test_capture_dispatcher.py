from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

from orbit.agent.tools.meeting_tools import enqueue_meeting_capture


VALID_MEETING_ID = "123e4567-e89b-12d3-a456-426614174000"
VALID_CAPTURE_SESSION_ID = "223e4567-e89b-12d3-a456-426614174001"


class CaptureDispatcherTests(unittest.IsolatedAsyncioTestCase):
    async def test_enqueue_accepts_native_uuid_ids(self):
        service = MagicMock()
        service.start_meeting_capture_session = AsyncMock(return_value={"status": "started"})

        with patch("orbit.capture_dispatcher.OrbitWhatsAppService", return_value=service):
            await enqueue_meeting_capture(
                UUID(VALID_MEETING_ID),
                gmeet_url="https://meet.google.com/abc-defg-hij",
                capture_session_id=UUID(VALID_CAPTURE_SESSION_ID),
            )

        service.start_meeting_capture_session.assert_awaited_once_with(
            meeting_id=VALID_MEETING_ID,
            meet_url="https://meet.google.com/abc-defg-hij",
            source_id=None,
            capture_session_id=VALID_CAPTURE_SESSION_ID,
        )
