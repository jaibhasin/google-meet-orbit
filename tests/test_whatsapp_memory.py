from __future__ import annotations

import asyncio
import struct
import unittest
import sys
import types
from unittest.mock import AsyncMock, patch


if "twilio" not in sys.modules:
    twilio_module = types.ModuleType("twilio")
    twilio_rest_module = types.ModuleType("twilio.rest")
    twilio_twiml_module = types.ModuleType("twilio.twiml")
    twilio_messaging_module = types.ModuleType("twilio.twiml.messaging_response")

    class MessagingResponse:
        def __init__(self, *args, **kwargs):
            self._value = ""

        def message(self, body=None):
            if body is not None:
                self._value = body
            return self._value

        def __str__(self):
            return str(self._value)

    twilio_rest_module.Client = object
    twilio_messaging_module.MessagingResponse = MessagingResponse
    twilio_module.rest = twilio_rest_module
    twilio_module.twiml = twilio_twiml_module
    twilio_twiml_module.messaging_response = twilio_messaging_module

    sys.modules["twilio"] = twilio_module
    sys.modules["twilio.rest"] = twilio_rest_module
    sys.modules["twilio.twiml"] = twilio_twiml_module
    sys.modules["twilio.twiml.messaging_response"] = twilio_messaging_module

from orbit.meet_types import ChatMessage, MeetingState
from orbit.meeting_store import merge_capture_session_metadata
from orbit.memory import MemoryAnswer, MemorySource
from orbit.transcript import TranscriptSegment
from orbit.whatsapp_service import (
    CAPTURE_AUDIO_METADATA_FLUSH_CHUNKS,
    ActiveMeeting,
    OrbitWhatsAppService,
)


class FakeMemory:
    def __init__(self, answer=None):
        self.recorded = []
        self.transcripts = []
        self.finalized = []
        self.questions = []
        self.answer = answer or MemoryAnswer(
            answer="The launch date discussed was Friday.",
            sources=[
                MemorySource(
                    label="Meet abc-defg-hij / Priya / 10:05",
                    source_type="meet_chat",
                    meeting_code="abc-defg-hij",
                    author="Priya",
                    timestamp_text="10:05",
                )
            ],
        )

    async def record_meeting_chat(self, state, message):
        self.recorded.append((state, message))

    async def record_transcript_segments(self, state, segments):
        self.transcripts.append((state, segments))

    async def finalize_meeting(self, state):
        self.finalized.append(state)

    async def search_memory(self, query):
        return []

    async def answer_from_memory(self, question):
        self.questions.append(question)
        return self.answer


class FakeMessage:
    def __init__(self, content):
        self.content = content


class FakeChoice:
    def __init__(self, content):
        self.message = FakeMessage(content)


class FakeResponse:
    def __init__(self, content):
        self.choices = [FakeChoice(content)]


