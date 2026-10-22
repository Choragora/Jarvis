from datetime import datetime, timezone

from jarvis.store import Store, next_occurrence


def test_memory_index_tracks_update_delete_and_reopen(tmp_path):
    path = tmp_path / "memory.sqlite3"
    db = Store(path)
    note = db.note("Preferências", "Respostas curtas em português", "user")
    assert db.notes("portugues")[0]["id"] == note["id"]
    db.note("Preferências", "Apenas factos verificados", "user", note["id"])
    assert not db.notes("curtas")
    assert db.notes("factos")[0]["id"] == note["id"]
    db.close()
    db = Store(path)
    assert db.notes("factos")[0]["source"] == "user"
    db.write("DELETE FROM notes WHERE id=?", (note["id"],))
    assert not db.notes("factos")
    db.close()


def test_fts_treats_query_as_data(tmp_path):
    db = Store(tmp_path / "m.db")
    db.note("Dados", "Texto seguro")
    assert isinstance(db.notes('" OR DROP TABLE notes; --'), list)
    assert len(db.notes()) == 1
    db.close()


def test_running_task_after_crash_is_unverified(tmp_path):
    path = tmp_path / "m.db"
    db = Store(path)
    task = db.task("file_create", {})
    db.task_status(task, "running")
    db.close()
    db = Store(path)
    assert db.query("SELECT status FROM tasks")[0]["status"] == "unverified"
    db.close()


def test_lisbon_dst_and_weekends():
    utc = timezone.utc
    assert next_occurrence(9, 0, [0, 1, 2, 3, 4], datetime(2026, 10, 23, 10, tzinfo=utc)) == datetime(
        2026, 10, 26, 9, tzinfo=utc
    )
    # The spring transition skips 01:30 Lisbon; choose the next real day, not 02:30.
    assert next_occurrence(1, 30, list(range(7)), datetime(2026, 3, 29, 0, tzinfo=utc)) == datetime(
        2026, 3, 30, 0, 30, tzinfo=utc
    )
    assert next_occurrence(9, 0, [0], datetime(2026, 7, 5, 12, tzinfo=utc)) == datetime(
        2026, 7, 6, 8, tzinfo=utc
    )


def test_routine_claim_is_persistent_and_unique(tmp_path):
    db = Store(tmp_path / "m.db")
    r = db.routine("Manhã", 9, 0, list(range(7)), [])
    due = datetime(2026, 10, 22, 8, tzinfo=timezone.utc)
    db.write("UPDATE routines SET next_run=? WHERE id=?", (due.isoformat(), r["id"]))
    first = db.due_routines(due)
    assert len(first) == 1
    assert db.due_routines(due) == []
    assert db.query("SELECT * FROM routine_runs")[0]["task_id"] == first[0][0]
    db.close()


def test_missed_routine_does_not_replay(tmp_path):
    db = Store(tmp_path / "m.db")
    r = db.routine("Antiga", 9, 0, list(range(7)), [])
    db.write("UPDATE routines SET next_run=? WHERE id=?", ("2026-10-20T08:00:00+00:00", r["id"]))
    assert not db.due_routines(datetime(2026, 10, 22, 8, tzinfo=timezone.utc))
    assert db.query("SELECT status FROM tasks")[0]["status"] == "blocked"
    db.close()


def test_routine_edit_preserves_identity_and_pause(tmp_path):
    db = Store(tmp_path / "m.db")
    r = db.routine("Original", 9, 0, [0, 1, 2, 3, 4], [])
    db.write("UPDATE routines SET enabled=0 WHERE id=?", (r["id"],))
    edited = db.edit_routine(
        r["id"],
        "Corrigida",
        10,
        30,
        [5, 6],
        [{"action": "app_open", "arguments": {"application": "notepad"}}],
    )
    assert edited["id"] == r["id"] and edited["enabled"] == 0
    assert edited["name"] == "Corrigida" and edited["hour"] == 10 and edited["minute"] == 30
    assert len(db.query("SELECT * FROM routines")) == 1
    db.close()
