"""Workspace identity normalization helpers."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import re
from typing import Any, Dict, Optional

from agent_history.utils.paths import (
    CACHED_REMOTE_PREFIX,
    CACHED_WSL_PREFIX,
    CACHED_WINDOWS_PREFIX,
    decode_workspace_path,
    is_cached_workspace,
    is_encoded_workspace_name,
)


class WorkspaceKind(str, Enum):
    """Classification of workspace identifiers."""

    PATH = "path"
    ENCODED = "encoded"
    HASH = "hash"
    CACHED = "cached"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class WorkspaceRef:
    """Canonical workspace identity."""

    key: str
    display: str
    raw: str
    kind: WorkspaceKind

    def as_dict(self) -> Dict[str, Any]:
        return {
            "workspace_key": self.key,
            "workspace_display": self.display,
            "workspace_raw": self.raw,
            "workspace_kind": self.kind.value,
        }


_HASH_RE = re.compile(r"^[0-9a-f]{32,64}$", re.IGNORECASE)
_HASH_DISPLAY_RE = re.compile(r"^\\[hash:[0-9a-f]+\\]$", re.IGNORECASE)


def _looks_like_path(value: str) -> bool:
    if not value:
        return False
    if value.startswith("//"):
        return True
    if "/" in value or "\\" in value:
        return True
    return len(value) > 1 and value[1] == ":"


def _normalize_path(value: str) -> str:
    if not value:
        return value
    normalized = value.replace("\\", "/")
    if normalized.startswith("//"):
        normalized = "//" + re.sub(r"/{2,}", "/", normalized[2:])
    else:
        normalized = re.sub(r"/{2,}", "/", normalized)
    if len(normalized) > 1 and normalized.endswith("/"):
        normalized = normalized.rstrip("/")
    return normalized


def _strip_cached_prefix(value: str) -> str:
    if value.startswith((CACHED_REMOTE_PREFIX, CACHED_WSL_PREFIX, CACHED_WINDOWS_PREFIX)):
        parts = value.split("_", 2)
        if len(parts) >= 3:
            return parts[2]
    return value


def _infer_kind(raw: str) -> WorkspaceKind:
    if not raw:
        return WorkspaceKind.UNKNOWN
    if is_cached_workspace(raw):
        return WorkspaceKind.CACHED
    if is_encoded_workspace_name(raw):
        return WorkspaceKind.ENCODED
    if _looks_like_path(raw):
        return WorkspaceKind.PATH
    if _HASH_RE.match(raw):
        return WorkspaceKind.HASH
    return WorkspaceKind.UNKNOWN


def _display_from_raw(raw: str, kind: WorkspaceKind) -> str:
    if not raw:
        return ""
    if kind == WorkspaceKind.CACHED:
        raw = _strip_cached_prefix(raw)
        if is_encoded_workspace_name(raw):
            return decode_workspace_path(raw, verify_local=False)
        return raw
    if kind == WorkspaceKind.ENCODED:
        return decode_workspace_path(raw, verify_local=False)
    if kind == WorkspaceKind.PATH:
        return _normalize_path(raw)
    if kind == WorkspaceKind.HASH:
        return f"[hash:{raw[:8]}]"
    return raw


def _select_key(raw: str, display: str, kind: WorkspaceKind) -> str:
    if display and _looks_like_path(display):
        return _normalize_path(display)
    if display and _HASH_DISPLAY_RE.match(display):
        return _normalize_path(raw)
    if kind in (WorkspaceKind.ENCODED, WorkspaceKind.CACHED):
        decoded = _display_from_raw(raw, kind)
        if _looks_like_path(decoded):
            return _normalize_path(decoded)
    return _normalize_path(raw)


def build_workspace_ref(raw: Optional[str], readable: Optional[str] = None) -> WorkspaceRef:
    raw_value = raw or ""
    kind = _infer_kind(raw_value)
    display = (readable or "").strip()
    if not display:
        display = _display_from_raw(raw_value, kind)
    key = _select_key(raw_value, display, kind)
    return WorkspaceRef(key=key, display=display or key, raw=raw_value, kind=kind)


def apply_workspace_ref(session: Dict[str, Any]) -> WorkspaceRef:
    raw = session.get("workspace") or ""
    readable = session.get("workspace_readable") or session.get("workspace_display")
    ref = build_workspace_ref(raw, readable)
    session.setdefault("workspace_raw", raw)
    session["workspace_key"] = ref.key
    session["workspace_display"] = ref.display
    session["workspace_kind"] = ref.kind.value
    if not session.get("workspace_readable"):
        session["workspace_readable"] = ref.display
    return ref