class FakeMeetingStore:
    def __init__(self):
        self.people = []
        self.sources = []
        self.meetings = []
        self.updates = []
        self.saved_chunks = []
        self.transcript_save_calls = []
        self.fail_save_chunks = False
        self.extraction_runs = []
        self.decisions = []
        self.action_items = []
        self.memories = []
        self.source_chunks_for_id = {}
        self.meetings_lookup = {}
        self.capture_session_updates = []
        self.capture_session_metadata_updates = []
        self.capture_session_metadata = {}
        self.capture_session_heartbeats = []
        self.failed_capture_sessions = []
        self.finished_capture_sessions = []

    async def find_or_create_person_by_phone(self, phone, name=None):
        self.people.append((phone, name))
        return "person-1"

    async def create_source(
        self,
        source_type,
        *,
        url=None,
        title=None,
        raw_text=None,
        raw_payload=None,
    ):
        self.sources.append(
            {
                "source_type": source_type,
                "url": url,
                "title": title,
                "raw_text": raw_text,
                "raw_payload": raw_payload,
            }
        )
        return "source-1"

    async def create_meeting(
        self,
        gmeet_url,
        *,
        source_id,
        status,
        requested_by_person_id=None,
        summary_short=None,
        summary_long=None,
        started_at=None,
        ended_at=None,
    ):
        self.meetings.append(
            {
                "id": "meeting-1",
                "gmeet_url": gmeet_url,
                "source_id": source_id,
                "status": status,
                "requested_by_person_id": requested_by_person_id,
                "summary_short": summary_short,
                "summary_long": summary_long,
                "started_at": started_at,
                "ended_at": ended_at,
            }
        )
        self.meetings_lookup["meeting-1"] = self.meetings[-1]
        return "meeting-1"

    async def update_meeting_status(self, meeting_id, status, **kwargs):
        self.updates.append({"meeting_id": meeting_id, "status": status, "fields": kwargs})

    async def update_capture_session_status(self, capture_session_id, status, metadata=None):
        self.capture_session_updates.append(
            {
                "capture_session_id": capture_session_id,
                "status": status,
                "metadata": metadata,
            }
        )
        return self.capture_session_updates[-1]

    async def heartbeat_capture_session(self, capture_session_id):
        self.capture_session_heartbeats.append(capture_session_id)

    async def update_capture_session_metadata(self, capture_session_id, patch, merge=True):
        self.capture_session_metadata_updates.append(
            {
                "capture_session_id": capture_session_id,
                "patch": patch,
                "merge": merge,
            }
        )
        self.capture_session_metadata = merge_capture_session_metadata(
            self.capture_session_metadata if merge else {},
            patch,
        )
        return {
            "capture_session_id": capture_session_id,
            "metadata": self.capture_session_metadata,
        }

    async def mark_capture_session_failed(
        self,
        capture_session_id,
        error_code,
        error_message,
        metadata=None,
    ):
        self.failed_capture_sessions.append(
            {
                "capture_session_id": capture_session_id,
                "status": "failed",
                "error_code": error_code,
                "error_message": error_message,
                "metadata": metadata,
            }
        )
        return self.failed_capture_sessions[-1]

    async def mark_capture_session_finished(self, capture_session_id):
        self.finished_capture_sessions.append(capture_session_id)
        return {"capture_session_id": capture_session_id, "status": "processed"}

    async def save_transcript_chunks(self, source_id, chunks):
        self.transcript_save_calls.append((source_id, chunks))
        if self.fail_save_chunks:
            raise RuntimeError("transcript persistence failure")
        self.saved_chunks.append((source_id, chunks))
        return len(chunks)

    async def saveTranscriptChunks(self, payload):
        source_id = payload["sourceId"]
        chunks = payload["chunks"]
        return await self.save_transcript_chunks(source_id, chunks)

    async def get_source_chunks_by_source_id(self, source_id):
        return list(self.source_chunks_for_id.get(source_id, []))

    async def getSourceChunksBySourceId(self, source_id):
        return await self.get_source_chunks_by_source_id(source_id)

    async def create_extraction_run(
        self,
        *,
        source_id=None,
        meeting_id=None,
        run_type=None,
        model=None,
        prompt_version=None,
        output_json=None,
        status=None,
        error=None,
    ):
        run_id = f"extract-{len(self.extraction_runs) + 1}"
        self.extraction_runs.append(
            {
                "source_id": source_id,
                "meeting_id": meeting_id,
                "run_type": run_type,
                "model": model,
                "prompt_version": prompt_version,
                "output_json": output_json,
                "status": status,
                "error": error,
            }
        )
        return run_id

    async def createExtractionRun(self, payload):
        return await self.create_extraction_run(
            source_id=payload.get("sourceId") or payload.get("source_id"),
            meeting_id=payload.get("meetingId") or payload.get("meeting_id"),
            run_type=payload.get("runType") or payload.get("run_type"),
            model=payload.get("model"),
            prompt_version=payload.get("promptVersion") or payload.get("prompt_version"),
            output_json=payload.get("outputJson") if "outputJson" in payload else payload.get("output_json"),
            status=payload.get("status"),
            error=payload.get("error"),
        )

    async def create_decision(
        self,
        *,
        meeting_id=None,
        source_id=None,
        title=None,
        decision_text=None,
        rationale=None,
        owner_text=None,
        confidence=None,
    ):
        if not meeting_id or not source_id:
            return None

        if not decision_text:
            return None

        decision_id = f"decision-{len(self.decisions) + 1}"
        self.decisions.append(
            {
                "id": decision_id,
                "meeting_id": meeting_id,
                "source_id": source_id,
                "title": title,
                "decision_text": decision_text,
                "rationale": rationale,
                "owner_text": owner_text,
                "confidence": confidence,
            }
        )
        return decision_id

    async def createDecision(self, payload):
        return await self.create_decision(
            meeting_id=payload.get("meetingId") or payload.get("meeting_id"),
            source_id=payload.get("sourceId") or payload.get("source_id"),
            title=payload.get("title"),
            decision_text=payload.get("decisionText") or payload.get("decision_text"),
            rationale=payload.get("rationale"),
            owner_text=payload.get("ownerText") or payload.get("owner_text"),
            confidence=payload.get("confidence"),
        )

    async def createDecisionsFromExtraction(
        self,
        *,
        meeting_id=None,
        source_id=None,
        decisions=None,
    ):
        # Idempotent behavior expected by extraction flow.
        self.decisions = [
            decision
            for decision in self.decisions
            if decision.get("meeting_id") != meeting_id
        ]

        if not isinstance(decisions, list):
            return 0

        inserted = 0
        for decision in decisions:
            decision_text = (
                (decision.get("decisionText") or "").strip()
                if isinstance(decision, dict)
                else ""
            )
            if not decision_text:
                decision_text = (
                    (decision.get("decision_text") or "").strip()
                    if isinstance(decision, dict)
                    else ""
                )
            if not decision_text:
                decision_text = (
                    (decision.get("decision") or "").strip()
                    if isinstance(decision, dict)
                    else ""
                )
            if not decision_text:
                decision_text = (
                    (decision.get("text") or "").strip()
                    if isinstance(decision, dict)
                    else ""
                )
            if not decision_text:
                continue

            await self.create_decision(
                meeting_id=meeting_id,
                source_id=source_id,
                title=(decision.get("title") or "").strip() if isinstance(decision, dict) else None,
                decision_text=decision_text,
                rationale=(decision.get("rationale") or "").strip()
                if isinstance(decision, dict) and decision.get("rationale") is not None
                else None,
                owner_text=(decision.get("ownerText") or decision.get("owner_text") or "").strip()
                if isinstance(decision, dict)
                and (decision.get("ownerText") or decision.get("owner_text") or decision.get("owner")) is not None
                else None,
                confidence=decision.get("confidence") if isinstance(decision, dict) else None,
            )
            inserted += 1

        return inserted

    async def create_action_item(
        self,
        *,
        meeting_id=None,
        source_id=None,
        task=None,
        owner_text=None,
        due_date=None,
        status=None,
        confidence=None,
    ):
        if not meeting_id or not source_id:
            return None

        if not task:
            return None

        action_id = f"action-{len(self.action_items) + 1}"
        self.action_items.append(
            {
                "id": action_id,
                "meeting_id": meeting_id,
                "source_id": source_id,
                "task": task,
                "owner_text": owner_text,
                "due_date": due_date,
                "status": status,
                "confidence": confidence,
            }
        )
        return action_id

    async def createActionItem(self, payload):
        return await self.create_action_item(
            meeting_id=payload.get("meetingId") or payload.get("meeting_id"),
            source_id=payload.get("sourceId") or payload.get("source_id"),
            task=payload.get("task") or payload.get("task_text") or payload.get("text"),
            owner_text=payload.get("ownerText") or payload.get("owner_text") or payload.get("owner"),
            due_date=payload.get("dueDate") or payload.get("due_date"),
            status=payload.get("status", "open"),
            confidence=payload.get("confidence"),
        )

    async def createActionItemsFromExtraction(
        self,
        *,
        meeting_id=None,
        source_id=None,
        action_items=None,
    ):
        self.action_items = [
            item
            for item in self.action_items
            if item.get("meeting_id") != meeting_id
        ]

        if not isinstance(action_items, list):
            return 0

        inserted = 0
        for item in action_items:
            task = (
                (item.get("task") or item.get("task_text") or item.get("taskText") or "").strip()
                if isinstance(item, dict)
                else ""
            )
            if not task:
                continue

            await self.create_action_item(
                meeting_id=meeting_id,
                source_id=source_id,
                task=task,
                owner_text=(item.get("ownerText") or item.get("owner_text") or item.get("owner") or "").strip()
                if isinstance(item, dict)
                and (item.get("ownerText") or item.get("owner_text") or item.get("owner")) is not None
                else None,
                due_date=(item.get("dueDate") or item.get("due_date") or "").strip()
                if isinstance(item, dict)
                and (item.get("dueDate") or item.get("due_date")) is not None
                else None,
                status=(item.get("status") or "open") if isinstance(item, dict) else "open",
                confidence=item.get("confidence") if isinstance(item, dict) else None,
            )
            inserted += 1

        return inserted

    async def create_memory(
        self,
        *,
        meeting_id=None,
        source_id=None,
        memory_type=None,
        content=None,
        importance=None,
        confidence=None,
    ):
        if not meeting_id or not source_id:
            return None

        if not content:
            return None

        memory_id = f"memory-{len(self.memories) + 1}"
        self.memories.append(
            {
                "id": memory_id,
                "meeting_id": meeting_id,
                "source_id": source_id,
                "memory_type": memory_type,
                "content": content,
                "importance": importance,
                "confidence": confidence,
            }
        )
        return memory_id

    async def createMemory(self, payload):
        return await self.create_memory(
            meeting_id=payload.get("meetingId") or payload.get("meeting_id"),
            source_id=payload.get("sourceId") or payload.get("source_id"),
            memory_type=payload.get("memoryType") or payload.get("memory_type"),
            content=payload.get("content"),
            importance=payload.get("importance"),
            confidence=payload.get("confidence"),
        )

    async def createMemoriesFromExtraction(
        self,
        *,
        meeting_id=None,
        source_id=None,
        memories=None,
    ):
        self.memories = [
            memory
            for memory in self.memories
            if memory.get("meeting_id") != meeting_id
        ]

        if not isinstance(memories, list):
            return 0

        inserted = 0
        for memory in memories:
            memory_content = (
                memory.get("content") if isinstance(memory, dict) else None
            )
            if not memory_content or not str(memory_content).strip():
                # Legacy payloads may use different keys; keep this simple and
                # strict for tests.
                continue

            memory_type = (
                memory.get("memoryType") or memory.get("memory_type") or "important_fact"
            )
            importance = memory.get("importance") or "medium"
            confidence = memory.get("confidence")

            if isinstance(importance, str):
                importance = importance.lower()
                if importance not in {"low", "medium", "high"}:
                    importance = "medium"
            else:
                importance = str(importance)
                if importance not in {"low", "medium", "high"}:
                    importance = "medium"

            await self.create_memory(
                meeting_id=meeting_id,
                source_id=source_id,
                memory_type=memory_type,
                content=(str(memory_content).strip()),
                importance=importance,
                confidence=confidence,
            )
            inserted += 1

        return inserted

    async def get_memories_by_meeting_id(self, meeting_id):
        return [memory for memory in self.memories if memory.get("meeting_id") == meeting_id]

    async def getMemoriesByMeetingId(self, meeting_id):
        return await self.get_memories_by_meeting_id(meeting_id)

    async def get_recent_memories(self, limit=20):
        return list(reversed(self.memories))[:limit]

    async def getRecentMemories(self, limit=20):
        return await self.get_recent_memories(limit=limit)

    async def get_memories_by_type(self, memory_type, limit=20):
        if not memory_type:
            return []
        filtered = [
            memory
            for memory in self.memories
            if memory.get("memory_type") == memory_type
        ]
        return list(reversed(filtered))[:limit]

    async def getMemoriesByType(self, memory_type, limit=20):
        return await self.get_memories_by_type(memory_type, limit=limit)

    async def get_action_items_by_meeting_id(self, meeting_id):
        return [item for item in self.action_items if item.get("meeting_id") == meeting_id]

    async def getActionItemsByMeetingId(self, meeting_id):
        return await self.get_action_items_by_meeting_id(meeting_id)

    async def get_recent_action_items(self, limit=20):
        return list(reversed(self.action_items))[:limit]

    async def getRecentActionItems(self, limit=20):
        return await self.get_recent_action_items(limit=limit)

    async def get_decisions_by_meeting_id(self, meeting_id):
        return [decision for decision in self.decisions if decision.get("meeting_id") == meeting_id]

    async def getDecisionsByMeetingId(self, meeting_id):
        return await self.get_decisions_by_meeting_id(meeting_id)

    async def get_recent_decisions(self, limit=20):
        return list(reversed(self.decisions))[:limit]

    async def getRecentDecisions(self, limit=20):
        return await self.get_recent_decisions(limit=limit)

    async def get_meeting_by_id(self, meeting_id):
        meeting = self.meetings_lookup.get(meeting_id)
        if meeting:
            return meeting
        if self.meetings:
            for created in self.meetings:
                if created.get("id") == meeting_id:
                    return created
        return None


class FakeCompletions:
    def __init__(self, responses=None):
        self.responses = list(responses or [])
        self.calls = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.responses:
            return FakeResponse(self.responses.pop(0))
        return FakeResponse("General answer from Orbit.")


class FakeChat:
    def __init__(self, responses=None):
        self.completions = FakeCompletions(responses=responses)


class FakeOpenAIClient:
    def __init__(self, responses=None):
        self.chat = FakeChat(responses=responses)


class FakeLiveSTT:
    def __init__(self):
        self.available = True
        self.sessions = []
        self.stopped = []

    async def add_captions(self, state, captions):
        return None

    async def get_or_create(self, state, audio_format=None):
        session = FakeLiveSTTSession()
        self.sessions.append((state, audio_format, session))
        return session

    async def stop(self, session_id):
        self.stopped.append(session_id)
        return None


class FakeLiveSTTSession:
    def __init__(self):
        self.audio_chunks = []
        self.keepalives = 0

    async def send_audio(self, chunk):
        self.audio_chunks.append(chunk)

    async def send_keepalive(self):
        self.keepalives += 1
        return True


class FakeWebSocket:
    def __init__(self, messages, query_params=None):
        self.messages = list(messages)
        self.query_params = query_params or {}
        self.accepted = False
        self.sent_json = []
        self.closed = None

    async def accept(self):
        self.accepted = True

    async def close(self, code=1000, reason=""):
        self.closed = (code, reason)

    async def receive(self):
        if not self.messages:
            raise RuntimeError("no more messages")
        return self.messages.pop(0)

    async def send_json(self, payload):
        self.sent_json.append(payload)


