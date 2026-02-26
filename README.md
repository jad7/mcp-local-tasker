# Local Task & Milestone MCP

Lightweight **Model Context Protocol (MCP) server** for local task tracking with milestones, dependencies, and full-text search.

This project is designed for **agent-assisted development** where you need:
- local task tracking (no Jira, no SaaS)
- strict, machine-readable contracts
- minimal dependencies
- predictable behavior for multiple agents

The server runs as a **pure MCP process** (STDIN/STDOUT) and stores all data locally in SQLite.

---

## Quick Start

### Installation

```bash
# Install from GitHub (recommended), specify version
pip install git+https://github.com/jad7/mcp-local-tasker@{version}

# Or latest (may be unstable)
pip install git+https://github.com/jad7/mcp-local-tasker

# Or local editable (for development)
pip install -e .
```

### Running

```bash
# Run as MCP server (STDIO) - default, for Claude/Cursor
python -m mcp_local_tasker

# Or use the entry point (after package is installed)
mcp-local-tasker

# HTTP SSE transport
python -m mcp_local_tasker --transport sse --mount-path /mcp

# HTTP Streamable transport
python -m mcp_local_tasker --transport streamable-http --mount-path /mcp
```

Transport options:
- `stdio` (default) - for Claude Desktop, Cursor, VS Code
- `sse` - Server-Sent Events over HTTP
- `streamable-http` - Streaming HTTP

### Configuration (Claude Desktop / Cursor)

Add to your MCP config:

```json
{
  "mcpServers": {
    "task-tracker": {
      "command": "python",
      "args": ["-m", "mcp_local_tasker"],
      "env": {},
      "description": "Local task and milestone tracker"
    }
  }
}
```

---

## Goals

- **Local-first**: everything lives inside the repository
- **Agent-safe**: clear rules, no hidden side effects
- **Minimal dependencies**: Python stdlib + MCP runtime
- **Structured data**: tasks are data, not markdown blobs
- **Searchable**: full-text search over task content
- **Auditable**: append-only event log

---

## Non-goals

- No UI
- No web server
- No authentication
- No cloud sync
- No LLM / agent SDKs
- No workflow automation beyond task modeling

This is **not** a project manager.  
This is a **stable task memory for agents and humans**.

---

## Data model overview

### Milestones
- Flat list (no nesting)
- Used only as high-level grouping
- Tickets may belong to **one milestone or none**

Fields:
- `id`
- `title`
- `description`
- `status`: `planned | active | done | archived`
- `priority`
- timestamps

---

### Tickets
Core unit of work.

Fields:
- `id`
- `milestone_id` (optional)
- `status`: `todo | in_progress | blocked | done | canceled`
- `priority` (integer)
- `category`: `backend | frontend | infra | docs | research | other`
- `title`
- `description`
- `recommendations` (optional)
- `acceptance_criteria` (optional)
- `version` (optimistic concurrency)
- `is_deleted` (soft delete)
- timestamps

---

### Dependencies
Directed graph:

> **Ticket A depends on Ticket B**

Meaning: A cannot be completed before B.

Rules:
- no self-dependencies
- optional cycle detection
- dependencies are ticket-to-ticket only

---

### Events (audit log)
Append-only event stream for traceability.

---

### Full-text search
SQLite **FTS5** index over:
- title
- description
- recommendations
- acceptance criteria

---

## Storage layout

All data lives inside the repository:

```
.project/
  tasks.db        # SQLite database (single source of truth)
```

You may safely add `.project/` to `.gitignore`.

---

## MCP contract principles

1. All mutations go through MCP tools
2. No direct database access by agents
3. Unknown fields are rejected
4. Updates are explicit and versioned
5. History is never rewritten

---

## Usage Example

```python
from mcp_local_tasker import init, milestone_create, ticket_create, dep_add

# Initialize (creates .project/tasks.db)
init("/path/to/your/project")

# Create milestone
ms = milestone_create(
    title="Q1 2025 Release",
    description="Ship new API",
    priority=10,
    status="planned"
)

# Create ticket
ticket = ticket_create(
    title="Add user authentication",
    milestone_id=ms["id"],
    description="Implement JWT auth",
    category="backend",
    priority=10,
    recommendations="Use JWT library",
    acceptance_criteria="Users can register, login, logout",
    status="todo"
)

# Create dependency: frontend depends on backend
frontend = ticket_create(
    title="Build login UI",
    milestone_id=ms["id"],
    description="Vue component",
    category="frontend",
    priority=5,
    status="todo"
)

dep_add(frontend["id"], ticket["id"], check_cycles=True)
```

---

## Available Tools

| Tool | Description |
|------|-------------|
| `init` | Initialize storage |
| `about` | Get server metadata and rules |
| `milestone_*` | CRUD for milestones |
| `ticket_*` | CRUD for tickets |
| `ticket_search` | Full-text search (FTS5) |
| `dep_*` | Manage dependencies |
| `ticket_graph` | Get dependency graph |
| `events_list` | Audit log |

---

## Philosophy

Agents need **stable memory**, not clever prompts.
