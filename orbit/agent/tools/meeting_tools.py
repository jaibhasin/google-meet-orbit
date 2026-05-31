from __future__ import annotations

from orbit.agent.tools._shared import (
    ConfigurationError,
    NotFoundError,
    _normalize_limit,
    _query_row,
    _query_rows,
    _require_database_url,
    _require_google_meet_url,
    _require_uuid,
    _to_iso_string,
)
from orbit.capture_dispatcher import enqueue_meeting_capture
from orbit.core import log
from orbit.meeting_intelligence_repository import build_meeting_intelligence_repository
from orbit.meeting_intelligence_service import (
    MeetingIntelligenceService,
    MeetingNotFoundError,
)
from orbit.meeting_store import DisabledMeetingStore, build_meeting_store


async def get_meeting_intelligence(meeting_id: str) -> dict:
    meeting_id = _require_uuid(
        meeting_id,
        field_name="meeting_id",
        error_code="INVALID_MEETING_ID",
        required_message="Meeting id must be a valid UUID.",
    )

    database_url = _require_database_url()
    repository = build_meeting_intelligence_repository(database_url)
    service = MeetingIntelligenceService(repository=repository)
    return await service.get_intelligence(meeting_id)


async def get_meeting_capture_status(meeting_id: str) -> dict:
    meeting_id = _require_uuid(
        meeting_id,
        field_name="meeting_id",
        error_code="INVALID_MEETING_ID",
        required_message="Meeting id must be a valid UUID.",
    )

    database_url = _require_database_url()
    store = build_meeting_store(database_url)
    meeting = await store.get_meeting_by_id(meeting_id)
    if not meeting:
        raise MeetingNotFoundError(
            code="MEETING_NOT_FOUND",
            message="Meeting not found.",
        )
    capture_session = await store.get_latest_capture_session_for_meeting(meeting_id)
    capture_started_at = capture_session.get("started_at") if capture_session else meeting.get("started_at")
    capture_ended_at = capture_session.get("ended_at") if capture_session else meeting.get("ended_at")
    return {
        "meeting_id": meeting["id"],
        "status": meeting["status"],
        "meeting_status": meeting["status"],
        "capture_status": capture_session.get("status") if capture_session else None,
        "started_at": _to_iso_string(capture_started_at),
        "ended_at": _to_iso_string(capture_ended_at),
        "last_heartbeat_at": _to_iso_string(capture_session.get("last_heartbeat_at")) if capture_session else None,
        "error": capture_session.get("error_message") if capture_session else None,
    }


async def request_meeting_capture(gmeet_url: str, requested_by_person_id: str) -> dict:
    gmeet_url = _require_google_meet_url(gmeet_url)
    requested_by_person_id = _require_uuid(
        requested_by_person_id,
        field_name="requested_by_person_id",
        error_code="INVALID_PERSON_ID",
        required_message="requested_by_person_id must be a valid UUID.",
    )

    database_url = _require_database_url()
    person = await _query_row(
        database_url,
        """
        SELECT id
        FROM people
        WHERE id = %s
        LIMIT 1
        """,
        (requested_by_person_id,),
    )
    if not person:
        raise NotFoundError(
            code="PERSON_NOT_FOUND",
            message="Requested person was not found.",
        )

    store = build_meeting_store(database_url)
    if isinstance(store, DisabledMeetingStore):
        raise ConfigurationError(
            code="MEETING_STORE_UNAVAILABLE",
            message="Meeting persistence store is unavailable.",
        )

    source_id = await store.create_source("gmeet", url=gmeet_url)
    if not source_id:
        raise ConfigurationError(
            code="MEETING_CAPTURE_CREATE_FAILED",
            message="Failed to create source record for the request.",
        )

    meeting_id = await store.create_meeting(
        gmeet_url=gmeet_url,
        source_id=source_id,
        status="created",
        requested_by_person_id=requested_by_person_id,
    )
    if not meeting_id:
        raise ConfigurationError(
            code="MEETING_CAPTURE_CREATE_FAILED",
            message="Failed to create meeting record for the request.",
        )

    capture_session = await store.create_capture_session(
        meeting_id,
        source_id,
        capture_strategy="chrome_extension",
        stt_provider="deepgram",
    )
    capture_session_id = capture_session.get("id") if capture_session else None
    if not capture_session_id:
        raise ConfigurationError(
            code="MEETING_CAPTURE_CREATE_FAILED",
            message="Failed to create capture session record for the request.",
        )

    log(
        f"Created meeting capture: meeting_id={meeting_id}, source_id={source_id}, "
        f"capture_session_id={capture_session_id}, requested_by_person_id={requested_by_person_id}",
        level="info",
    )

    try:
        await enqueue_meeting_capture(
            meeting_id,
            gmeet_url=gmeet_url,
            source_id=source_id,
            requested_by_person_id=requested_by_person_id,
            capture_session_id=capture_session_id,
        )
    except Exception:
        try:
            await store.update_meeting_status(meeting_id, "failed")
        except Exception as error:
            log(
                f"Failed to mark meeting as failed after dispatch failure. meeting_id={meeting_id}: {error}",
                level="error",
            )

        try:
            await store.mark_capture_session_failed(
                capture_session_id,
                "CAPTURE_DISPATCH_FAILED",
                "Meeting capture was created but could not be scheduled.",
            )
        except Exception as error:
            log(
                f"Failed to mark capture session as failed after dispatch failure. "
                f"capture_session_id={capture_session_id}: {error}",
                level="error",
            )

        log(
            f"Failed to dispatch capture job. meeting_id={meeting_id}, source_id={source_id}, "
            f"capture_session_id={capture_session_id}, requested_by_person_id={requested_by_person_id}",
            level="error",
        )
        raise ConfigurationError(
            code="MEETING_CAPTURE_DISPATCH_FAILED",
            message="Meeting capture was created but could not be scheduled. Please retry in a moment.",
        )

    return {
        "meeting_id": meeting_id,
        "capture_session_id": capture_session_id,
        "status": "created",
        "message": "Meeting capture created and scheduled.",
    }


async def get_recent_meetings(limit: int = 5, status: str | None = None) -> list[dict]:
    safe_limit = _normalize_limit(limit, default=5, maximum=20)

    normalized_status = (status or "").strip()

    conditions = []
    params: list[str | int] = []

    if normalized_status:
        conditions.append("status = %s")
        params.append(normalized_status.lower())

    where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""
    params.append(safe_limit)

    rows = await _query_rows(
        _require_database_url(),
        f"""
        SELECT
            id,
            status,
            started_at,
            ended_at,
            summary_short,
            created_at
        FROM meetings
        {where_clause}
        ORDER BY created_at DESC
        LIMIT %s
        """,
        tuple(params),
    )

    return [
        {
            "meeting_id": row["id"],
            "title": None,
            "status": row["status"],
            "started_at": _to_iso_string(row.get("started_at")),
            "ended_at": _to_iso_string(row.get("ended_at")),
            "summary_short": row.get("summary_short"),
        }
        for row in rows
    ]
