from __future__ import annotations

from orbit.agent.tools._shared import (
    ConfigurationError,
    _require_google_meet_url,
    _require_uuid,
)
from orbit.core import log
from orbit.whatsapp_service import OrbitWhatsAppService


async def enqueue_meeting_capture(
    meeting_id: str,
    *,
    gmeet_url: str,
    source_id: str | None = None,
    requested_by_person_id: str | None = None,
) -> None:
    meeting_id = _require_uuid(
        meeting_id,
        field_name="meeting_id",
        error_code="INVALID_MEETING_ID",
        required_message="Meeting id must be a valid UUID.",
    )

    gmeet_url = _require_google_meet_url(gmeet_url)

    log(
        f"Dispatching capture scheduling: meeting_id={meeting_id}, source_id={source_id}, requested_by_person_id={requested_by_person_id}",
        level="info",
    )

    service = OrbitWhatsAppService()
    result = await service.start_meeting_capture_session(
        meeting_id=meeting_id,
        meet_url=gmeet_url,
        source_id=source_id,
    )

    if result.get("status") != "started":
        status = str(result.get("status") or "unknown").lower()
        raise ConfigurationError(
            code="MEETING_CAPTURE_DISPATCH_REJECTED",
            message=f"Meeting capture could not be started now: {status}.",
        )