class FakeServerAudioSinkProcess:
    def __init__(self, pid=0, returncode=0):
        self.pid = pid
        self.returncode = returncode
        self.returncode_set = returncode
        self.wait_calls = 0

    async def wait(self):
        self.wait_calls += 1
        return self.returncode_set


class FakeServerAudioSinkHandle:
    def __init__(self, session_id, capture_session_id, sink_name, pid=12345):
        self.session_id = session_id
        self.capture_session_id = capture_session_id
        self.sink_name = sink_name
        self.module_id = f"mod-{session_id}"
        self.ffmpeg_process = FakeServerAudioSinkProcess(pid=pid)
        self.stop_calls = 0

    async def stop(self):
        self.stop_calls += 1


class FakeStdout:
    def __init__(self, chunks):
        self._chunks = list(chunks)

    async def read(self, _size):
        if not self._chunks:
            return b""
        return self._chunks.pop(0)


def pcm16_chunk(amplitude, sample_count=1600):
    return struct.pack(f"<{sample_count}h", *([amplitude] * sample_count))


def build_service(memory=None, meeting_store=None):
    service = OrbitWhatsAppService.__new__(OrbitWhatsAppService)
    service.twilio_allowed_from = "whatsapp:+15551234567"
    service.model_name = "test-model"
    service.openai_client = FakeOpenAIClient()
    service.max_parallel_meetings = 3
    service.active_sessions = {}
    service.lock = asyncio.Lock()
    service.memory = memory or FakeMemory()
    service.meeting_store = meeting_store or FakeMeetingStore()
    service.live_stt = FakeLiveSTT()
    return service


