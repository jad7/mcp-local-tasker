import os
import tempfile
import pytest

from mcp_local_tasker import (
    Storage,
    milestone_create,
    milestone_list,
    milestone_get,
    milestone_update,
    milestone_delete,
    ticket_create,
    ticket_get,
    ticket_list,
    ticket_update,
    ticket_delete,
    ticket_search,
    dep_add,
    dep_remove,
    dep_list,
    ticket_graph,
    events_list,
)


@pytest.fixture
def storage():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        st = Storage(db_path=db_path)
        st.init_schema()
        yield st


def test_milestone_crud(storage):
    m = storage.milestone_create(
        title="Test Milestone",
        description="Test description",
        status="planned",
        priority=1
    )
    assert m["title"] == "Test Milestone"
    assert m["status"] == "planned"

    milestones = storage.milestone_list(status=None, include_counts=False)
    assert len(milestones) == 1

    m2 = storage.milestone_get(m["id"])
    assert m2["id"] == m["id"]

    m3 = storage.milestone_update(m["id"], {"title": "Updated", "status": "active"})
    assert m3["title"] == "Updated"
    assert m3["status"] == "active"

    result = storage.milestone_delete(m["id"], force=False)
    assert result["status"] == "archived"

    m4 = storage.milestone_create(title="To Delete", description="", status="planned", priority=0)
    result = storage.milestone_delete(m4["id"], force=True)
    assert result["ok"] is True


def test_milestone_list_with_counts(storage):
    ms = storage.milestone_create(title="MS1", description="", status="planned", priority=1)
    t1 = storage.ticket_create(ms["id"], "T1", "", "backend", 1, "", "", "todo")
    t2 = storage.ticket_create(ms["id"], "T2", "", "backend", 1, "", "", "done")

    milestones = storage.milestone_list(status=None, include_counts=True)
    assert len(milestones) == 1
    assert milestones[0]["ticket_count"] == 2
    assert milestones[0]["open_ticket_count"] == 1


def test_milestone_list_filtered(storage):
    storage.milestone_create(title="MS1", description="", status="planned", priority=1)
    storage.milestone_create(title="MS2", description="", status="done", priority=1)

    active = storage.milestone_list(status="active", include_counts=False)
    assert len(active) == 0

    planned = storage.milestone_list(status="planned", include_counts=False)
    assert len(planned) == 1


def test_milestone_update_no_changes(storage):
    m = storage.milestone_create(title="MS1", description="", status="planned", priority=0)
    m2 = storage.milestone_update(m["id"], {})
    assert m2["id"] == m["id"]


def test_milestone_update_invalid_status(storage):
    m = storage.milestone_create(title="MS1", description="", status="planned", priority=0)
    with pytest.raises(ValueError):
        storage.milestone_update(m["id"], {"status": "invalid"})


def test_milestone_update_invalid_field(storage):
    m = storage.milestone_create(title="MS1", description="", status="planned", priority=0)
    with pytest.raises(ValueError, match="Unknown fields"):
        storage.milestone_update(m["id"], {"invalid_field": "value"})


def test_milestone_get_not_found(storage):
    with pytest.raises(KeyError):
        storage.milestone_get("ms-nonexistent")


def test_milestone_delete_not_found(storage):
    with pytest.raises(KeyError):
        storage.milestone_delete("ms-nonexistent", force=True)


def test_ticket_crud(storage):
    ms = storage.milestone_create(title="MS1", description="", status="planned", priority=0)

    t = storage.ticket_create(
        milestone_id=ms["id"],
        title="Test Ticket",
        description="Description",
        category="backend",
        priority=5,
        recommendations="Recs",
        acceptance_criteria="AC",
        status="todo"
    )
    assert t["title"] == "Test Ticket"
    assert t["status"] == "todo"
    assert t["milestone_id"] == ms["id"]

    t2 = storage.ticket_get(t["id"])
    assert t2["depends_on"] == []
    assert t2["blocked_by"] == []

    t3 = storage.ticket_update(t["id"], {"status": "in_progress", "title": "Updated Title"}, None)
    assert t3["status"] == "in_progress"
    assert t3["title"] == "Updated Title"
    assert t3["version"] == 2

    tickets = storage.ticket_list(None, None, None, None, False, "priority")
    assert len(tickets) == 1

    result = storage.ticket_delete(t["id"], hard=False)
    assert result["ok"] is True

    t4 = storage.ticket_create(None, "To Delete", "", "other", 0, "", "", "todo")
    result = storage.ticket_delete(t4["id"], hard=True)
    assert result["ok"] is True


