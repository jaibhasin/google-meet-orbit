from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from orbit.meet import (
    AUDIO_ROUTING_MODE_NOT_IMPLEMENTED,
    AUDIO_ROUTING_MODE_PROCESS_ENV,
    build_browser,
)


class TestBuildBrowserRouting(unittest.TestCase):
    def setUp(self):
        self._orig_env = dict(os.environ)

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self._orig_env)

    def test_build_browser_uses_process_env_when_available_for_server_sink(self):
        calls = []

        class FakeBrowser:
            init_calls = []

            def __init__(self, **kwargs):
                self.kwargs = dict(kwargs)
                calls.append(self.kwargs)
                FakeBrowser.init_calls.append(self.kwargs)

            @classmethod
            def from_system_chrome(cls, **kwargs):
                raise AssertionError("system chrome should not be used for server_audio_sink routing")

        state = type("state", (), {"session_id": "session-a"})()
        config = type(
            "config",
            (),
            {
                "audio_capture_strategy": "server_audio_sink",
                "audio_sink_name": "orbit_meet_session_a",
                "capture_session_id": "capture-a",
            },
        )()

        with patch.dict(
            os.environ,
            {
                "GMEET_USE_SYSTEM_CHROME": "0",
                "ORBIT_CHROME_CDP_URL": "",
                "HEADLESS": "1",
            },
            clear=False,
        ):
            browser = build_browser(FakeBrowser, state=state, session_config=config)

        self.assertIsNotNone(browser)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["env"], {"PULSE_SINK": "orbit_meet_session_a"})
        self.assertEqual(state.audio_capture_routing_mode, AUDIO_ROUTING_MODE_PROCESS_ENV)
        self.assertTrue(state.browser_audio_routed)
        self.assertTrue(state.browser_process_isolated)

    def test_build_browser_marks_routing_not_implemented_with_cdp(self):
        class FakeBrowser:
            def __init__(self, cdp_url=None, keep_alive=False, **kwargs):
                self.cdp_url = cdp_url
                self.keep_alive = keep_alive
                self.kwargs = dict(kwargs)

            @classmethod
            def from_system_chrome(cls, **kwargs):
                raise AssertionError("shared CDP should bypass managed browser path")

        state = type("state", (), {"session_id": "session-cdp"})()
        config = type(
            "config",
            (),
            {
                "audio_capture_strategy": "server_audio_sink",
                "audio_sink_name": "orbit_meet_session_cdp",
                "capture_session_id": "capture-cdp",
            },
        )()

        with patch.dict(os.environ, {"ORBIT_CHROME_CDP_URL": "ws://127.0.0.1:9222"}, clear=False):
            browser = build_browser(FakeBrowser, state=state, session_config=config)

        self.assertIsNotNone(browser)
        self.assertEqual(browser.cdp_url, "ws://127.0.0.1:9222")
        self.assertTrue(browser.keep_alive)
        self.assertEqual(state.audio_capture_routing_mode, AUDIO_ROUTING_MODE_NOT_IMPLEMENTED)
        self.assertFalse(state.browser_audio_routed)
        self.assertFalse(state.browser_process_isolated)

    def test_build_browser_fallback_when_env_arg_not_supported(self):
        calls = []

        class FakeBrowser:
            def __init__(self, headless=False, keep_alive=False, window_size=None, args=None):
                self.kwargs = {
                    "headless": headless,
                    "keep_alive": keep_alive,
                    "window_size": window_size,
                    "args": args,
                }
                calls.append(self.kwargs)

        state = type("state", (), {"session_id": "session-noenv"})()
        config = type(
            "config",
            (),
            {
                "audio_capture_strategy": "server_audio_sink",
                "audio_sink_name": "orbit_meet_session_noenv",
                "capture_session_id": "capture-noenv",
            },
        )()

        with patch.dict(os.environ, {"GMEET_USE_SYSTEM_CHROME": "0", "ORBIT_CHROME_CDP_URL": ""}, clear=False):
            browser = build_browser(FakeBrowser, state=state, session_config=config)

        self.assertIsNotNone(browser)
        self.assertEqual(len(calls), 1)
        self.assertNotIn("env", calls[0])
        self.assertEqual(state.audio_capture_routing_mode, AUDIO_ROUTING_MODE_NOT_IMPLEMENTED)
        self.assertFalse(state.browser_audio_routed)
        self.assertTrue(state.browser_process_isolated)

    def test_two_server_sessions_get_different_browser_routing_configs(self):
        calls = []

        class FakeBrowser:
            def __init__(self, **kwargs):
                self.kwargs = dict(kwargs)
                calls.append(self.kwargs)

        state_one = type("state", (), {"session_id": "session-one"})()
        state_two = type("state", (), {"session_id": "session-two"})()
        config_one = type(
            "config",
            (),
            {
                "audio_capture_strategy": "server_audio_sink",
                "audio_sink_name": "orbit_meet_session_one",
                "capture_session_id": "capture-one",
            },
        )()
        config_two = type(
            "config",
            (),
            {
                "audio_capture_strategy": "server_audio_sink",
                "audio_sink_name": "orbit_meet_session_two",
                "capture_session_id": "capture-two",
            },
        )()

        with patch.dict(os.environ, {"GMEET_USE_SYSTEM_CHROME": "0", "ORBIT_CHROME_CDP_URL": ""}, clear=False):
            build_browser(FakeBrowser, state=state_one, session_config=config_one)
            build_browser(FakeBrowser, state=state_two, session_config=config_two)

        self.assertEqual(len(calls), 2)
        self.assertNotEqual(calls[0]["env"]["PULSE_SINK"], calls[1]["env"]["PULSE_SINK"])
        self.assertIsNotNone(calls[0].get("env"))
        self.assertIsNotNone(calls[1].get("env"))
        self.assertNotEqual(state_one.session_id, state_two.session_id)
