import os
from typing import Optional

from mcp.server.fastmcp import FastMCP

from .constants import (
    ALLOWED_CATEGORY,
    ALLOWED_MILESTONE_STATUS,
    ALLOWED_TICKET_STATUS,
    ensure_dir,
)
from .storage import Storage

mcp = FastMCP("local-task-tracker")

_storage: Optional[Storage] = None


def require_storage() -> Storage:
    global _storage
    if _storage is None:
        raise RuntimeError("Storage not initialized. Call init() first.")
    return _storage


@mcp.tool()
def about() -> dict:
    """
    Returns server metadata and rules. Always call this first to understand capabilities.
    
    Response includes:
    - name: server name
    - storage: backend type (SQLite + FTS5)
    - rules: core architectural rules
    - ticket_status: allowed values for ticket status
    - milestone_status: allowed values for milestone status
    - category: allowed ticket categories
    """
    return {
        "name": "local-task-tracker-mcp",
        "storage": "SQLite + FTS5",
        "rules": [
            "Milestones are flat (no nested milestones).",
            "Tickets may optionally belong to a milestone.",
            "Dependencies are directed edges: ticket depends on another ticket.",
            "Events are append-only for auditability.",
            "Ticket updates support optimistic concurrency with version.",
        ],
        "ticket_status": sorted(ALLOWED_TICKET_STATUS),
        "milestone_status": sorted(ALLOWED_MILESTONE_STATUS),
        "category": sorted(ALLOWED_CATEGORY),
    }


@mcp.tool()
def init(project_root: Optional[str] = None) -> dict:
    """
    Initialize storage. Must be called before any other operations.
    
    Creates SQLite database at <project_root>/.project/tasks.db
    If project_root is not provided, uses current working directory.
    
    Args:
        project_root: Absolute path to project root directory. Optional.
    
    Returns:
        dict with ok=true and db_path
    
    Example:
        init("/Users/me/projects/myapp")
    """
    global _storage
    root = project_root or os.getcwd()
    proj_dir = os.path.join(root, ".project")
    ensure_dir(proj_dir)
    db_path = os.path.join(proj_dir, "tasks.db")

    st = Storage(db_path=db_path)
    st.init_schema()
    _storage = st

    return {"ok": True, "db_path": db_path}


# ---- Milestone tools ----


@mcp.tool()
def milestone_create(
    title: str,
    description: str = "",
    priority: int = 0,
    status: str = "planned",
) -> dict:
    """
    Create a new milestone (milestone = sprint/release/goal container).
    
    Args:
        title: Short title for milestone (required)
        description: Detailed description (optional, default: "")
        priority: Integer priority, higher = more important (default: 0)
        status: Initial status (default: "planned")
            Allowed: planned, active, done, archived
    
    Returns:
        Created milestone dict with id, title, description, status, priority, 
        created_at, updated_at, version
    
    Example:
        milestone_create(title="Q1 2025 Release", description="Ship new API", priority=10, status="planned")
    """
    st = require_storage()
    return st.milestone_create(
        title=title,
        description=description,
        status=status,
        priority=int(priority),
    )


@mcp.tool()
def milestone_list(
    status: Optional[str] = None, include_counts: bool = True
) -> list[dict]:
    """
    List all milestones, optionally filtered by status.
    
    Args:
        status: Filter by status (optional)
            Allowed: planned, active, done, archived
        include_counts: Whether to include ticket counts (default: true)
            Adds ticket_count and open_ticket_count to each milestone
    
    Returns:
        List of milestone dicts, sorted by priority DESC, then updated_at DESC
    
    Example:
        milestone_list(status="active", include_counts=True)
    """
    st = require_storage()
    if status and status not in ALLOWED_MILESTONE_STATUS:
        raise ValueError(f"Invalid milestone status: {status}")
    return st.milestone_list(status=status, include_counts=bool(include_counts))


@mcp.tool()
def milestone_get(id: str) -> dict:
    """
    Get single milestone by ID.
    
    Args:
        id: Milestone ID (format: ms-xxxxxxxxxx)
    
    Returns:
        Milestone dict with all fields
    
    Raises:
        KeyError: If milestone not found
    
    Example:
        milestone_get(id="ms-a1b2c3d4e5")
    """
    st = require_storage()
    return st.milestone_get(id)


