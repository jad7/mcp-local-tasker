import json
import os
import time
import uuid
from functools import lru_cache
from typing import Any

try:
    from importlib.metadata import version

    __version__ = version("mcp-local-tasker")
except Exception:
    __version__ = "0.0.0"

ALLOWED_TICKET_STATUS = {"todo", "in_progress", "blocked", "done", "canceled"}
ALLOWED_MILESTONE_STATUS = {"planned", "active", "done", "archived"}
ALLOWED_CATEGORY = {"backend", "frontend", "infra", "docs", "research", "other"}

CATEGORY_SHORT = {
    "backend": "BE",
    "frontend": "FE",
    "infra": "INFRA",
    "docs": "DOCS",
    "research": "RES",
    "other": "OTH",
}


def now_ts() -> int:
    return int(time.time())


def gen_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10]}"


def gen_ticket_id(
    milestone_prefix: str, category: str, is_bug: bool, counter: int
) -> str:
    cat = CATEGORY_SHORT.get(category, category[:3].upper())
    type_suffix = "BUG" if is_bug else "T"
    if milestone_prefix.endswith("-"):
        return f"{milestone_prefix}{type_suffix}-{counter}"
    return f"{milestone_prefix}-{cat}-{type_suffix}-{counter}"


def ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def json_dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
