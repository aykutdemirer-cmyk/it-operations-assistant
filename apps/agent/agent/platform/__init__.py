"""Platform-özel toplama mantığının dispatch noktası — `collectors/*`
modülleri doğrudan `windows`/`linux` alt modüllerini import ETMEZ,
bunun yerine `resolve()` ile o anki platforma uygun modülü alır. Bu,
her yeni collector'da tekrar `sys.platform` kontrolü tekrarını önler."""

from __future__ import annotations

import sys
from types import ModuleType


def current_os() -> str:
    if sys.platform.startswith("win"):
        return "windows"
    if sys.platform.startswith("linux"):
        return "linux"
    raise RuntimeError(
        f"Desteklenmeyen platform: {sys.platform!r} (yalnızca Windows/Linux destekleniyor)"
    )


def resolve() -> ModuleType:
    if current_os() == "windows":
        from agent.platform import windows

        return windows
    from agent.platform import linux

    return linux