def test_ticket_create_with_invalid_milestone(storage):
    with pytest.raises(KeyError):
        storage.ticket_create(milestone_id="ms-invalid", title="T1", description="", category="backend", priority=0, recommendations="", acceptance_criteria="", status="todo")


def test_ticket_list_filters(storage):
    ms = storage.milestone_create(title="MS1", description="", status="planned", priority=0)
    t1 = storage.ticket_create(ms["id"], "T1", "", "backend", 1, "", "", "todo")
    t2 = storage.ticket_create(ms["id"], "T2", "", "frontend", 1, "", "", "done")

    by_milestone = storage.ticket_list(ms["id"], None, None, None, False, "priority")
    assert len(by_milestone) == 2

    by_status = storage.ticket_list(None, "done", None, None, False, "priority")
    assert len(by_status) == 1

    by_category = storage.ticket_list(None, None, None, "backend", False, "priority")
    assert len(by_category) == 1


def test_ticket_list_sorting(storage):
    t1 = storage.ticket_create(None, "T1", "", "backend", 1, "", "", "todo")
    t2 = storage.ticket_create(None, "T2", "", "backend", 10, "", "", "todo")

    by_priority = storage.ticket_list(None, None, None, None, False, "priority")
    assert by_priority[0]["id"] == t2["id"]

    by_created = storage.ticket_list(None, None, None, None, False, "created")
    assert len(by_created) == 2


def test_ticket_update_invalid_field(storage):
    t = storage.ticket_create(None, "T1", "", "backend", 0, "", "", "todo")
    with pytest.raises(ValueError, match="Unknown fields"):
        storage.ticket_update(t["id"], {"invalid": "value"}, None)


def test_ticket_update_invalid_status(storage):
    t = storage.ticket_create(None, "T1", "", "backend", 0, "", "", "todo")
    with pytest.raises(ValueError):
        storage.ticket_update(t["id"], {"status": "invalid"}, None)


def test_ticket_update_invalid_category(storage):
    t = storage.ticket_create(None, "T1", "", "backend", 0, "", "", "todo")
    with pytest.raises(ValueError):
        storage.ticket_update(t["id"], {"category": "invalid"}, None)


def test_ticket_set_status(storage):
    t = storage.ticket_create(None, "T1", "", "backend", 0, "", "", "todo")
    t2 = storage.ticket_set_status(t["id"], "in_progress", None)
    assert t2["status"] == "in_progress"


def test_ticket_delete_not_found(storage):
    with pytest.raises(KeyError):
        storage.ticket_delete("t-nonexistent", True)


def test_ticket_search_fts(storage):
    t1 = storage.ticket_create(None, "Python API endpoint", "Create REST API", "backend", 0, "", "", "todo")
    t2 = storage.ticket_create(None, "Vue Component", "UI Component", "frontend", 0, "", "", "todo")

    results = storage.ticket_search("API", None, None, None, 10)
    assert len(results) == 1
    assert results[0]["id"] == t1["id"]


def test_ticket_search_no_query(storage):
    t1 = storage.ticket_create(None, "T1", "", "backend", 0, "", "", "todo")
    t2 = storage.ticket_create(None, "T2", "", "frontend", 0, "", "", "todo")

    results = storage.ticket_search("", None, None, "frontend", 10)
    assert len(results) == 1
    assert results[0]["id"] == t2["id"]


def test_ticket_search_limit(storage):
    for i in range(25):
        storage.ticket_create(None, f"T{i}", "", "backend", i, "", "", "todo")

    results = storage.ticket_search("", None, None, None, 5)
    assert len(results) == 5


def test_dependencies(storage):
    t1 = storage.ticket_create(None, "Ticket 1", "", "backend", 0, "", "", "todo")
    t2 = storage.ticket_create(None, "Ticket 2", "", "frontend", 0, "", "", "todo")

    result = storage.dep_add(t2["id"], t1["id"], check_cycles=True)
    assert result["ok"] is True

    deps = storage.dep_list(t2["id"])
    assert t1["id"] in deps["depends_on"]

    blocked = storage.dep_list(t1["id"])
    assert t2["id"] in blocked["blocked_by"]

    result = storage.dep_remove(t2["id"], t1["id"])
    assert result["ok"] is True


def test_dep_add_same_ticket(storage):
    t1 = storage.ticket_create(None, "T1", "", "backend", 0, "", "", "todo")
    with pytest.raises(ValueError, match="cannot depend on itself"):
        storage.dep_add(t1["id"], t1["id"], True)


