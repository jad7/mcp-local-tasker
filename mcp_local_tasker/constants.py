import json
import os
import time
import uuid
from typing import Any

ALLOWED_TICKET_STATUS = {"todo", "in_progress", "blocked", "done", "canceled"}
ALLOWED_MILESTONE_STATUS = {"planned", "active", "done", "archived"}
ALLOWED_CATEGORY = {"backend", "frontend", "infra", "docs", "research", "other"}


def now_ts() -> int:
    return int(time.time())


def gen_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10]}"


def ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def json_dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