@mcp.tool()
def milestone_update(id: str, patch: dict) -> dict:
    """
    Update milestone fields (partial update).
    
    Args:
        id: Milestone ID to update
        patch: Dict with fields to update:
            - title: str
            - description: str  
            - status: planned | active | done | archived
            - priority: int
    
    Returns:
        Updated milestone dict
    
    Raises:
        KeyError: If milestone not found
        ValueError: If unknown fields or invalid status
    
    Example:
        milestone_update(id="ms-a1b2c3d4e5", patch={"status": "active", "priority": 5})
    """
    st = require_storage()
    return st.milestone_update(id, patch)


@mcp.tool()
def milestone_delete(id: str, force: bool = False) -> dict:
    """
    Delete or archive a milestone.
    
    Args:
        id: Milestone ID to delete
        force: If false (default), archives milestone (sets status='archived').
               If true, permanently deletes from database.
    
    Returns:
        dict with ok=true and status (if archived) or empty (if force deleted)
    
    Example:
        milestone_delete(id="ms-a1b2c3d4e5", force=False)  # archive
        milestone_delete(id="ms-a1b2c3d4e5", force=True)   # hard delete
    """
    st = require_storage()
    return st.milestone_delete(id, bool(force))


# ---- Ticket tools ----


@mcp.tool()
def ticket_create(
    title: str,
    milestone_id: Optional[str] = None,
    description: str = "",
    category: str = "other",
    priority: int = 0,
    recommendations: str = "",
    acceptance_criteria: str = "",
    status: str = "todo",
) -> dict:
    """
    Create a new ticket (task/issue/work item).
    
    Args:
        title: Short title (required)
        milestone_id: Optional milestone ID to assign ticket to (format: ms-xxxxxxxxxx)
        description: Detailed description of work (default: "")
        category: Type of work (default: "other")
            Allowed: backend, frontend, infra, docs, research, other
        priority: Integer priority, higher = more important (default: 0)
        recommendations: Suggestions/improvements for this ticket (default: "")
        acceptance_criteria: What needs to be done to close this ticket (default: "")
        status: Initial status (default: "todo")
            Allowed: todo, in_progress, blocked, done, canceled
    
    Returns:
        Created ticket dict with id, milestone_id, title, description, category,
        priority, status, version, depends_on[], blocked_by[], created_at, updated_at
    
    Example:
        ticket_create(
            title="Add user authentication",
            milestone_id="ms-a1b2c3d4e5",
            description="Implement JWT auth",
            category="backend",
            priority=10,
            recommendations="Use auth0 or implement JWT",
            acceptance_criteria="Users can register, login, logout",
            status="todo"
        )
    """
    st = require_storage()
    return st.ticket_create(
        milestone_id=milestone_id,
        title=title,
        description=description,
        category=category,
        priority=int(priority),
        recommendations=recommendations,
        acceptance_criteria=acceptance_criteria,
        status=status,
    )


@mcp.tool()
def ticket_get(id: str) -> dict:
    """
    Get single ticket by ID with dependency info.
    
    Args:
        id: Ticket ID (format: t-xxxxxxxxxx)
    
    Returns:
        Ticket dict including:
        - depends_on: list of ticket IDs this ticket depends on
        - blocked_by: list of ticket IDs that depend on this ticket
    
    Raises:
        KeyError: If ticket not found
    
    Example:
        ticket_get(id="t-a1b2c3d4e5")
    """
    st = require_storage()
    return st.ticket_get(id)


@mcp.tool()
def ticket_list(
    milestone_id: Optional[str] = None,
    status: Optional[str] = None,
    category: Optional[str] = None,
    include_deleted: bool = False,
    sort: str = "priority",
) -> list[dict]:
    """
    List tickets with optional filters.
    
    Args:
        milestone_id: Filter by milestone (optional, format: ms-xxxxxxxxxx)
        status: Filter by status (optional)
            Allowed: todo, in_progress, blocked, done, canceled
        category: Filter by category (optional)
            Allowed: backend, frontend, infra, docs, research, other
        include_deleted: Include soft-deleted tickets (default: false)
        sort: Sort order (default: "priority")
            Allowed: priority (priority DESC, updated_at DESC),
                    updated (updated_at DESC),
                    created (created_at DESC)
    
    Returns:
        List of ticket dicts
    
    Example:
        ticket_list(milestone_id="ms-a1b2c3d4e5", status="todo", sort="priority")
    """
    st = require_storage()
    if status and status not in ALLOWED_TICKET_STATUS:
        raise ValueError(f"Invalid ticket status: {status}")
    if category and category not in ALLOWED_CATEGORY:
        raise ValueError(f"Invalid category: {category}")
    if sort not in {"priority", "updated", "created"}:
        raise ValueError("sort must be one of: priority, updated, created")
    return st.ticket_list(
        milestone_id, status, category, bool(include_deleted), sort
    )