def test_dep_add_invalid_ticket(storage):
    t1 = storage.ticket_create(None, "T1", "", "backend", 0, "", "", "todo")
    with pytest.raises(KeyError):
        storage.dep_add(t1["id"], "t-nonexistent", True)


def test_dep_remove_nonexistent(storage):
    result = storage.dep_remove("t-a", "t-b")
    assert result["ok"] is True


def test_cycle_detection(storage):
    t1 = storage.ticket_create(None, "T1", "", "backend", 0, "", "", "todo")
    t2 = storage.ticket_create(None, "T2", "", "backend", 0, "", "", "todo")
    t3 = storage.ticket_create(None, "T3", "", "backend", 0, "", "", "todo")

    storage.dep_add(t2["id"], t1["id"], check_cycles=True)
    storage.dep_add(t3["id"], t2["id"], check_cycles=True)

    with pytest.raises(ValueError, match="cycle"):
        storage.dep_add(t1["id"], t3["id"], check_cycles=True)


def test_cycle_detection_disabled(storage):
    t1 = storage.ticket_create(None, "T1", "", "backend", 0, "", "", "todo")
    t2 = storage.ticket_create(None, "T2", "", "backend", 0, "", "", "todo")

    storage.dep_add(t2["id"], t1["id"], check_cycles=False)
    result = storage.dep_add(t1["id"], t2["id"], check_cycles=False)
    assert result["ok"] is True


def test_ticket_graph(storage):
    ms = storage.milestone_create(title="MS1", description="", status="planned", priority=0)
    t1 = storage.ticket_create(ms["id"], "T1", "", "backend", 0, "", "", "todo")
    t2 = storage.ticket_create(ms["id"], "T2", "", "backend", 0, "", "", "todo")

    storage.dep_add(t2["id"], t1["id"], check_cycles=True)

    graph = storage.ticket_graph(ms["id"], 5)
    assert len(graph["nodes"]) == 2
    assert len(graph["edges"]) == 1
    assert graph["edges"][0]["from"] == t2["id"]
    assert graph["edges"][0]["to"] == t1["id"]


def test_ticket_graph_no_milestone(storage):
    t1 = storage.ticket_create(None, "T1", "", "backend", 0, "", "", "todo")
    t2 = storage.ticket_create(None, "T2", "", "backend", 0, "", "", "todo")

    storage.dep_add(t2["id"], t1["id"], check_cycles=True)

    graph = storage.ticket_graph(None, 5)
    assert len(graph["nodes"]) == 2


def test_ticket_graph_depth_limit(storage):
    for i in range(10):
        storage.ticket_create(None, f"T{i}", "", "backend", 0, "", "", "todo")

    graph = storage.ticket_graph(None, 1)
    assert graph["depth"] == 1

    graph = storage.ticket_graph(None, 100)
    assert graph["depth"] == 50


def test_events(storage):
    m = storage.milestone_create(title="MS1", description="", status="planned", priority=0)

    events = storage.events_list("milestone", None, 10)
    assert len(events) == 1
    assert events[0]["event_type"] == "create"

    events = storage.events_list(None, m["id"], 10)
    assert len(events) == 1


def test_events_limit(storage):
    for i in range(10):
        storage.milestone_create(title=f"MS{i}", description="", status="planned", priority=0)

    events = storage.events_list(None, None, 5)
    assert len(events) == 5


def test_events_no_results(storage):
    events = storage.events_list("milestone", "ms-nonexistent", 10)
    assert len(events) == 0


def test_version_conflict(storage):
    t = storage.ticket_create(None, "T1", "", "backend", 0, "", "", "todo")
    original_version = t["version"]

    t2 = storage.ticket_update(t["id"], {"status": "in_progress"}, None)
    assert t2["version"] == original_version + 1

    with pytest.raises(ValueError, match="Version mismatch"):
        storage.ticket_update(t["id"], {"status": "done"}, original_version)

    t3 = storage.ticket_update(t["id"], {"status": "done"}, t2["version"])
    assert t3["version"] == t2["version"] + 1


def test_version_conflict_not_found(storage):
    with pytest.raises(KeyError):
        storage.ticket_update("t-nonexistent", {"status": "done"}, 1)


def test_invalid_status(storage):
    with pytest.raises(ValueError, match="Invalid milestone status"):
        storage.milestone_create(title="MS1", description="", status="invalid_status", priority=0)

    with pytest.raises(ValueError, match="Invalid ticket status"):
        storage.ticket_create(None, "T1", "", "backend", 0, "", "", "invalid_status")


