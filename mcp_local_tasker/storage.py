from __future__ import annotations

import json
import os
import sqlite3
from dataclasses import dataclass
from typing import Any, Optional

from .constants import (
    ALLOWED_CATEGORY,
    ALLOWED_MILESTONE_STATUS,
    ALLOWED_TICKET_STATUS,
    CATEGORY_SHORT,
    json_dumps,
    now_ts,
    gen_id,
    gen_ticket_id,
    ensure_dir,
)


def format_output(data: Any, format: str, group_by_milestone: bool = False) -> str:
    if format == "json":
        return json.dumps(data, indent=2, ensure_ascii=False)
    elif format == "md":
        if isinstance(data, list):
            if group_by_milestone:
                from collections import defaultdict

                by_milestone = defaultdict(list)
                for item in data:
                    mid = item.get("milestone_id", "no-milestone")
                    by_milestone[mid].append(item)

                lines = ["# Tickets\n"]
                for mid, items in by_milestone.items():
                    lines.append(f"## Milestone: {mid}\n")
                    for item in items:
                        lines.append(
                            f"- **{item.get('title', 'N/A')}** ({item.get('status', 'N/A')})"
                        )
                        lines.append(f"  - ID: {item.get('id', 'N/A')}")
                        lines.append(f"  - Category: {item.get('category', 'N/A')}")
                        if item.get("description"):
                            lines.append(
                                f"  - Description: {item.get('description', '')}"
                            )
                        lines.append("")
                    lines.append("")
                return "\n".join(lines)
            else:
                lines = ["# Tickets\n"]
                for item in data:
                    lines.append(
                        f"- **{item.get('title', 'N/A')}** ({item.get('status', 'N/A')})"
                    )
                    lines.append(f"  - ID: {item.get('id', 'N/A')}")
                    lines.append(f"  - Category: {item.get('category', 'N/A')}")
                    if item.get("description"):
                        lines.append(f"  - Description: {item.get('description', '')}")
                    lines.append("")
                return "\n".join(lines)
        elif isinstance(data, dict):
            lines = ["# Ticket\n"]
            for key, value in data.items():
                lines.append(f"- **{key}**: {value}")
            return "\n".join(lines)
        else:
            return str(data)
    else:
        raise ValueError(f"Unknown format: {format}")


def write_output(data: Any, output: dict) -> dict:
    mode = output.get("mode", "inline")
    format = output.get("format", "json")
    path = output.get("path")
    group_by_milestone = output.get("group_by_milestone", False)

    if mode == "inline":
        return data

    if mode == "file":
        if not path:
            raise ValueError("path is required when mode is 'file'")

        ensure_dir(os.path.dirname(path))
        content = format_output(data, format, group_by_milestone)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)

        return {
            "ok": True,
            "written_to": path,
            "format": format,
            "count": len(data) if isinstance(data, list) else 1,
        }

    raise ValueError(f"Unknown mode: {mode}")


