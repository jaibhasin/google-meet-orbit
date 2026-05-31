from __future__ import annotations

from typing import Any


_capture_service: Any = None


def register_capture_service(service: Any) -> None:
    global _capture_service
    _capture_service = service


def unregister_capture_service(service: Any = None) -> None:
    global _capture_service
    if service is None or _capture_service is service:
        _capture_service = None


def get_capture_service() -> Any:
    return _capture_service