@mcp.tool()
def ticket_update(id: str, patch: dict, expected_version: Optional[int] = None) -> dict:
    """
    Update ticket fields (partial update). Supports optimistic concurrency.
    
    Args:
        id: Ticket ID to update
        patch: Dict with fields to update. Unknown fields are rejected.
            - title: str
            - description: str
            - status: todo | in_progress | blocked | done | canceled
            - priority: int
            - category: backend | frontend | infra | docs | research | other
            - recommendations: str
            - acceptance_criteria: str
            - milestone_id: str | null (assign to milestone or unassign)
        expected_version: If provided, update fails if version doesn't match
                         (optimistic locking). Use ticket_get to get current version.
    
    Returns:
        Updated ticket dict with incremented version
    
    Raises:
        KeyError: If ticket not found
        ValueError: If version mismatch (when expected_version provided) or invalid fields
    
    Example:
        ticket_update(id="t-a1b2c3d4e5", patch={"status": "in_progress", "priority": 5})
        ticket_update(id="t-a1b2c3d4e5", patch={"status": "done"}, expected_version=3)
    """
    st = require_storage()
    return st.ticket_update(id, patch, expected_version)


@mcp.tool()
def ticket_set_status(
    id: str, status: str, expected_version: Optional[int] = None
) -> dict:
    """
    Quick status change for ticket. Convenience wrapper around ticket_update.
    
    Args:
        id: Ticket ID
        status: New status
            Allowed: todo, in_progress, blocked, done, canceled
        expected_version: Optional version for optimistic locking
    
    Returns:
        Updated ticket dict
    
    Example:
        ticket_set_status(id="t-a1b2c3d4e5", status="in_progress")
    """
    st = require_storage()
    return st.ticket_set_status(id, status, expected_version)


@mcp.tool()
def ticket_delete(id: str, hard: bool = False) -> dict:
    """
    Delete a ticket.
    
    Args:
        id: Ticket ID to delete
        hard: If false (default), soft-deletes (marks is_deleted=1).
              If true, permanently removes from database.
    
    Returns:
        dict with ok=true and hard=true/false indicating delete type
    
    Example:
        ticket_delete(id="t-a1b2c3d4e5")        # soft delete
        ticket_delete(id="t-a1b2c3d4e5", hard=True)  # hard delete
    """
    st = require_storage()
    return st.ticket_delete(id, bool(hard))


@mcp.tool()
def ticket_search(
    query: str,
    milestone_id: Optional[str] = None,
    status: Optional[str] = None,
    category: Optional[str] = None,
    limit: int = 20,
) -> list[dict]:
    """
    Full-text search tickets using SQLite FTS5.
    
    Args:
        query: Search query using FTS5 MATCH syntax.
               Note: FTS5 is not SQL LIKE. Use AND, OR, NOT, prefix* (e.g., "auth*"), 
               or quoted phrases for exact matches.
               Use empty string "" to get all tickets matching filters.
               Examples: "API", "authentication", 'word1 OR word2', "auth*"
        milestone_id: Filter by milestone (optional)
        status: Filter by status (optional)
        category: Filter by category (optional)
        limit: Max results (default: 20, max: 100)
    
    Returns:
        List of ticket dicts with id, title, status, priority, category, 
        milestone_id, updated_at, and bm25 rank score
    
    Example:
        ticket_search(query="authentication", category="backend", limit=10)
        ticket_search(query="", status="todo", milestone_id="ms-a1b2c3d4e5")
    """
    st = require_storage()
    if status and status not in ALLOWED_TICKET_STATUS:
        raise ValueError(f"Invalid ticket status: {status}")
    if category and category not in ALLOWED_CATEGORY:
        raise ValueError(f"Invalid category: {category}")
    return st.ticket_search(query, milestone_id, status, category, int(limit))


