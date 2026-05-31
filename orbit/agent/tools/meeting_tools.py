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
from orbit.audio_capture import get_audio_capture_strategy
from orbit.core import log
from orbit.meeting_intelligence_repository import build_meeting_intelligence_repository
from orbit.meeting_intelligence_service import (
    MeetingIntelligenceService,
    MeetingNotFoundError,
)
from orbit.meeting_store import (
    DisabledMeetingStore,
    build_meeting_store,
    default_capture_session_metadata,
    merge_capture_session_metadata,
)


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
    capture_metadata = merge_capture_session_metadata(
        default_capture_session_metadata(),
        capture_session.get("metadata") if capture_session else None,
    )
    audio = capture_metadata["audio"]
    deepgram = capture_metadata["deepgram"]
    audio_capture = capture_metadata.get("audio_capture") or {}
    return {
        "meeting_id": meeting["id"],
        "status": meeting["status"],
        "meeting_status": meeting["status"],
        "capture_status": capture_session.get("status") if capture_session else None,
        "started_at": _to_iso_string(capture_started_at),
        "ended_at": _to_iso_string(capture_ended_at),
        "last_heartbeat_at": _to_iso_string(capture_session.get("last_heartbeat_at")) if capture_session else None,
        "error": capture_session.get("error_message") if capture_session else None,
        "audio_health": {
            "streaming_started": bool(audio.get("streaming_started")),
            "first_chunk_at": _to_iso_string(audio.get("first_chunk_at")),
            "last_chunk_at": _to_iso_string(audio.get("last_chunk_at")),
            "chunk_count": int(audio.get("chunk_count") or 0),
            "bytes_received": int(audio.get("bytes_received") or 0),
            "bytes_forwarded_to_stt": int(audio.get("bytes_forwarded_to_stt") or 0),
            "bytes_dropped_silence": int(audio.get("bytes_dropped_silence") or 0),
            "speech_chunk_count": int(audio.get("speech_chunk_count") or 0),
            "silent_chunk_count": int(audio.get("silent_chunk_count") or 0),
            "silence_gate_enabled": bool(audio.get("silence_gate_enabled")),
            "silence_gated": bool(audio.get("silence_gated")),
            "last_rms": float(audio.get("last_rms") or 0),
            "last_speech_at": _to_iso_string(audio.get("last_speech_at")),
            "last_silence_at": _to_iso_string(audio.get("last_silence_at")),
        },
        "stt_health": {
            "provider": capture_session.get("stt_provider") if capture_session else None,
            "connected_at": _to_iso_string(deepgram.get("connected_at")),
            "connection_closed_at": _to_iso_string(deepgram.get("connection_closed_at")),
            "last_transcript_at": _to_iso_string(deepgram.get("last_transcript_at")),
            "final_transcript_count": int(deepgram.get("final_transcript_count") or 0),
            "interim_transcript_count": int(deepgram.get("interim_transcript_count") or 0),
            "keepalive_count": int(deepgram.get("keepalive_count") or 0),
            "last_keepalive_at": _to_iso_string(deepgram.get("last_keepalive_at")),
        },
        "audio_capture": {
            "strategy": audio_capture.get("strategy"),
            "sink_name": audio_capture.get("sink_name"),
            "ffmpeg_pid": audio_capture.get("ffmpeg_pid"),
            "routing_mode": audio_capture.get("routing_mode"),
            "browser_audio_routed": audio_capture.get("browser_audio_routed"),
            "browser_process_isolated": audio_capture.get("browser_process_isolated"),
            "started_at": _to_iso_string(audio_capture.get("started_at")),
            "stopped_at": _to_iso_string(audio_capture.get("stopped_at")),
            "error": audio_capture.get("error"),
        },
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
        capture_strategy=get_audio_capture_strategy(),
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