@dataclass
class Storage:
    db_path: str

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        conn.execute("PRAGMA foreign_keys=ON;")
        return conn

    def init_schema(self) -> None:
        with self.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS milestones (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL,
                    priority INTEGER NOT NULL DEFAULT 0,
                    rank INTEGER NOT NULL DEFAULT 0,
                    prefix TEXT NOT NULL DEFAULT '',
                    ticket_counter INTEGER NOT NULL DEFAULT 0,
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL
                );

                CREATE TABLE IF NOT EXISTS tickets (
                    id TEXT PRIMARY KEY,
                    milestone_id TEXT NULL,
                    status TEXT NOT NULL,
                    priority INTEGER NOT NULL DEFAULT 0,
                    category TEXT NOT NULL DEFAULT 'other',
                    is_bug INTEGER NOT NULL DEFAULT 0,
                    title TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    recommendations TEXT NOT NULL DEFAULT '',
                    acceptance_criteria TEXT NOT NULL DEFAULT '',
                    is_deleted INTEGER NOT NULL DEFAULT 0,
                    version INTEGER NOT NULL DEFAULT 1,
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL,
                    FOREIGN KEY (milestone_id) REFERENCES milestones(id) ON DELETE SET NULL
                );

                CREATE TABLE IF NOT EXISTS ticket_deps (
                    ticket_id TEXT NOT NULL,
                    depends_on_ticket_id TEXT NOT NULL,
                    created_at INTEGER NOT NULL,
                    PRIMARY KEY (ticket_id, depends_on_ticket_id),
                    FOREIGN KEY (ticket_id) REFERENCES tickets(id) ON DELETE CASCADE,
                    FOREIGN KEY (depends_on_ticket_id) REFERENCES tickets(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    entity_type TEXT NOT NULL,
                    entity_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    created_at INTEGER NOT NULL
                );

                CREATE VIRTUAL TABLE IF NOT EXISTS ticket_fts
                USING fts5(
                    ticket_id,
                    title,
                    description,
                    recommendations,
                    acceptance_criteria
                );

                CREATE INDEX IF NOT EXISTS idx_tickets_milestone ON tickets(milestone_id);
                CREATE INDEX IF NOT EXISTS idx_tickets_status ON tickets(status);
                CREATE INDEX IF NOT EXISTS idx_tickets_category ON tickets(category);
                """
            )

            # Migration: add rank column if it doesn't exist
            try:
                conn.execute("SELECT rank FROM milestones LIMIT 1")
            except sqlite3.OperationalError:
                conn.execute(
                    "ALTER TABLE milestones ADD COLUMN rank INTEGER NOT NULL DEFAULT 0"
                )

            # Migration: add prefix and ticket_counter to milestones
            try:
                conn.execute("SELECT prefix FROM milestones LIMIT 1")
            except sqlite3.OperationalError:
                conn.execute(
                    "ALTER TABLE milestones ADD COLUMN prefix TEXT NOT NULL DEFAULT ''"
                )
                conn.execute(
                    "ALTER TABLE milestones ADD COLUMN ticket_counter INTEGER NOT NULL DEFAULT 0"
                )

            # Migration: add is_bug column if it doesn't exist
            try:
                conn.execute("SELECT is_bug FROM tickets LIMIT 1")
            except sqlite3.OperationalError:
                conn.execute(
                    "ALTER TABLE tickets ADD COLUMN is_bug INTEGER NOT NULL DEFAULT 0"
                )

            conn.execute("DELETE FROM ticket_fts;")
            conn.execute(
                """
                INSERT INTO ticket_fts(ticket_id, title, description, recommendations, acceptance_criteria)
                SELECT id, title, description, recommendations, acceptance_criteria
                FROM tickets
                WHERE is_deleted = 0;
                """
            )

    def log_event(
        self,
        conn: sqlite3.Connection,
        entity_type: str,
        entity_id: str,
        event_type: str,
        payload: dict,
    ) -> None:
        conn.execute(
            "INSERT INTO events(entity_type, entity_id, event_type, payload, created_at) VALUES (?, ?, ?, ?, ?)",
            (entity_type, entity_id, event_type, json_dumps(payload), now_ts()),
        )

    # ---- Milestones ----

    def milestone_create(
        self,
        title: str,
        description: str,
        status: str,
        priority: int,
        rank: Optional[int] = None,
        prefix: Optional[str] = None,
    ) -> dict:
        if status not in ALLOWED_MILESTONE_STATUS:
            raise ValueError(f"Invalid milestone status: {status}")
        mid = gen_id("ms")
        ts = now_ts()
        rank = rank if rank is not None else priority

        with self.connect() as conn:
            if not prefix:
                count = conn.execute("SELECT COUNT(*) as c FROM milestones").fetchone()[
                    "c"
                ]
                prefix = f"M{count + 1}"

            conn.execute(
                """
                INSERT INTO milestones(id, title, description, status, priority, rank, prefix, ticket_counter, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    mid,
                    title,
                    description or "",
                    status,
                    int(priority or 0),
                    int(rank),
                    prefix,
                    0,
                    ts,
                    ts,
                ),
            )
            self.log_event(
                conn,
                "milestone",
                mid,
                "create",
                {
                    "title": title,
                    "status": status,
                    "priority": priority,
                    "rank": rank,
                    "prefix": prefix,
                },
            )
        return self.milestone_get(mid)

    def milestone_get(self, milestone_id: str) -> dict:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM milestones WHERE id = ?", (milestone_id,)
            ).fetchone()
            if not row:
                raise KeyError(f"Milestone not found: {milestone_id}")
            return dict(row)

    def milestone_list(self, status: Optional[str], include_counts: bool) -> list[dict]:
        with self.connect() as conn:
            params: list[Any] = []
            q = "SELECT * FROM milestones"
            if status:
                q += " WHERE status = ?"
                params.append(status)
            q += " ORDER BY rank DESC, priority DESC, updated_at DESC"

            rows = [dict(r) for r in conn.execute(q, params).fetchall()]
            if not include_counts:
                return rows

            for m in rows:
                cnt = conn.execute(
                    "SELECT COUNT(*) AS c FROM tickets WHERE milestone_id = ? AND is_deleted = 0",
                    (m["id"],),
                ).fetchone()["c"]
                open_cnt = conn.execute(
                    """
                    SELECT COUNT(*) AS c
                    FROM tickets
                    WHERE milestone_id = ? AND is_deleted = 0 AND status NOT IN ('done','canceled')
                    """,
                    (m["id"],),
                ).fetchone()["c"]
                m["ticket_count"] = int(cnt)
                m["open_ticket_count"] = int(open_cnt)
            return rows

    def milestone_update(self, milestone_id: str, patch: dict) -> dict:
        allowed = {"title", "description", "status", "priority", "rank"}
        unknown = set(patch.keys()) - allowed
        if unknown:
            raise ValueError(f"Unknown fields in patch: {sorted(unknown)}")
        if "status" in patch and patch["status"] not in ALLOWED_MILESTONE_STATUS:
            raise ValueError(f"Invalid milestone status: {patch['status']}")

        fields = []
        params = []
        for k in allowed:
            if k in patch:
                fields.append(f"{k} = ?")
                params.append(patch[k])

        if not fields:
            return self.milestone_get(milestone_id)

        params.append(now_ts())
        params.append(milestone_id)

        with self.connect() as conn:
            cur = conn.execute(
                f"UPDATE milestones SET {', '.join(fields)}, updated_at = ? WHERE id = ?",
                params,
            )
            if cur.rowcount == 0:
                raise KeyError(f"Milestone not found: {milestone_id}")
            self.log_event(conn, "milestone", milestone_id, "update", {"patch": patch})
        return self.milestone_get(milestone_id)

    def milestone_delete(self, milestone_id: str, force: bool) -> dict:
        with self.connect() as conn:
            if force:
                cur = conn.execute(
                    "DELETE FROM milestones WHERE id = ?", (milestone_id,)
                )
                if cur.rowcount == 0:
                    raise KeyError(f"Milestone not found: {milestone_id}")
                self.log_event(
                    conn, "milestone", milestone_id, "delete", {"force": True}
                )
                return {"ok": True}
            else:
                cur = conn.execute(
                    "UPDATE milestones SET status = 'archived', updated_at = ? WHERE id = ?",
                    (now_ts(), milestone_id),
                )
                if cur.rowcount == 0:
                    raise KeyError(f"Milestone not found: {milestone_id}")
                self.log_event(
                    conn, "milestone", milestone_id, "archive", {"force": False}
                )
                return {"ok": True, "status": "archived"}

    # ---- Tickets ----

    def _ticket_validate(self, status: str, category: str) -> None:
        if status not in ALLOWED_TICKET_STATUS:
            raise ValueError(f"Invalid ticket status: {status}")
        if category not in ALLOWED_CATEGORY:
            raise ValueError(f"Invalid category: {category}")

    def _fts_upsert(self, conn: sqlite3.Connection, ticket_id: str) -> None:
        conn.execute("DELETE FROM ticket_fts WHERE ticket_id = ?", (ticket_id,))
        conn.execute(
            """
            INSERT INTO ticket_fts(ticket_id, title, description, recommendations, acceptance_criteria)
            SELECT id, title, description, recommendations, acceptance_criteria
            FROM tickets
            WHERE id = ? AND is_deleted = 0
            """,
            (ticket_id,),
        )

    def ticket_create(
        self,
        milestone_id: Optional[str],
        title: str,
        description: str,
        category: str,
        priority: int,
        recommendations: str,
        acceptance_criteria: str,
        status: str,
        is_bug: bool = False,
        id: Optional[str] = None,
    ) -> dict:
        self._ticket_validate(status, category)
        ts = now_ts()
        with self.connect() as conn:
            if milestone_id:
                m = conn.execute(
                    "SELECT id, prefix, ticket_counter FROM milestones WHERE id = ?",
                    (milestone_id,),
                ).fetchone()
                if not m:
                    raise KeyError(f"Milestone not found: {milestone_id}")

                if id is None:
                    new_counter = m["ticket_counter"] + 1
                    conn.execute(
                        "UPDATE milestones SET ticket_counter = ? WHERE id = ?",
                        (new_counter, milestone_id),
                    )
                    tid = gen_ticket_id(m["prefix"], category, is_bug, new_counter)
                else:
                    tid = id
            else:
                tid = id if id else gen_id("t")

            conn.execute(
                """
                INSERT INTO tickets(
                    id, milestone_id, status, priority, category, is_bug, title,
                    description, recommendations, acceptance_criteria,
                    is_deleted, version, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 1, ?, ?)
                """,
                (
                    tid,
                    milestone_id,
                    status,
                    int(priority or 0),
                    category,
                    1 if is_bug else 0,
                    title,
                    description or "",
                    recommendations or "",
                    acceptance_criteria or "",
                    ts,
                    ts,
                ),
            )
            self._fts_upsert(conn, tid)
            self.log_event(
                conn,
                "ticket",
                tid,
                "create",
                {"title": title, "status": status, "milestone_id": milestone_id},
            )
        return self.ticket_get(tid)

    def ticket_get(self, ticket_id: str, output: Optional[dict] = None) -> Any:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM tickets WHERE id = ?", (ticket_id,)
            ).fetchone()
            if not row:
                raise KeyError(f"Ticket not found: {ticket_id}")
            ticket = dict(row)

            deps = conn.execute(
                "SELECT depends_on_ticket_id FROM ticket_deps WHERE ticket_id = ? ORDER BY depends_on_ticket_id",
                (ticket_id,),
            ).fetchall()
            blocked_by = conn.execute(
                "SELECT ticket_id FROM ticket_deps WHERE depends_on_ticket_id = ? ORDER BY ticket_id",
                (ticket_id,),
            ).fetchall()

            ticket["depends_on"] = [r["depends_on_ticket_id"] for r in deps]
            ticket["blocked_by"] = [r["ticket_id"] for r in blocked_by]

            if output:
                return write_output(ticket, output)
            return ticket

    def ticket_list(
        self,
        milestone_id: Optional[str],
        status: Optional[str],
        statuses: Optional[list[str]],
        category: Optional[str],
        include_deleted: bool,
        sort: str,
        output: Optional[dict] = None,
    ) -> Any:
        if status and statuses:
            raise ValueError("Cannot use both 'status' and 'statuses' at once")

        if statuses:
            for s in statuses:
                if s not in ALLOWED_TICKET_STATUS:
                    raise ValueError(f"Invalid ticket status: {s}")

        with self.connect() as conn:
            where = []
            params: list[Any] = []

            if milestone_id is not None:
                where.append("milestone_id = ?")
                params.append(milestone_id)

            if statuses:
                placeholders = ",".join("?" * len(statuses))
                where.append(f"status IN ({placeholders})")
                params.extend(statuses)
            elif status:
                where.append("status = ?")
                params.append(status)

            if category:
                where.append("category = ?")
                params.append(category)

            if not include_deleted:
                where.append("is_deleted = 0")

            q = "SELECT * FROM tickets"
            if where:
                q += " WHERE " + " AND ".join(where)

            if sort == "priority":
                q += " ORDER BY priority DESC, updated_at DESC"
            elif sort == "updated":
                q += " ORDER BY updated_at DESC"
            else:
                q += " ORDER BY created_at DESC"

            rows = [dict(r) for r in conn.execute(q, params).fetchall()]

            if output:
                return write_output(rows, output)
            return rows

    def ticket_update(
        self,
        ticket_id: str,
        patch: dict,
        expected_version: Optional[int],
    ) -> dict:
        allowed = {
            "milestone_id",
            "status",
            "priority",
            "category",
            "is_bug",
            "title",
            "description",
            "recommendations",
            "acceptance_criteria",
        }
        unknown = set(patch.keys()) - allowed
        if unknown:
            raise ValueError(f"Unknown fields in patch: {sorted(unknown)}")

        if "status" in patch:
            if patch["status"] not in ALLOWED_TICKET_STATUS:
                raise ValueError(f"Invalid ticket status: {patch['status']}")
        if "category" in patch:
            if patch["category"] not in ALLOWED_CATEGORY:
                raise ValueError(f"Invalid category: {patch['category']}")

        fields = []
        params = []
        for k in allowed:
            if k in patch:
                fields.append(f"{k} = ?")
                params.append(patch[k])

        if not fields:
            return self.ticket_get(ticket_id)

        with self.connect() as conn:
            if expected_version is not None:
                row = conn.execute(
                    "SELECT version FROM tickets WHERE id = ?", (ticket_id,)
                ).fetchone()
                if not row:
                    raise KeyError(f"Ticket not found: {ticket_id}")
                if int(row["version"]) != int(expected_version):
                    raise ValueError(
                        f"Version mismatch for {ticket_id}: expected {expected_version}, actual {row['version']}"
                    )

            params.append(now_ts())
            q = f"UPDATE tickets SET {', '.join(fields)}, updated_at = ?, version = version + 1 WHERE id = ?"
            params.append(ticket_id)

            cur = conn.execute(q, params)
            if cur.rowcount == 0:
                raise KeyError(f"Ticket not found: {ticket_id}")

            self._fts_upsert(conn, ticket_id)
            self.log_event(conn, "ticket", ticket_id, "update", {"patch": patch})

            if "status" in patch:
                self._maybe_update_milestone_status(conn, ticket_id)

        return self.ticket_get(ticket_id)

    def _maybe_update_milestone_status(
        self, conn: sqlite3.Connection, ticket_id: str
    ) -> None:
        row = conn.execute(
            "SELECT milestone_id FROM tickets WHERE id = ?", (ticket_id,)
        ).fetchone()
        if not row or not row["milestone_id"]:
            return

        milestone_id = row["milestone_id"]

        open_tickets = conn.execute(
            """
            SELECT COUNT(*) as c FROM tickets
            WHERE milestone_id = ? AND is_deleted = 0 AND status NOT IN ('done', 'canceled')
            """,
            (milestone_id,),
        ).fetchone()["c"]

        if open_tickets == 0:
            m = conn.execute(
                "SELECT status FROM milestones WHERE id = ?", (milestone_id,)
            ).fetchone()
            if m and m["status"] not in ("done", "archived"):
                conn.execute(
                    "UPDATE milestones SET status = 'done', updated_at = ? WHERE id = ?",
                    (now_ts(), milestone_id),
                )
                self.log_event(
                    conn,
                    "milestone",
                    milestone_id,
                    "auto_done",
                    {"reason": "all_tickets_completed"},
                )

    def ticket_set_status(
        self, ticket_id: str, status: str, expected_version: Optional[int]
    ) -> dict:
        return self.ticket_update(ticket_id, {"status": status}, expected_version)

    def ticket_delete(self, ticket_id: str, hard: bool) -> dict:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT milestone_id FROM tickets WHERE id = ?", (ticket_id,)
            ).fetchone()
            milestone_id = row["milestone_id"] if row else None

            if hard:
                cur = conn.execute("DELETE FROM tickets WHERE id = ?", (ticket_id,))
                if cur.rowcount == 0:
                    raise KeyError(f"Ticket not found: {ticket_id}")
                conn.execute("DELETE FROM ticket_fts WHERE ticket_id = ?", (ticket_id,))
                self.log_event(conn, "ticket", ticket_id, "delete", {"hard": True})
                result = {"ok": True, "hard": True}
            else:
                cur = conn.execute(
                    "UPDATE tickets SET is_deleted = 1, updated_at = ?, version = version + 1 WHERE id = ?",
                    (now_ts(), ticket_id),
                )
                if cur.rowcount == 0:
                    raise KeyError(f"Ticket not found: {ticket_id}")
                conn.execute("DELETE FROM ticket_fts WHERE ticket_id = ?", (ticket_id,))
                self.log_event(conn, "ticket", ticket_id, "delete", {"hard": False})
                result = {"ok": True, "hard": False}

            if milestone_id:
                self._maybe_update_milestone_status(conn, ticket_id)

            return result

    def ticket_search(
        self,
        query: str,
        milestone_id: Optional[str],
        status: Optional[str],
        statuses: Optional[list[str]],
        category: Optional[str],
        limit: int,
        output: Optional[dict] = None,
    ) -> Any:
        if status and statuses:
            raise ValueError("Cannot use both 'status' and 'statuses' at once")

        if statuses:
            for s in statuses:
                if s not in ALLOWED_TICKET_STATUS:
                    raise ValueError(f"Invalid ticket status: {s}")

        limit = int(limit or 20)
        if limit < 1:
            limit = 1
        if limit > 100:
            limit = 100

        with self.connect() as conn:
            use_fts = query and query.strip()
            if use_fts:
                where = ["t.is_deleted = 0", "f.ticket_id = t.id", "ticket_fts MATCH ?"]
                params: list[Any] = [query]
            else:
                where = ["t.is_deleted = 0"]
                params = []

            if milestone_id is not None:
                where.append("t.milestone_id = ?")
                params.append(milestone_id)

            if statuses:
                placeholders = ",".join("?" * len(statuses))
                where.append(f"t.status IN ({placeholders})")
                params.extend(statuses)
            elif status:
                where.append("t.status = ?")
                params.append(status)

            if category:
                where.append("t.category = ?")
                params.append(category)

            if use_fts:
                sql = f"""
                    SELECT
                        t.id, t.title, t.status, t.priority, t.category, t.milestone_id, t.updated_at,
                        bm25(ticket_fts) AS rank
                    FROM ticket_fts f
                    JOIN tickets t
                    WHERE {" AND ".join(where)}
                    ORDER BY rank
                    LIMIT {limit}
                """
            else:
                sql = f"""
                    SELECT
                        t.id, t.title, t.status, t.priority, t.category, t.milestone_id, t.updated_at,
                        0 AS rank
                    FROM tickets t
                    WHERE {" AND ".join(where)}
                    ORDER BY t.priority DESC, t.updated_at DESC
                    LIMIT {limit}
                """
            rows = [dict(r) for r in conn.execute(sql, params).fetchall()]

            if output:
                return write_output(rows, output)
            return rows

    # ---- Dependencies ----

    def dep_add(
        self, ticket_id: str, depends_on_ticket_id: str, check_cycles: bool
    ) -> dict:
        if ticket_id == depends_on_ticket_id:
            raise ValueError("A ticket cannot depend on itself")

        with self.connect() as conn:
            a = conn.execute(
                "SELECT 1 FROM tickets WHERE id = ? AND is_deleted = 0", (ticket_id,)
            ).fetchone()
            b = conn.execute(
                "SELECT 1 FROM tickets WHERE id = ? AND is_deleted = 0",
                (depends_on_ticket_id,),
            ).fetchone()
            if not a:
                raise KeyError(f"Ticket not found: {ticket_id}")
            if not b:
                raise KeyError(f"Ticket not found: {depends_on_ticket_id}")

            if check_cycles:
                if self._reachable(
                    conn, start=depends_on_ticket_id, target=ticket_id, max_nodes=5000
                ):
                    raise ValueError("Dependency would create a cycle")

            conn.execute(
                "INSERT OR IGNORE INTO ticket_deps(ticket_id, depends_on_ticket_id, created_at) VALUES (?, ?, ?)",
                (ticket_id, depends_on_ticket_id, now_ts()),
            )
            self.log_event(
                conn,
                "ticket",
                ticket_id,
                "dependency_add",
                {"depends_on": depends_on_ticket_id},
            )
        return {"ok": True}

    def dep_remove(self, ticket_id: str, depends_on_ticket_id: str) -> dict:
        with self.connect() as conn:
            conn.execute(
                "DELETE FROM ticket_deps WHERE ticket_id = ? AND depends_on_ticket_id = ?",
                (ticket_id, depends_on_ticket_id),
            )
            self.log_event(
                conn,
                "ticket",
                ticket_id,
                "dependency_remove",
                {"depends_on": depends_on_ticket_id},
            )
        return {"ok": True}

    def dep_list(self, ticket_id: str) -> dict:
        with self.connect() as conn:
            deps = conn.execute(
                "SELECT depends_on_ticket_id FROM ticket_deps WHERE ticket_id = ? ORDER BY depends_on_ticket_id",
                (ticket_id,),
            ).fetchall()
            blocked_by = conn.execute(
                "SELECT ticket_id FROM ticket_deps WHERE depends_on_ticket_id = ? ORDER BY ticket_id",
                (ticket_id,),
            ).fetchall()
            return {
                "depends_on": [r["depends_on_ticket_id"] for r in deps],
                "blocked_by": [r["ticket_id"] for r in blocked_by],
            }

    def _reachable(
        self, conn: sqlite3.Connection, start: str, target: str, max_nodes: int
    ) -> bool:
        visited = set()
        queue = [start]
        steps = 0
        while queue:
            cur = queue.pop(0)
            if cur == target:
                return True
            if cur in visited:
                continue
            visited.add(cur)
            steps += 1
            if steps > max_nodes:
                return True
            rows = conn.execute(
                "SELECT depends_on_ticket_id FROM ticket_deps WHERE ticket_id = ?",
                (cur,),
            ).fetchall()
            for r in rows:
                nxt = r["depends_on_ticket_id"]
                if nxt not in visited:
                    queue.append(nxt)
        return False

    def ticket_graph(self, milestone_id: Optional[str], depth: int) -> dict:
        depth = int(depth or 5)
        if depth < 1:
            depth = 1
        if depth > 50:
            depth = 50

        with self.connect() as conn:
            params: list[Any] = []
            where = ["t.is_deleted = 0"]
            if milestone_id is not None:
                where.append("t.milestone_id = ?")
                params.append(milestone_id)

            nodes = [
                dict(r)
                for r in conn.execute(
                    f"SELECT id, title, status, priority, category, milestone_id FROM tickets t WHERE {' AND '.join(where)}",
                    params,
                ).fetchall()
            ]

            node_ids = {n["id"] for n in nodes}
            edges = []
            for r in conn.execute(
                "SELECT ticket_id, depends_on_ticket_id FROM ticket_deps"
            ).fetchall():
                a = r["ticket_id"]
                b = r["depends_on_ticket_id"]
                if a in node_ids and b in node_ids:
                    edges.append({"from": a, "to": b})

            return {"nodes": nodes, "edges": edges, "depth": depth}

    # ---- Stats ----

    def get_stats(self) -> dict:
        with self.connect() as conn:
            total = conn.execute(
                "SELECT COUNT(*) as c FROM tickets WHERE is_deleted = 0"
            ).fetchone()["c"]

            by_status = {}
            for status in ALLOWED_TICKET_STATUS:
                c = conn.execute(
                    "SELECT COUNT(*) as c FROM tickets WHERE status = ? AND is_deleted = 0",
                    (status,),
                ).fetchone()["c"]
                by_status[status] = c

            by_category = {}
            for cat in ALLOWED_CATEGORY:
                c = conn.execute(
                    "SELECT COUNT(*) as c FROM tickets WHERE category = ? AND is_deleted = 0",
                    (cat,),
                ).fetchone()["c"]
                by_category[cat] = c

            bugs_total = conn.execute(
                "SELECT COUNT(*) as c FROM tickets WHERE is_bug = 1 AND is_deleted = 0"
            ).fetchone()["c"]
            bugs_by_status = {}
            for status in ("todo", "in_progress", "blocked", "done", "canceled"):
                c = conn.execute(
                    "SELECT COUNT(*) as c FROM tickets WHERE is_bug = 1 AND status = ? AND is_deleted = 0",
                    (status,),
                ).fetchone()["c"]
                bugs_by_status[status] = c

            by_priority = {}
            for row in conn.execute(
                "SELECT priority, COUNT(*) as c FROM tickets WHERE is_deleted = 0 GROUP BY priority ORDER BY priority DESC"
            ).fetchall():
                by_priority[str(row["priority"])] = row["c"]

            milestones = []
            for m in conn.execute(
                "SELECT id, title, status FROM milestones ORDER BY rank DESC, priority DESC"
            ).fetchall():
                total_m = conn.execute(
                    "SELECT COUNT(*) as c FROM tickets WHERE milestone_id = ? AND is_deleted = 0",
                    (m["id"],),
                ).fetchone()["c"]
                done_m = conn.execute(
                    "SELECT COUNT(*) as c FROM tickets WHERE milestone_id = ? AND status IN ('done', 'canceled') AND is_deleted = 0",
                    (m["id"],),
                ).fetchone()["c"]
                progress = round((done_m / total_m * 100) if total_m > 0 else 0)
                milestones.append(
                    {
                        "id": m["id"],
                        "title": m["title"],
                        "status": m["status"],
                        "total": total_m,
                        "done": done_m,
                        "progress": progress,
                    }
                )

            return {
                "total_tickets": total,
                "by_status": by_status,
                "by_category": by_category,
                "bugs": {
                    "total": bugs_total,
                    "by_status": bugs_by_status,
                },
                "by_priority": by_priority,
                "milestones": milestones,
                "available_statuses": sorted(ALLOWED_TICKET_STATUS),
                "available_categories": sorted(ALLOWED_CATEGORY),
            }

    # ---- Events ----

    def events_list(
        self,
        entity_type: Optional[str],
        entity_id: Optional[str],
        limit: int,
    ) -> list[dict]:
        limit = int(limit or 50)
        if limit < 1:
            limit = 1
        if limit > 200:
            limit = 200

        with self.connect() as conn:
            where = []
            params: list[Any] = []

            if entity_type:
                where.append("entity_type = ?")
                params.append(entity_type)
            if entity_id:
                where.append("entity_id = ?")
                params.append(entity_id)

            q = "SELECT * FROM events"
            if where:
                q += " WHERE " + " AND ".join(where)
            q += " ORDER BY id DESC LIMIT ?"
            params.append(limit)

            rows = [dict(r) for r in conn.execute(q, params).fetchall()]
            for e in rows:
                try:
                    e["payload"] = json.loads(e["payload"])
                except Exception:
                    pass
            return rows

    # ---- Next Task (Iterator) ----

    def ticket_next(self, category: Optional[str] = None) -> Optional[dict]:
        if category and category not in ALLOWED_CATEGORY:
            raise ValueError(f"Invalid category: {category}")

        with self.connect() as conn:
            milestone_rows = conn.execute(
                """
                SELECT id FROM milestones
                WHERE status NOT IN ('done', 'archived')
                ORDER BY rank DESC, priority DESC, updated_at DESC
                """
            ).fetchall()
            if not milestone_rows:
                return None

            open_statuses = ("todo", "in_progress", "blocked")

            for m_row in milestone_rows:
                milestone_id = m_row["id"]

                params: list[Any] = [milestone_id, *open_statuses]
                where = "milestone_id = ? AND is_deleted = 0 AND status IN (?, ?, ?)"
                if category:
                    where += " AND category = ?"
                    params.append(category)

                candidate_rows = conn.execute(
                    f"""
                    SELECT id, title, status, priority, category, milestone_id, is_bug
                    FROM tickets
                    WHERE {where}
                    ORDER BY is_bug DESC, priority DESC, created_at ASC
                    """,
                    params,
                ).fetchall()

                for row in candidate_rows:
                    tid = row["id"]
                    deps = conn.execute(
                        """
                        SELECT t.status FROM tickets t
                        JOIN ticket_deps d ON d.depends_on_ticket_id = t.id
                        WHERE d.ticket_id = ?
                        """,
                        (tid,),
                    ).fetchall()
                    blocked = any(d["status"] not in ("done", "canceled") for d in deps)
                    if not blocked:
                        return self.ticket_get(tid)

            return None