# ---- Dependency tools ----


@mcp.tool()
def dep_add(
    ticket_id: str, depends_on_ticket_id: str, check_cycles: bool = True
) -> dict:
    """
    Add dependency: ticket_id depends on depends_on_ticket_id.
    
    Creates directed edge: ticket -> depends_on_ticket
    This means depends_on_ticket must be completed before ticket.
    
    Args:
        ticket_id: Dependent ticket (format: t-xxxxxxxxxx)
        depends_on_ticket_id: Ticket being depended on (format: t-xxxxxxxxxx)
        check_cycles: If true (default), rejects dependency if it would create cycle
    
    Returns:
        dict with ok=true
    
    Raises:
        KeyError: If either ticket not found
        ValueError: If self-dependency or cycle detected
    
    Example:
        dep_add(ticket_id="t-frontend", depends_on_ticket_id="t-backend")
    """
    st = require_storage()
    return st.dep_add(ticket_id, depends_on_ticket_id, bool(check_cycles))


@mcp.tool()
def dep_remove(ticket_id: str, depends_on_ticket_id: str) -> dict:
    """
    Remove dependency between two tickets.
    
    Args:
        ticket_id: Dependent ticket
        depends_on_ticket_id: Ticket being depended on
    
    Returns:
        dict with ok=true
    
    Example:
        dep_remove(ticket_id="t-frontend", depends_on_ticket_id="t-backend")
    """
    st = require_storage()
    return st.dep_remove(ticket_id, depends_on_ticket_id)


@mcp.tool()
def dep_list(ticket_id: str) -> dict:
    """
    List all dependencies for a ticket.
    
    Args:
        ticket_id: Ticket ID
    
    Returns:
        dict with:
        - depends_on: list of ticket IDs this ticket depends on
        - blocked_by: list of ticket IDs that depend on this ticket
    
    Example:
        dep_list(ticket_id="t-a1b2c3d4e5")
    """
    st = require_storage()
    return st.dep_list(ticket_id)


@mcp.tool()
def ticket_graph(milestone_id: Optional[str] = None, depth: int = 5) -> dict:
    """
    Get graph representation of tickets and dependencies.
    
    Useful for visualization or analyzing dependency chains.
    
    Args:
        milestone_id: Filter to single milestone (optional)
        depth: Maximum depth for graph traversal (default: 5, max: 50).
               Note: depth does NOT currently limit traversal - used as metadata only.
    
    Returns:
        dict with:
        - nodes: list of ticket dicts (id, title, status, priority, category, milestone_id)
        - edges: list of dependency edges [{"from": ticket_id, "to": depends_on_id}, ...]
        - depth: the depth parameter
    
    Example:
        ticket_graph(milestone_id="ms-a1b2c3d4e5", depth=10)
    """
    st = require_storage()
    return st.ticket_graph(milestone_id, int(depth))


# ---- Events ----


@mcp.tool()
def events_list(
    entity_type: Optional[str] = None,
    entity_id: Optional[str] = None,
    limit: int = 50,
) -> list[dict]:
    """
    List audit log events (append-only event store).
    
    Tracks all changes to milestones and tickets. Events are returned ordered by created_at DESC.
    
    Args:
        entity_type: Filter by entity type (optional)
            Allowed: milestone, ticket
        entity_id: Filter by specific entity ID (optional)
        limit: Max events to return (default: 50, max: 200)
    
    Returns:
        List of event dicts with:
        - id: event ID
        - entity_type: milestone or ticket
        - entity_id: ID of affected entity
        - event_type: create, update, delete, archive, dependency_add, dependency_remove
        - payload: dict with change details
        - created_at: Unix timestamp
    
    Example:
        events_list(entity_type="ticket", limit=20)
        events_list(entity_id="ms-a1b2c3d4e5")
    """
    st = require_storage()
    if entity_type and entity_type not in {"milestone", "ticket"}:
        raise ValueError("entity_type must be milestone or ticket")
    return st.events_list(entity_type, entity_id, int(limit))
