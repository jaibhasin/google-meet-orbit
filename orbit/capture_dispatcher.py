from __future__ import annotations

from orbit.capture_service_registry import get_capture_service
from orbit.core import log
from orbit.whatsapp_service import OrbitWhatsAppService


async def enqueue_meeting_capture(
    meeting_id: str,
    *,
    gmeet_url: str,
    source_id: str | None = None,
    requested_by_person_id: str | None = None,
    capture_session_id: str | None = None,
) -> None:
    from orbit.agent.tools._shared import (
        ConfigurationError,
        _require_google_meet_url,
        _require_uuid,
    )

    meeting_id = _require_uuid(
        meeting_id,
        field_name="meeting_id",
        error_code="INVALID_MEETING_ID",
        required_message="Meeting id must be a valid UUID.",
    )

    gmeet_url = _require_google_meet_url(gmeet_url)
    if capture_session_id is not None:
        capture_session_id = _require_uuid(
            capture_session_id,
            field_name="capture_session_id",
            error_code="INVALID_CAPTURE_SESSION_ID",
            required_message="Capture session id must be a valid UUID.",
        )

    log(
        f"Dispatching capture scheduling: meeting_id={meeting_id}, source_id={source_id}, "
        f"capture_session_id={capture_session_id}, requested_by_person_id={requested_by_person_id}",
        level="info",
    )

    service = get_capture_service() or OrbitWhatsAppService()
    result = await service.start_meeting_capture_session(
        meeting_id=meeting_id,
        meet_url=gmeet_url,
        source_id=source_id,
        capture_session_id=capture_session_id,
    )

    if result.get("status") != "started":
        status = str(result.get("status") or "unknown").lower()
        raise ConfigurationError(
            code="MEETING_CAPTURE_DISPATCH_REJECTED",
            message=f"Meeting capture could not be started now: {status}.",
        )