class WhatsAppMemoryTests(unittest.IsolatedAsyncioTestCase):
    async def test_normal_question_uses_memory_answer(self):
        service = build_service()

        xml = await service.handle_incoming_message(
            "whatsapp:+15551234567",
            "what is the launch date?",
        )

        self.assertIn("Answer mode: memory-backed recall", xml)
        self.assertIn("The launch date discussed was Friday.", xml)
        self.assertIn("Sources:", xml)
        self.assertEqual(service.memory.questions, ["what is the launch date?"])
        self.assertEqual(service.openai_client.chat.completions.calls, [])

    async def test_normal_question_falls_back_to_general_answer_when_memory_is_empty(self):
        memory = FakeMemory(
            MemoryAnswer(
                "I do not have enough company memory yet to answer that.",
                mode="insufficient_memory",
            )
        )
        service = build_service(memory)

        xml = await service.handle_incoming_message(
            "whatsapp:+15551234567",
            "what is product market fit?",
        )

        self.assertIn("Answer mode: general fallback", xml)
        self.assertIn("This answer is not based on stored company memory.", xml)
        self.assertIn("General answer from Orbit.", xml)
        self.assertEqual(memory.questions, ["what is product market fit?"])
        self.assertEqual(len(service.openai_client.chat.completions.calls), 1)

    async def test_meet_link_still_starts_session_path(self):
        service = build_service()
        service.dialogue_history = [
            type("Turn", (), {"inbound": "old", "reply": "old reply"})()
        ]

        async def fake_start(meet_links, **kwargs):
            return f"started {len(meet_links)}"

        service.start_meeting_sessions = fake_start

        xml = await service.handle_incoming_message(
            "whatsapp:+15551234567",
            "join https://meet.google.com/abc-defg-hij",
        )

        self.assertIn("started 1", xml)
        self.assertEqual(service.memory.questions, [])
        self.assertEqual(len(service.dialogue_history), 1)
        self.assertEqual(service.dialogue_history[0].inbound, "join https://meet.google.com/abc-defg-hij")

    async def test_start_single_meeting_session_persists_people_source_and_meeting(self):
        store = FakeMeetingStore()
        service = build_service(memory=FakeMemory(), meeting_store=store)
        result = await service.start_single_meeting_session(
            "https://meet.google.com/abc-defg-hij",
            from_number="whatsapp:+15551234567",
        )

        self.assertEqual(result["status"], "started")
        self.assertEqual(store.people, [("+15551234567", None)])
        self.assertEqual(store.sources[0]["url"], "https://meet.google.com/abc-defg-hij")
        self.assertEqual(store.meetings[0]["status"], "joining")
        self.assertEqual(store.meetings[0]["requested_by_person_id"], "person-1")
        self.assertEqual(store.meetings[0]["gmeet_url"], "https://meet.google.com/abc-defg-hij")

    async def test_session_status_updates_persistent_meeting_status(self):
        store = FakeMeetingStore()
        service = build_service(meeting_store=store)
        state = MeetingState(
            session_id="session-1",
            meet_url="https://meet.google.com/abc-defg-hij",
            meeting_code="abc-defg-hij",
            display_name="Orbit",
        )
        service.active_sessions[state.session_id] = ActiveMeeting(
            session_id=state.session_id,
            meet_url=state.meet_url,
            state=state,
            meeting_id="meeting-1",
        )

        await service.handle_session_status(state, "starting_join", "opening")
        await service.handle_session_status(state, "joined", "joined")

        self.assertEqual(store.updates[0]["status"], "joining")
        self.assertEqual(store.updates[1]["status"], "live")

    async def test_capture_session_tracks_start_join_live_and_failure(self):
        store = FakeMeetingStore()
        service = build_service(meeting_store=store)
        state = MeetingState(
            session_id="session-1",
            meet_url="https://meet.google.com/abc-defg-hij",
            meeting_code="abc-defg-hij",
            display_name="Orbit",
        )
        active = ActiveMeeting(
            session_id=state.session_id,
            meet_url=state.meet_url,
            state=state,
            meeting_id="meeting-1",
            capture_session_id="capture-1",
        )
        service.active_sessions[state.session_id] = active

        with patch("orbit.whatsapp_service.run_meeting_session", new_callable=AsyncMock):
            await service._run_session(
                active,
                types.SimpleNamespace(live_stt_enabled=False),
            )

        self.assertEqual(store.capture_session_updates[0]["status"], "starting")

        service.active_sessions[state.session_id] = active
        await service.handle_session_status(state, "starting_join", "opening")
        await service.handle_session_status(state, "joined", "joined")
        await service.handle_session_status(state, "join_denied", "denied")

        self.assertEqual(
            [update["status"] for update in store.capture_session_updates],
            ["starting", "joining", "live"],
        )
        self.assertEqual(store.failed_capture_sessions[-1]["error_code"], "JOIN_DENIED")

    async def test_run_session_starts_server_audio_sink_when_configured(self):
        store = FakeMeetingStore()
        service = build_service(meeting_store=store)
        state = MeetingState(
            session_id="session-a",
            meet_url="https://meet.google.com/abc-defg-hij",
            meeting_code="abc-defg-hij",
            display_name="Orbit",
        )
        active = ActiveMeeting(
            session_id=state.session_id,
            meet_url=state.meet_url,
            state=state,
            capture_session_id="capture-a",
        )
        service.active_sessions[state.session_id] = active

        fake_handle = FakeServerAudioSinkHandle(
            session_id="session-a",
            capture_session_id="capture-a",
            sink_name="orbit_meet_session-a",
            pid=4001,
        )

        with patch(
            "orbit.whatsapp_service.get_audio_capture_strategy",
            return_value="server_audio_sink",
        ), patch(
            "orbit.whatsapp_service.start_server_audio_sink_capture",
            new_callable=AsyncMock,
            return_value=fake_handle,
        ) as start_capture, patch("orbit.whatsapp_service.run_meeting_session", new_callable=AsyncMock):
            await service._run_session(
                active,
                types.SimpleNamespace(live_stt_enabled=True),
            )

        start_capture.assert_awaited_once_with("session-a", "capture-a")
        self.assertIsNone(active.server_audio_sink_handle)
        self.assertEqual(fake_handle.stop_calls, 1)
        self.assertEqual(
            store.capture_session_metadata["audio_capture"]["strategy"],
            "server_audio_sink",
        )
        self.assertEqual(
            store.capture_session_metadata["audio_capture"]["sink_name"],
            "orbit_meet_session-a",
        )
        self.assertEqual(
            store.capture_session_metadata["audio_capture"]["ffmpeg_pid"],
            4001,
        )
        self.assertIn("stopped_at", store.capture_session_metadata["audio_capture"])

    async def test_run_session_keeps_chrome_extension_behavior_by_default(self):
        store = FakeMeetingStore()
        service = build_service(meeting_store=store)
        state = MeetingState(
            session_id="session-b",
            meet_url="https://meet.google.com/abc-defg-hij",
            meeting_code="abc-defg-hij",
            display_name="Orbit",
        )
        active = ActiveMeeting(
            session_id=state.session_id,
            meet_url=state.meet_url,
            state=state,
            capture_session_id="capture-b",
        )
        service.active_sessions[state.session_id] = active

        with patch(
            "orbit.whatsapp_service.get_audio_capture_strategy",
            return_value="chrome_extension",
        ), patch(
            "orbit.whatsapp_service.start_server_audio_sink_capture",
            new_callable=AsyncMock,
        ) as start_capture, patch(
            "orbit.whatsapp_service.run_meeting_session",
            new_callable=AsyncMock,
        ):
            await service._run_session(
                active,
                types.SimpleNamespace(live_stt_enabled=True),
            )

        start_capture.assert_not_awaited()

    async def test_run_session_marks_capture_failed_when_server_audio_sink_fails_to_start(self):
        store = FakeMeetingStore()
        service = build_service(meeting_store=store)
        state = MeetingState(
            session_id="session-c",
            meet_url="https://meet.google.com/abc-defg-hij",
            meeting_code="abc-defg-hij",
            display_name="Orbit",
        )
        active = ActiveMeeting(
            session_id=state.session_id,
            meet_url=state.meet_url,
            state=state,
            capture_session_id="capture-c",
        )
        service.active_sessions[state.session_id] = active

        with patch(
            "orbit.whatsapp_service.get_audio_capture_strategy",
            return_value="server_audio_sink",
        ), patch(
            "orbit.whatsapp_service.start_server_audio_sink_capture",
            new_callable=AsyncMock,
            side_effect=RuntimeError("pactl failed to create sink"),
        ), patch("orbit.whatsapp_service.run_meeting_session", new_callable=AsyncMock):
            await service._run_session(
                active,
                types.SimpleNamespace(live_stt_enabled=True),
            )

        failure = store.failed_capture_sessions[-1]
        self.assertEqual(failure["error_code"], "AUDIO_SINK_CREATE_FAILED")
        self.assertIn("Could not start server-side audio sink capture.", failure["error_message"])

    async def test_server_audio_sink_reader_forwards_ffmpeg_audio_to_shared_stt_handler(self):
        store = FakeMeetingStore()
        service = build_service(meeting_store=store)
        state = MeetingState(
            session_id="session-d",
            meet_url="https://meet.google.com/abc-defg-hij",
            meeting_code="abc-defg-hij",
            display_name="Orbit",
        )
        active = ActiveMeeting(
            session_id=state.session_id,
            meet_url=state.meet_url,
            state=state,
            capture_session_id="capture-d",
        )
        process = FakeServerAudioSinkProcess(pid=51234, returncode=0)
        process.stdout = FakeStdout([pcm16_chunk(1200), b""])
        active.server_audio_sink_handle = FakeServerAudioSinkHandle(
            session_id=state.session_id,
            capture_session_id=active.capture_session_id,
            sink_name="orbit_meet_session_d",
            pid=process.pid,
        )
        active.server_audio_sink_handle.ffmpeg_process = process
        service.active_sessions[state.session_id] = active

        await service._run_server_audio_sink_reader(active)

        self.assertTrue(state.live_stt_started)
        self.assertIsNotNone(service.live_stt.sessions[-1][1])
        fake_session = service.live_stt.sessions[-1][2]
        self.assertEqual(fake_session.audio_chunks, [pcm16_chunk(1200)])
        self.assertEqual(store.capture_session_updates[-1]["status"], "streaming_audio")

    async def test_server_audio_sink_reader_marks_failed_when_only_empty_chunks_seen(self):
        store = FakeMeetingStore()
        service = build_service(meeting_store=store)
        state = MeetingState(
            session_id="session-e",
            meet_url="https://meet.google.com/abc-defg-hij",
            meeting_code="abc-defg-hij",
            display_name="Orbit",
        )
        active = ActiveMeeting(
            session_id=state.session_id,
            meet_url=state.meet_url,
            state=state,
            capture_session_id="capture-e",
        )
        process = FakeServerAudioSinkProcess(pid=51235, returncode=0)
        process.stdout = FakeStdout([b"", b""])
        handle = FakeServerAudioSinkHandle(
            session_id=state.session_id,
            capture_session_id=active.capture_session_id,
            sink_name="orbit_meet_session_e",
            pid=process.pid,
        )
        handle.ffmpeg_process = process
        active.server_audio_sink_handle = handle

        await service._run_server_audio_sink_reader(active)

        self.assertFalse(state.live_stt_started)
        self.assertEqual(store.failed_capture_sessions[-1]["error_code"], "NO_AUDIO_FROM_SINK")

    async def test_server_audio_sink_cleanup_is_idempotent(self):
        store = FakeMeetingStore()
        service = build_service(meeting_store=store)
        state = MeetingState(
            session_id="session-f",
            meet_url="https://meet.google.com/abc-defg-hij",
            meeting_code="abc-defg-hij",
            display_name="Orbit",
        )
        handle = FakeServerAudioSinkHandle(
            session_id="session-f",
            capture_session_id="capture-f",
            sink_name="orbit_meet_session_f",
            pid=51236,
        )
        active = ActiveMeeting(
            session_id=state.session_id,
            meet_url=state.meet_url,
            state=state,
            capture_session_id="capture-f",
            server_audio_sink_handle=handle,
        )

        await service._stop_server_audio_sink_capture(active)
        await service._stop_server_audio_sink_capture(active)
        self.assertEqual(handle.stop_calls, 1)
        self.assertIsNone(active.server_audio_sink_handle)
        self.assertIn("stopped_at", store.capture_session_metadata["audio_capture"])

    async def test_two_server_audio_sink_handles_do_not_share_state(self):
        store = FakeMeetingStore()
        service = build_service(meeting_store=store)
        state_one = MeetingState(
            session_id="session-g",
            meet_url="https://meet.google.com/abc-defg-hij",
            meeting_code="abc-defg-hij",
            display_name="Orbit",
        )
        state_two = MeetingState(
            session_id="session-h",
            meet_url="https://meet.google.com/klm-nopq-rst",
            meeting_code="klm-nopq-rst",
            display_name="Orbit",
        )
        active_one = ActiveMeeting(
            session_id=state_one.session_id,
            meet_url=state_one.meet_url,
            state=state_one,
            capture_session_id="capture-g",
        )
        active_two = ActiveMeeting(
            session_id=state_two.session_id,
            meet_url=state_two.meet_url,
            state=state_two,
            capture_session_id="capture-h",
        )
        handle_one = FakeServerAudioSinkHandle(
            session_id="session-g",
            capture_session_id="capture-g",
            sink_name="orbit_meet_session_g",
            pid=1001,
        )
        handle_two = FakeServerAudioSinkHandle(
            session_id="session-h",
            capture_session_id="capture-h",
            sink_name="orbit_meet_session_h",
            pid=1002,
        )

        with patch(
            "orbit.whatsapp_service.start_server_audio_sink_capture",
            new_callable=AsyncMock,
            side_effect=[handle_one, handle_two],
        ) as start_capture:
            await service._start_server_audio_sink_capture(active_one)
            await service._start_server_audio_sink_capture(active_two)

        self.assertEqual(start_capture.await_count, 2)
        self.assertIsNot(active_one.server_audio_sink_handle, active_two.server_audio_sink_handle)
        self.assertIsNot(
            active_one.server_audio_sink_handle.ffmpeg_process,
            active_two.server_audio_sink_handle.ffmpeg_process,
        )
        self.assertNotEqual(
            active_one.server_audio_sink_handle.sink_name,
            active_two.server_audio_sink_handle.sink_name,
        )
        self.assertNotEqual(
            active_one.server_audio_sink_handle.module_id,
            active_two.server_audio_sink_handle.module_id,
        )

    async def test_session_finished_marks_meeting_processed(self):
        store = FakeMeetingStore()
        store.source_chunks_for_id = {
            "source-1": [
                {
                    "chunk_index": 0,
                    "speaker_label": "Aman",
                    "text": "We should launch next week.",
                    "metadata": {},
                }
            ]
        }
        service = build_service(meeting_store=store)
        service.openai_client = FakeOpenAIClient(
            responses=[
                '{"summary_short":"Orbit recap","summary_long":"Aman launch update and Ravi issue.","decisions":[],"action_items":[],"risks":[],"open_questions":[],"durable_memories":[]}'
            ]
        )
        state = MeetingState(
            session_id="session-1",
            meet_url="https://meet.google.com/abc-defg-hij",
            meeting_code="abc-defg-hij",
            display_name="Orbit",
            joined_at="2026-05-31T10:00:00",
            live_stt_requested=True,
            live_stt_started=True,
            finished_at="2026-05-31T11:00:00",
        )
        state.captured_messages = [
            ChatMessage(
                fingerprint="fp",
                raw_text="Orbit\\nhello",
                normalized_text="hello",
                author="Orbit",
                timestamp_text="10:00",
            )
        ]
        service.active_sessions[state.session_id] = ActiveMeeting(
            session_id=state.session_id,
            meet_url=state.meet_url,
            state=state,
            meeting_id="meeting-1",
            source_id="source-1",
            capture_session_id="capture-1",
            capture_health_metadata={
                "audio": {"chunk_count": 1, "speech_chunk_count": 1},
                "deepgram": {"final_transcript_count": 1, "interim_transcript_count": 0},
            },
        )
        service.live_stt = FakeLiveSTT()

        async def fake_send_whatsapp_message(body):
            return None

        service.send_whatsapp_message = fake_send_whatsapp_message

        await service.handle_session_finished(state)

        self.assertEqual(store.updates[0]["status"], "processing")
        self.assertEqual(store.updates[-1]["status"], "processed")
        self.assertEqual(store.extraction_runs[-1]["status"], "success")
        self.assertEqual(store.capture_session_updates[-1]["status"], "processing")
        self.assertEqual(store.finished_capture_sessions, ["capture-1"])
        fields = store.updates[-1]["fields"]
        self.assertEqual(fields["ended_at"], "2026-05-31T11:00:00")
        self.assertEqual(fields["started_at"], "2026-05-31T10:00:00")
        self.assertEqual(fields["summary_short"], "Orbit recap")

    async def test_run_meeting_extraction_persists_decisions(self):
        store = FakeMeetingStore()
        store.source_chunks_for_id = {
            "source-1": [
                {
                    "chunk_index": 0,
                    "speaker_label": "Aman",
                    "text": "We should launch next week.",
                },
                {
                    "chunk_index": 1,
                    "speaker_label": "Ravi",
                    "text": "Payments are still failing.",
                },
            ]
        }
        service = build_service(
            memory=FakeMemory(),
            meeting_store=store,
        )
        service.openai_client = FakeOpenAIClient(
            responses=[
                '{"summary_short":"Launch update","summary_long":"Aman said launch and Ravi reported payments issue.","decisions":[{"title":"Delay launch","decision_text":"The team decided to delay launch by one week.","rationale":"Payments are still failing.","owner_text":"Engineering","confidence":0.86},{"title":"Invalid","owner_text":"PM"}],"action_items":[],"risks":[],"open_questions":[],"durable_memories":[]}'
            ]
        )
        result = await service.runMeetingExtraction(
            {
                "meetingId": "meeting-1",
                "sourceId": "source-1",
            }
        )

        self.assertEqual(result["status"], "success")
        self.assertEqual(result.get("decisions_inserted"), 1)
        self.assertEqual(len(store.decisions), 1)
        self.assertEqual(store.decisions[0]["title"], "Delay launch")
        self.assertEqual(store.decisions[0]["decision_text"], "The team decided to delay launch by one week.")
        self.assertEqual(store.decisions[0]["owner_text"], "Engineering")
        self.assertEqual(store.decisions[0]["confidence"], 0.86)

    async def test_run_meeting_extraction_persists_decisions_with_legacy_keys(self):
        store = FakeMeetingStore()
        store.source_chunks_for_id = {
            "source-1": [
                {
                    "chunk_index": 0,
                    "speaker_label": "Aman",
                    "text": "We should launch next week.",
                },
                {
                    "chunk_index": 1,
                    "speaker_label": "Ravi",
                    "text": "Payments are still failing.",
                },
            ]
        }
        service = build_service(
            memory=FakeMemory(),
            meeting_store=store,
        )
        service.openai_client = FakeOpenAIClient(
            responses=[
                '{"summary_short":"Launch update","summary_long":"Aman said launch and Ravi reported payments issue.","decisions":[{"decision":"The team decided to delay launch by one week.","confidence":0.91},{"owner":"PM","decision":"Close pending tasks before launch."}],"action_items":[],"risks":[],"open_questions":[],"durable_memories":[]}'
            ]
        )
        result = await service.runMeetingExtraction(
            {
                "meetingId": "meeting-1",
                "sourceId": "source-1",
            }
        )

        self.assertEqual(result["status"], "success")
        self.assertEqual(result.get("decisions_inserted"), 2)
        self.assertEqual(len(store.decisions), 2)
        self.assertEqual(store.decisions[0]["decision_text"], "The team decided to delay launch by one week.")
        self.assertEqual(store.decisions[1]["decision_text"], "Close pending tasks before launch.")
        self.assertEqual(store.decisions[1]["title"], "")

    async def test_run_meeting_extraction_persists_action_items(self):
        store = FakeMeetingStore()
        store.source_chunks_for_id = {
            "source-1": [
                {
                    "chunk_index": 0,
                    "speaker_label": "Aman",
                    "text": "We should launch next week.",
                },
                {
                    "chunk_index": 1,
                    "speaker_label": "Ravi",
                    "text": "Payments are still failing.",
                },
            ]
        }
        service = build_service(
            memory=FakeMemory(),
            meeting_store=store,
        )
        service.openai_client = FakeOpenAIClient(
            responses=[
                '{"summary_short":"Launch update","summary_long":"Aman said launch and Ravi reported payments issue.","decisions":[],"action_items":[{"task":"Prepare launch checklist","ownerText":"PM","dueDate":"2026-06-03","confidence":0.71},{"due_date":"2026-06-04","owner":"Ops","task":"Schedule launch rehearsal","dueDate":"2026-06-05"},{"task":" ","ownerText":"PM"}],"risks":[],"open_questions":[],"durable_memories":[]}'
            ]
        )
        result = await service.runMeetingExtraction(
            {
                "meetingId": "meeting-1",
                "sourceId": "source-1",
            }
        )

        self.assertEqual(result["status"], "success")
        self.assertEqual(result.get("action_items_inserted"), 2)
        self.assertEqual(len(store.action_items), 2)
        self.assertEqual(store.action_items[0]["task"], "Prepare launch checklist")
        self.assertEqual(store.action_items[0]["owner_text"], "PM")
        self.assertEqual(store.action_items[0]["due_date"], "2026-06-03")
        self.assertEqual(store.action_items[0]["status"], "open")
        self.assertEqual(store.action_items[0]["confidence"], 0.71)
        self.assertEqual(store.action_items[1]["task"], "Schedule launch rehearsal")
        self.assertEqual(store.action_items[1]["owner_text"], "Ops")

    async def test_run_meeting_extraction_persists_memories(self):
        store = FakeMeetingStore()
        store.source_chunks_for_id = {
            "source-1": [
                {
                    "chunk_index": 0,
                    "speaker_label": "Aman",
                    "text": "We should launch next week.",
                },
                {
                    "chunk_index": 1,
                    "speaker_label": "Ravi",
                    "text": "Payments are still failing.",
                },
            ]
        }
        service = build_service(
            memory=FakeMemory(),
            meeting_store=store,
        )
        service.openai_client = FakeOpenAIClient(
            responses=[
                '{"summary_short":"Launch update","summary_long":"Aman said launch and Ravi reported payments issue.","decisions":[{"title":"Delay launch","decision_text":"The team decided to delay launch by one week."}],"action_items":[],"risks":[],"open_questions":[],"durable_memories":[{"memory_type":"risk","content":"Payment reliability is currently a launch risk.","importance":"high","confidence":0.84},{"content":"The team is prioritizing enterprise customers.","importance":"medium","confidence":0.75}]}'
            ]
        )
        result = await service.runMeetingExtraction(
            {
                "meetingId": "meeting-1",
                "sourceId": "source-1",
            }
        )

        self.assertEqual(result["status"], "success")
        self.assertEqual(result.get("memories_inserted"), 2)
        self.assertEqual(len(store.memories), 2)
        self.assertEqual(store.memories[0]["memory_type"], "risk")
        self.assertEqual(store.memories[0]["content"], "Payment reliability is currently a launch risk.")
        self.assertEqual(store.memories[0]["importance"], "high")
        self.assertEqual(store.memories[0]["confidence"], 0.84)
        self.assertEqual(store.memories[1]["memory_type"], "important_fact")
        self.assertEqual(store.memories[1]["content"], "The team is prioritizing enterprise customers.")
        self.assertEqual(store.memories[1]["importance"], "medium")

    async def test_run_meeting_extraction_success(self):
        store = FakeMeetingStore()
        store.source_chunks_for_id = {
            "source-1": [
                {
                    "chunk_index": 0,
                    "speaker_label": "Aman",
                    "text": "We should launch next week.",
                },
                {
                    "chunk_index": 1,
                    "speaker_label": "Ravi",
                    "text": "Payments are still failing.",
                },
            ]
        }
        service = build_service(
            memory=FakeMemory(),
            meeting_store=store,
        )
        service.openai_client = FakeOpenAIClient(
            responses=[
                '{"summary_short":"Launch update","summary_long":"Aman said launch and Ravi reported payments issue.","decisions":[],"action_items":[],"risks":[],"open_questions":[],"durable_memories":[]}'
            ]
        )
        result = await service.runMeetingExtraction(
            {
                "meetingId": "meeting-1",
                "sourceId": "source-1",
            }
        )

        self.assertEqual(result["status"], "success")
        self.assertEqual(len(store.extraction_runs), 1)
        self.assertEqual(store.extraction_runs[0]["status"], "success")
        self.assertEqual(store.updates[0]["status"], "processing")
        self.assertEqual(store.updates[-1]["status"], "processed")
        self.assertEqual(store.extraction_runs[0]["output_json"]["summary_short"], "Launch update")

    async def test_run_meeting_extraction_failed_on_non_json_output(self):
        store = FakeMeetingStore()
        store.source_chunks_for_id = {
            "source-1": [
                {
                    "chunk_index": 0,
                    "speaker_label": "Aman",
                    "text": "We should launch next week.",
                },
            ]
        }
        service = build_service(
            meeting_store=store,
        )
        service.openai_client = FakeOpenAIClient(
            responses=[
                "Sorry I cannot give JSON."
            ]
        )
        result = await service.runMeetingExtraction(
            {
                "meetingId": "meeting-1",
                "sourceId": "source-1",
            }
        )

        self.assertEqual(result["status"], "failed")
        self.assertEqual(len(store.extraction_runs), 1)
        self.assertEqual(store.extraction_runs[0]["status"], "failed")
        self.assertEqual(store.updates[-1]["status"], "failed")
        self.assertIn("output_json", store.extraction_runs[0])

    async def test_session_finished_marks_meeting_failed_when_chunk_save_fails(self):
        store = FakeMeetingStore()
        store.fail_save_chunks = True
        service = build_service(meeting_store=store)
        state = MeetingState(
            session_id="session-1",
            meet_url="https://meet.google.com/abc-defg-hij",
            meeting_code="abc-defg-hij",
            display_name="Orbit",
            joined_at="2026-05-31T10:00:00",
            live_transcript_segments=[
                TranscriptSegment(
                    source_id="s1",
                    raw_text="hello",
                    clean_text="Hello.",
                    memory_text="Hello.",
                )
            ],
            finished_at="2026-05-31T11:00:00",
        )
        service.active_sessions[state.session_id] = ActiveMeeting(
            session_id=state.session_id,
            meet_url=state.meet_url,
            state=state,
            meeting_id="meeting-1",
            source_id="source-1",
        )
        service.live_stt = FakeLiveSTT()

        async def fake_send_whatsapp_message(body):
            return None

        service.send_whatsapp_message = fake_send_whatsapp_message

        await service.handle_session_finished(state)

        self.assertEqual(store.updates[0]["status"], "processing")
        self.assertEqual(store.updates[-1]["status"], "failed")
        self.assertEqual(len(store.transcript_save_calls), 1)
        self.assertEqual(store.transcript_save_calls[0][0], "source-1")

    async def test_build_transcript_source_chunks_prefers_clean_text(self):
        service = build_service()
        state = MeetingState(
            session_id="session-1",
            meet_url="https://meet.google.com/abc-defg-hij",
            meeting_code="abc-defg-hij",
            display_name="Orbit",
            live_transcript_segments=[
                TranscriptSegment(
                    source_id="s1",
                    raw_text="Meet abc-defg-hij transcript - 00:00:01-00:00:02: Hello.",
                    clean_text="Hello.",
                    memory_text="Meet abc-defg-hij transcript - 00:00:01-00:00:02: Hello.",
                )
            ],
        )

        chunks = service._build_transcript_source_chunks(state)

        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0]["text"], "Hello.")
        self.assertEqual(chunks[0]["metadata"]["memory_text"], "Meet abc-defg-hij transcript - 00:00:01-00:00:02: Hello.")

    async def test_new_resets_dialogue_without_stopping_meetings(self):
        service = build_service()
        state = MeetingState(
            session_id="session-1",
            meet_url="https://meet.google.com/abc-defg-hij",
            meeting_code="abc-defg-hij",
            display_name="Orbit",
        )
        service.active_sessions[state.session_id] = ActiveMeeting(
            session_id=state.session_id,
            meet_url=state.meet_url,
            state=state,
        )
        service.dialogue_history = [
            type("Turn", (), {"inbound": "old", "reply": "old reply"})()
        ]

        xml = await service.handle_incoming_message("whatsapp:+15551234567", "/new")

        self.assertIn("context reset", xml)
        self.assertEqual(service.dialogue_history, [])
        self.assertIn(state.session_id, service.active_sessions)

    async def test_dialogue_history_is_bounded_and_truncated(self):
        service = build_service()

        for index in range(14):
            service.record_dialogue_turn(f"user-{index}", "x" * 2500)

        self.assertEqual(len(service.dialogue_history), 12)
        self.assertEqual(service.dialogue_history[0].inbound, "user-2")
        self.assertEqual(len(service.dialogue_history[-1].reply), 2000)

    async def test_status_lists_active_meeting(self):
        service = build_service()
        state = MeetingState(
            session_id="session-1",
            meet_url="https://meet.google.com/abc-defg-hij",
            meeting_code="abc-defg-hij",
            display_name="Orbit",
            status="joined",
            joined_at="2026-05-30T09:34:16Z",
            live_stt_requested=True,
            live_stt_available=True,
            live_stt_started=True,
        )
        state.live_transcript_segments = [
            TranscriptSegment(
                source_id="s1",
                raw_text="hello",
                clean_text="Hello.",
                memory_text="Hello.",
            )
        ]
        service.active_sessions[state.session_id] = ActiveMeeting(
            session_id=state.session_id,
            meet_url=state.meet_url,
            state=state,
        )

        xml = await service.handle_incoming_message("whatsapp:+15551234567", "status")

        self.assertIn("abc-defg-hij", xml)
        self.assertIn("transcript segments: 1", xml)

    async def test_multiple_meetings_ask_for_code_for_live_recall(self):
        service = build_service()
        for code in ["abc-defg-hij", "xyz-abcd-uvw"]:
            state = MeetingState(
                session_id=f"{code}-session",
                meet_url=f"https://meet.google.com/{code}",
                meeting_code=code,
                display_name="Orbit",
            )
            service.active_sessions[state.session_id] = ActiveMeeting(
                session_id=state.session_id,
                meet_url=state.meet_url,
                state=state,
            )

        xml = await service.handle_incoming_message(
            "whatsapp:+15551234567",
            "what are people discussing?",
        )

        self.assertIn("Multiple meetings are active", xml)
        self.assertIn("abc-defg-hij", xml)
        self.assertIn("xyz-abcd-uvw", xml)

    async def test_live_recall_uses_selected_live_transcript(self):
        service = build_service()
        state = MeetingState(
            session_id="session-1",
            meet_url="https://meet.google.com/abc-defg-hij",
            meeting_code="abc-defg-hij",
            display_name="Orbit",
            live_stt_requested=True,
            live_stt_available=True,
            live_stt_started=True,
        )
        state.live_transcript_segments = [
            TranscriptSegment(
                source_id="s1",
                raw_text="pricing",
                clean_text="We are discussing pricing.",
                memory_text="We are discussing pricing.",
                speaker_name="Priya",
                start_ms=1000,
                end_ms=3000,
            ),
            TranscriptSegment(
                source_id="s2",
                raw_text="launch",
                clean_text="The launch date is Friday.",
                memory_text="The launch date is Friday.",
                speaker_name="Jai",
                start_ms=4000,
                end_ms=6000,
            ),
        ]
        service.active_sessions[state.session_id] = ActiveMeeting(
            session_id=state.session_id,
            meet_url=state.meet_url,
            state=state,
        )

        xml = await service.handle_incoming_message(
            "whatsapp:+15551234567",
            "summarize the meeting",
        )

        self.assertIn("Answer mode: live transcript", xml)
        self.assertIn("Sources:", xml)
        call = service.openai_client.chat.completions.calls[0]
        self.assertIn("We are discussing pricing.", call["messages"][1]["content"])
        self.assertIn("The launch date is Friday.", call["messages"][1]["content"])
        self.assertEqual(service.memory.questions, [])

    async def test_live_recall_does_not_fall_back_to_memory_when_stt_is_sparse(self):
        service = build_service()
        state = MeetingState(
            session_id="session-1",
            meet_url="https://meet.google.com/abc-defg-hij",
            meeting_code="abc-defg-hij",
            display_name="Orbit",
            live_stt_requested=True,
            live_stt_available=True,
            live_stt_started=True,
        )
        service.active_sessions[state.session_id] = ActiveMeeting(
            session_id=state.session_id,
            meet_url=state.meet_url,
            state=state,
        )

        xml = await service.handle_incoming_message(
            "whatsapp:+15551234567",
            "what are people discussing?",
        )

        self.assertIn("too little live transcript context", xml)
        self.assertEqual(service.memory.questions, [])

    async def test_stop_sets_state_and_waits_for_cleanup(self):
        service = build_service()
        state = MeetingState(
            session_id="session-1",
            meet_url="https://meet.google.com/abc-defg-hij",
            meeting_code="abc-defg-hij",
            display_name="Orbit",
        )

        async def done():
            return None

        task = asyncio.create_task(done())
        service.active_sessions[state.session_id] = ActiveMeeting(
            session_id=state.session_id,
            meet_url=state.meet_url,
            state=state,
            task=task,
        )

        xml = await service.handle_incoming_message("whatsapp:+15551234567", "stop monitoring")

        self.assertTrue(state.stop_requested)
        self.assertIn("completed cleanup", xml)

    async def test_leave_in_normal_question_does_not_stop_meeting(self):
        service = build_service()
        state = MeetingState(
            session_id="session-1",
            meet_url="https://meet.google.com/abc-defg-hij",
            meeting_code="abc-defg-hij",
            display_name="Orbit",
        )
        service.active_sessions[state.session_id] = ActiveMeeting(
            session_id=state.session_id,
            meet_url=state.meet_url,
            state=state,
        )

        xml = await service.handle_incoming_message(
            "whatsapp:+15551234567",
            "what is our parental leave policy?",
        )

        self.assertFalse(state.stop_requested)
        self.assertIn("Answer mode: memory-backed recall", xml)
        self.assertEqual(service.memory.questions, ["what is our parental leave policy?"])

    async def test_chat_messages_are_forwarded_to_memory(self):
        service = build_service()
        state = MeetingState(
            session_id="session-1",
            meet_url="https://meet.google.com/abc-defg-hij",
            meeting_code="abc-defg-hij",
            display_name="Orbit",
        )
        message = ChatMessage(
            fingerprint="fp-1",
            raw_text="Priya\\nlaunch is Friday",
            normalized_text="launch is Friday",
            author="Priya",
            timestamp_text="10:05",
        )

        await service.handle_chat_message(state, message, "poll")
        await service.handle_session_finished(state)

        self.assertEqual(service.memory.recorded, [(state, message)])
        self.assertEqual(service.memory.finalized, [state])

    async def test_finished_meeting_reports_missing_live_audio(self):
        service = build_service()
        whatsapp_updates = []

        async def fake_send_whatsapp_message(body):
            whatsapp_updates.append(body)

        service.send_whatsapp_message = fake_send_whatsapp_message
        state = MeetingState(
            session_id="session-1",
            meet_url="https://meet.google.com/abc-defg-hij",
            meeting_code="abc-defg-hij",
            display_name="Orbit",
            joined_at="2026-05-30T09:34:16Z",
            live_stt_requested=True,
        )

        await service.handle_session_finished(state)

        self.assertEqual(
            whatsapp_updates,
            [
                "Orbit finished Meet abc-defg-hij. Captured 0 chat message(s). "
                "Live audio transcription did not start because no audio chunk was received."
            ],
        )

    async def test_finished_meeting_marks_missing_live_audio_failed(self):
        service = build_service()
        state = MeetingState(
            session_id="session-1",
            meet_url="https://meet.google.com/abc-defg-hij",
            meeting_code="abc-defg-hij",
            display_name="Orbit",
            joined_at="2026-05-30T09:34:16Z",
            live_stt_requested=True,
        )
        service.active_sessions[state.session_id] = ActiveMeeting(
            session_id=state.session_id,
            meet_url=state.meet_url,
            state=state,
            capture_session_id="capture-1",
        )

        async def fake_send_whatsapp_message(body):
            return None

        service.send_whatsapp_message = fake_send_whatsapp_message
        await service.handle_session_finished(state)

        self.assertEqual(
            service.meeting_store.failed_capture_sessions[-1]["error_code"],
            "NO_AUDIO_CHUNKS_RECEIVED",
        )

    async def test_finished_unadmitted_meeting_marks_capture_session_failed(self):
        service = build_service()
        state = MeetingState(
            session_id="session-1",
            meet_url="https://meet.google.com/abc-defg-hij",
            meeting_code="abc-defg-hij",
            display_name="Orbit",
            status="waiting_for_host",
        )
        service.active_sessions[state.session_id] = ActiveMeeting(
            session_id=state.session_id,
            meet_url=state.meet_url,
            state=state,
            capture_session_id="capture-1",
        )

        async def fake_send_whatsapp_message(body):
            return None

        service.send_whatsapp_message = fake_send_whatsapp_message

        await service.handle_session_finished(state)

        self.assertEqual(
            service.meeting_store.failed_capture_sessions[-1]["error_code"],
            "CAPTURE_NOT_ADMITTED",
        )

    async def test_finished_meeting_reports_leave_reason(self):
        service = build_service()
        whatsapp_updates = []

        async def fake_send_whatsapp_message(body):
            whatsapp_updates.append(body)

        service.send_whatsapp_message = fake_send_whatsapp_message
        state = MeetingState(
            session_id="session-1",
            meet_url="https://meet.google.com/abc-defg-hij",
            meeting_code="abc-defg-hij",
            display_name="Orbit",
            joined_at="2026-05-30T09:34:16Z",
            leave_reason="Orbit is the only participant left in the meeting.",
        )

        await service.handle_session_finished(state)

        self.assertEqual(
            whatsapp_updates,
            [
                "Orbit finished Meet abc-defg-hij. Captured 0 chat message(s). "
                "Orbit is the only participant left in the meeting."
            ],
        )

    async def test_meet_chat_mention_gets_model_reply(self):
        service = build_service()
        state = MeetingState(
            session_id="session-1",
            meet_url="https://meet.google.com/abc-defg-hij",
            meeting_code="abc-defg-hij",
            display_name="Orbit",
        )
        previous = ChatMessage(
            fingerprint="fp-1",
            raw_text="Jai\\nwe are discussing pricing",
            normalized_text="we are discussing pricing",
            author="Jai",
            timestamp_text="10:04",
        )
        mention = ChatMessage(
            fingerprint="fp-2",
            raw_text="Jai\\n@orbit are you there?",
            normalized_text="@orbit are you there?",
            author="Jai",
            timestamp_text="10:05",
        )
        state.captured_messages = [previous, mention]

        reply = await service.handle_orbit_mention(state, mention)

        self.assertEqual(reply, "General answer from Orbit.")
        call = service.openai_client.chat.completions.calls[0]
        self.assertIn("are you there?", call["messages"][1]["content"])
        self.assertIn("we are discussing pricing", call["messages"][1]["content"])

    async def test_extension_audio_stream_forwards_chunks_to_live_stt(self):
        service = build_service()
        whatsapp_updates = []

        async def fake_send_whatsapp_message(body):
            whatsapp_updates.append(body)

        service.send_whatsapp_message = fake_send_whatsapp_message
        state = MeetingState(
            session_id="session-1",
            meet_url="https://meet.google.com/abc-defg-hij",
            meeting_code="abc-defg-hij",
            display_name="Orbit",
        )
        service.active_sessions[state.session_id] = ActiveMeeting(
            session_id=state.session_id,
            meet_url=state.meet_url,
            state=state,
            capture_session_id="capture-1",
        )
        websocket = FakeWebSocket(
            [
                {"text": '{"type":"start","encoding":"linear16","sample_rate":16000,"channels":1}'},
                {"bytes": b"pcm"},
                {"bytes": b"more"},
                {"text": '{"type":"stop"}'},
            ]
        )

        await service.handle_audio_stream(websocket, state.session_id)

        self.assertTrue(websocket.accepted)
        self.assertEqual(websocket.sent_json, [{"type": "ready"}])
        fake_session = service.live_stt.sessions[0][2]
        self.assertEqual(fake_session.audio_chunks, [b"pcm", b"more"])
        self.assertEqual(service.live_stt.stopped, [state.session_id])
        self.assertTrue(state.live_stt_started)
        self.assertIsNotNone(state.live_stt_audio_confirmed_at)
        self.assertEqual(
            state.live_stt_status_detail,
            "Deepgram stream connected and first audio chunk forwarded.",
        )
        self.assertEqual(
            whatsapp_updates,
            ["Orbit confirmed live audio transcription for Meet abc-defg-hij."],
        )
        self.assertEqual(
            service.meeting_store.capture_session_updates[-1]["status"],
            "streaming_audio",
        )
        audio = service.active_sessions[state.session_id].capture_health_metadata["audio"]
        self.assertTrue(audio["streaming_started"])
        self.assertIsNotNone(audio["first_chunk_at"])
        self.assertEqual(audio["chunk_count"], 2)
        self.assertEqual(audio["bytes_received"], 7)
        self.assertEqual(audio["bytes_forwarded_to_stt"], 7)
        self.assertTrue(service.meeting_store.capture_session_metadata_updates)

    async def test_deepgram_health_tracks_connection_and_transcripts_without_text(self):
        service = build_service()
        state = MeetingState(
            session_id="session-1",
            meet_url="https://meet.google.com/abc-defg-hij",
            meeting_code="abc-defg-hij",
            display_name="Orbit",
        )
        active = ActiveMeeting(
            session_id=state.session_id,
            meet_url=state.meet_url,
            state=state,
            capture_session_id="capture-1",
        )
        service.active_sessions[state.session_id] = active

        await service._handle_live_stt_health_event(state, "connect_started", {})
        await service._handle_live_stt_health_event(state, "connected", {})
        await service._handle_live_stt_health_event(
            state,
            "transcript",
            {"is_final": False, "transcript": "must not be stored"},
        )
        await service._handle_live_stt_health_event(
            state,
            "transcript",
            {"is_final": True, "transcript": "must not be stored"},
        )
        await service._handle_live_stt_health_event(state, "keepalive", {})

        deepgram = active.capture_health_metadata["deepgram"]
        self.assertIsNotNone(deepgram["connect_started_at"])
        self.assertIsNotNone(deepgram["connected_at"])
        self.assertIsNotNone(deepgram["first_transcript_at"])
        self.assertEqual(deepgram["final_transcript_count"], 1)
        self.assertEqual(deepgram["interim_transcript_count"], 1)
        self.assertEqual(deepgram["keepalive_count"], 1)
        self.assertIsNotNone(deepgram["last_keepalive_at"])
        self.assertNotIn("must not be stored", str(service.meeting_store.capture_session_metadata))

    async def test_extension_audio_stream_drops_sustained_pcm_silence_and_sends_keepalive(self):
        service = build_service()
        state = MeetingState(
            session_id="session-1",
            meet_url="https://meet.google.com/abc-defg-hij",
            meeting_code="abc-defg-hij",
            display_name="Orbit",
        )
        service.active_sessions[state.session_id] = ActiveMeeting(
            session_id=state.session_id,
            meet_url=state.meet_url,
            state=state,
            capture_session_id="capture-1",
        )
        speech = pcm16_chunk(2000)
        silence = pcm16_chunk(0)
        websocket = FakeWebSocket(
            [
                {"text": '{"type":"start","encoding":"linear16","sample_rate":16000,"channels":1}'},
                {"bytes": speech},
                *[{"bytes": silence} for _ in range(15)],
                {"text": '{"type":"stop"}'},
            ]
        )

        await service.handle_audio_stream(websocket, state.session_id)

        fake_session = service.live_stt.sessions[0][2]
        self.assertEqual(fake_session.audio_chunks, [speech, *([silence] * 9)])
        self.assertGreaterEqual(fake_session.keepalives, 1)
        audio = service.active_sessions[state.session_id].capture_health_metadata["audio"]
        self.assertEqual(audio["speech_chunk_count"], 1)
        self.assertEqual(audio["silent_chunk_count"], 15)
        self.assertEqual(audio["bytes_received"], len(speech) + len(silence) * 15)
        self.assertEqual(audio["bytes_forwarded_to_stt"], len(speech) + len(silence) * 9)
        self.assertEqual(audio["bytes_dropped_silence"], len(silence) * 6)
        self.assertTrue(audio["silence_gated"])

    async def test_finished_meeting_classifies_audio_only_silence(self):
        service = build_service()
        state = MeetingState(
            session_id="session-1",
            meet_url="https://meet.google.com/abc-defg-hij",
            meeting_code="abc-defg-hij",
            display_name="Orbit",
            joined_at="2026-05-30T09:34:16Z",
            live_stt_requested=True,
        )
        active = ActiveMeeting(
            session_id=state.session_id,
            meet_url=state.meet_url,
            state=state,
            capture_session_id="capture-1",
        )
        active.capture_health_metadata["audio"]["chunk_count"] = 5
        active.capture_health_metadata["audio"]["silent_chunk_count"] = 5
        service.active_sessions[state.session_id] = active

        async def fake_send_whatsapp_message(body):
            return None

        service.send_whatsapp_message = fake_send_whatsapp_message
        await service.handle_session_finished(state)

        self.assertEqual(
            service.meeting_store.failed_capture_sessions[-1]["error_code"],
            "AUDIO_ONLY_SILENCE",
        )

    async def test_finished_meeting_classifies_missing_transcript(self):
        service = build_service()
        state = MeetingState(
            session_id="session-1",
            meet_url="https://meet.google.com/abc-defg-hij",
            meeting_code="abc-defg-hij",
            display_name="Orbit",
            joined_at="2026-05-30T09:34:16Z",
            live_stt_requested=True,
        )
        active = ActiveMeeting(
            session_id=state.session_id,
            meet_url=state.meet_url,
            state=state,
            capture_session_id="capture-1",
        )
        active.capture_health_metadata["audio"]["chunk_count"] = 5
        active.capture_health_metadata["audio"]["speech_chunk_count"] = 2
        service.active_sessions[state.session_id] = active

        async def fake_send_whatsapp_message(body):
            return None

        service.send_whatsapp_message = fake_send_whatsapp_message
        await service.handle_session_finished(state)

        self.assertEqual(
            service.meeting_store.failed_capture_sessions[-1]["error_code"],
            "NO_TRANSCRIPT_RECEIVED",
        )

    async def test_deepgram_keepalive_failure_is_classified(self):
        service = build_service()
        state = MeetingState(
            session_id="session-1",
            meet_url="https://meet.google.com/abc-defg-hij",
            meeting_code="abc-defg-hij",
            display_name="Orbit",
        )
        service.active_sessions[state.session_id] = ActiveMeeting(
            session_id=state.session_id,
            meet_url=state.meet_url,
            state=state,
            capture_session_id="capture-1",
        )

        await service._handle_live_stt_health_event(
            state,
            "keepalive_failed",
            {"error": "connection closed"},
        )

        failure = service.meeting_store.failed_capture_sessions[-1]
        self.assertEqual(failure["error_code"], "DEEPGRAM_KEEPALIVE_FAILED")
        self.assertEqual(failure["metadata"]["deepgram"]["error"], "connection closed")

    async def test_audio_metadata_writes_are_throttled(self):
        service = build_service()
        state = MeetingState(
            session_id="session-1",
            meet_url="https://meet.google.com/abc-defg-hij",
            meeting_code="abc-defg-hij",
            display_name="Orbit",
        )
        active = ActiveMeeting(
            session_id=state.session_id,
            meet_url=state.meet_url,
            state=state,
            capture_session_id="capture-1",
            last_capture_metadata_flush_at=asyncio.get_running_loop().time(),
        )

        for _ in range(CAPTURE_AUDIO_METADATA_FLUSH_CHUNKS - 1):
            service._record_audio_chunk_received(active, 3)
            service._record_audio_chunk_forwarded(active, 3)
            await service._flush_capture_audio_health(active)

        self.assertEqual(service.meeting_store.capture_session_metadata_updates, [])

        service._record_audio_chunk_received(active, 3)
        service._record_audio_chunk_forwarded(active, 3)
        await service._flush_capture_audio_health(active)

        self.assertEqual(len(service.meeting_store.capture_session_metadata_updates), 1)
        self.assertEqual(
            service.meeting_store.capture_session_metadata["audio"]["chunk_count"],
            CAPTURE_AUDIO_METADATA_FLUSH_CHUNKS,
        )

    async def test_deepgram_connect_failure_is_classified(self):
        service = build_service()
        state = MeetingState(
            session_id="session-1",
            meet_url="https://meet.google.com/abc-defg-hij",
            meeting_code="abc-defg-hij",
            display_name="Orbit",
        )
        service.active_sessions[state.session_id] = ActiveMeeting(
            session_id=state.session_id,
            meet_url=state.meet_url,
            state=state,
            capture_session_id="capture-1",
        )

        await service._handle_live_stt_health_event(
            state,
            "connect_failed",
            {"error": "provider unavailable"},
        )

        failure = service.meeting_store.failed_capture_sessions[-1]
        self.assertEqual(failure["error_code"], "DEEPGRAM_CONNECT_FAILED")
        self.assertEqual(failure["metadata"]["deepgram"]["error"], "provider unavailable")

    async def test_extension_audio_stream_is_not_confirmed_before_first_chunk(self):
        service = build_service()
        state = MeetingState(
            session_id="session-1",
            meet_url="https://meet.google.com/abc-defg-hij",
            meeting_code="abc-defg-hij",
            display_name="Orbit",
        )
        service.active_sessions[state.session_id] = ActiveMeeting(
            session_id=state.session_id,
            meet_url=state.meet_url,
            state=state,
        )
        websocket = FakeWebSocket(
            [
                {"text": '{"type":"start","encoding":"linear16","sample_rate":16000,"channels":1}'},
                {"text": '{"type":"stop"}'},
            ]
        )

        await service.handle_audio_stream(websocket, state.session_id)

        self.assertFalse(state.live_stt_started)
        self.assertIsNone(state.live_stt_audio_confirmed_at)
        self.assertEqual(
            state.live_stt_status_detail,
            "Extension audio WebSocket connected. Waiting for the first audio chunk.",
        )

    async def test_extension_audio_stream_failure_marks_capture_session_failed(self):
        service = build_service()
        state = MeetingState(
            session_id="session-1",
            meet_url="https://meet.google.com/abc-defg-hij",
            meeting_code="abc-defg-hij",
            display_name="Orbit",
        )
        service.active_sessions[state.session_id] = ActiveMeeting(
            session_id=state.session_id,
            meet_url=state.meet_url,
            state=state,
            capture_session_id="capture-1",
        )
        websocket = FakeWebSocket(
            [
                {"text": '{"type":"start","encoding":"linear16","sample_rate":16000,"channels":1}'},
            ]
        )

        await service.handle_audio_stream(websocket, state.session_id)

        self.assertEqual(
            service.meeting_store.failed_capture_sessions[-1]["error_code"],
            "AUDIO_WEBSOCKET_CLOSED",
        )

    async def test_extension_empty_audio_chunk_does_not_confirm_live_stt(self):
        service = build_service()
        state = MeetingState(
            session_id="session-1",
            meet_url="https://meet.google.com/abc-defg-hij",
            meeting_code="abc-defg-hij",
            display_name="Orbit",
        )
        service.active_sessions[state.session_id] = ActiveMeeting(
            session_id=state.session_id,
            meet_url=state.meet_url,
            state=state,
            capture_session_id="capture-1",
        )
        websocket = FakeWebSocket(
            [
                {"text": '{"type":"start","encoding":"linear16","sample_rate":16000,"channels":1}'},
                {"bytes": b""},
                {"text": '{"type":"stop"}'},
            ]
        )

        await service.handle_audio_stream(websocket, state.session_id)

        self.assertFalse(state.live_stt_started)
        fake_session = service.live_stt.sessions[0][2]
        self.assertEqual(fake_session.audio_chunks, [])
        self.assertEqual(
            service.active_sessions[state.session_id]
            .capture_health_metadata["audio"]["silent_or_empty_chunk_count"],
            1,
        )

    async def test_extension_missing_unknown_session_closes_websocket(self):
        service = build_service()
        websocket = FakeWebSocket([])

        await service.handle_audio_stream(websocket, "missing")

        self.assertEqual(websocket.closed[0], 4404)

    async def test_extension_audio_stream_rejects_bad_session_token(self):
        service = build_service()
        state = MeetingState(
            session_id="session-1",
            meet_url="https://meet.google.com/abc-defg-hij",
            meeting_code="abc-defg-hij",
            display_name="Orbit",
            live_stt_audio_token="expected-token",
        )
        service.active_sessions[state.session_id] = ActiveMeeting(
            session_id=state.session_id,
            meet_url=state.meet_url,
            state=state,
        )
        websocket = FakeWebSocket([], query_params={"token": "wrong-token"})

        await service.handle_audio_stream(websocket, state.session_id)

        self.assertEqual(websocket.closed[0], 4403)
        self.assertFalse(websocket.accepted)


if __name__ == "__main__":
    unittest.main()