def test_invalid_category(storage):
    with pytest.raises(ValueError, match="Invalid category"):
        storage.ticket_create(None, "T1", "", "invalid_cat", 0, "", "", "todo")


def test_reachable_function(storage):
    t1 = storage.ticket_create(None, "T1", "", "backend", 0, "", "", "todo")
    t2 = storage.ticket_create(None, "T2", "", "backend", 0, "", "", "todo")
    t3 = storage.ticket_create(None, "T3", "", "backend", 0, "", "", "todo")

    storage.dep_add(t2["id"], t1["id"], False)
    storage.dep_add(t3["id"], t2["id"], False)

    with storage.connect() as conn:
        assert storage._reachable(conn, t3["id"], t1["id"], 100) is True
        assert storage._reachable(conn, t1["id"], t3["id"], 100) is False


def test_fts_upsert_on_update(storage):
    t = storage.ticket_create(None, "UniqueWord123 Title", "Original desc", "backend", 0, "", "", "todo")

    storage.ticket_update(t["id"], {"title": "Different456 Title"}, None)

    results = storage.ticket_search("Different456", None, None, None, 10)
    assert len(results) == 1

    results = storage.ticket_search("UniqueWord123", None, None, None, 10)
    assert len(results) == 0


def test_soft_delete_removes_from_fts(storage):
    t = storage.ticket_create(None, "To Delete", "description", "backend", 0, "", "", "todo")

    storage.ticket_delete(t["id"], False)

    results = storage.ticket_search("Delete", None, None, None, 10)
    assert len(results) == 0


def test_ticket_get_not_found(storage):
    with pytest.raises(KeyError):
        storage.ticket_get("t-nonexistent")


def test_ticket_update_no_fields(storage):
    t = storage.ticket_create(None, "T1", "", "backend", 0, "", "", "todo")
    t2 = storage.ticket_update(t["id"], {}, None)
    assert t2["id"] == t["id"]


def test_ticket_list_include_deleted(storage):
    t = storage.ticket_create(None, "T1", "", "backend", 0, "", "", "todo")
    storage.ticket_delete(t["id"], False)

    deleted = storage.ticket_list(None, None, None, None, True, "priority")
    assert len(deleted) == 1

    active = storage.ticket_list(None, None, None, None, False, "priority")
    assert len(active) == 0


def test_ticket_list_statuses_filter(storage):
    t1 = storage.ticket_create(None, "T1", "", "backend", 0, "", "", "todo")
    t2 = storage.ticket_create(None, "T2", "", "backend", 0, "", "", "in_progress")
    t3 = storage.ticket_create(None, "T3", "", "backend", 0, "", "", "done")
    t4 = storage.ticket_create(None, "T4", "", "backend", 0, "", "", "canceled")

    # All open tickets
    open_tickets = storage.ticket_list(None, None, ["todo", "in_progress", "blocked"], None, False, "created")
    assert len(open_tickets) == 2
    ids = [t["id"] for t in open_tickets]
    assert t1["id"] in ids
    assert t2["id"] in ids

    # Only done
    done = storage.ticket_list(None, None, ["done"], None, False, "created")
    assert len(done) == 1
    assert done[0]["id"] == t3["id"]


def test_milestone_not_found_error(storage):
    with pytest.raises(KeyError):
        storage.milestone_get("ms-doesnotexist")


def test_ticket_search_by_status_and_category(storage):
    t1 = storage.ticket_create(None, "Backend task one", "", "backend", 0, "", "", "todo")
    t2 = storage.ticket_create(None, "Backend task two", "", "backend", 0, "", "", "done")
    t3 = storage.ticket_create(None, "Frontend task", "", "frontend", 0, "", "", "todo")

    results = storage.ticket_search("task one", None, None, None, 10)
    assert len(results) == 1
    assert results[0]["id"] == t1["id"]


def test_ticket_graph_all_milestones(storage):
    ms1 = storage.milestone_create(title="MS1", description="", status="planned", priority=0)
    ms2 = storage.milestone_create(title="MS2", description="", status="planned", priority=0)
    t1 = storage.ticket_create(ms1["id"], "T1", "", "backend", 0, "", "", "todo")
    t2 = storage.ticket_create(ms2["id"], "T2", "", "backend", 0, "", "", "todo")

    graph = storage.ticket_graph(None, 5)
    assert len(graph["nodes"]) == 2
