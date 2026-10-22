from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def next_occurrence(hour: int, minute: int, weekdays: list[int], after: datetime) -> datetime:
    """Find a real local time; skip DST gaps and choose the first repeated occurrence."""
    zone = ZoneInfo("Europe/Lisbon")
    local = after.astimezone(zone)
    for day in range(9):
        date = local.date() + timedelta(days=day)
        candidate = datetime(date.year, date.month, date.day, hour, minute, tzinfo=zone, fold=0)
        utc = candidate.astimezone(timezone.utc)
        if candidate.weekday() in weekdays and utc > after and utc.astimezone(zone).hour == hour:
            return utc
    raise ValueError("Não foi possível calcular a próxima execução.")


class Store:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
        PRAGMA journal_mode=WAL;
        CREATE TABLE IF NOT EXISTS notes(id TEXT PRIMARY KEY, title TEXT, body TEXT, source TEXT, updated TEXT);
        CREATE VIRTUAL TABLE IF NOT EXISTS notes_fts USING fts5(title, body, content='notes', content_rowid='rowid', tokenize='unicode61 remove_diacritics 2');
        CREATE TRIGGER IF NOT EXISTS notes_ai AFTER INSERT ON notes BEGIN
          INSERT INTO notes_fts(rowid,title,body) VALUES(new.rowid,new.title,new.body); END;
        CREATE TRIGGER IF NOT EXISTS notes_ad AFTER DELETE ON notes BEGIN
          INSERT INTO notes_fts(notes_fts,rowid,title,body) VALUES('delete',old.rowid,old.title,old.body); END;
        CREATE TRIGGER IF NOT EXISTS notes_au AFTER UPDATE ON notes BEGIN
          INSERT INTO notes_fts(notes_fts,rowid,title,body) VALUES('delete',old.rowid,old.title,old.body);
          INSERT INTO notes_fts(rowid,title,body) VALUES(new.rowid,new.title,new.body); END;
        CREATE TABLE IF NOT EXISTS tasks(id TEXT PRIMARY KEY, action TEXT, args TEXT, status TEXT, result TEXT, created TEXT, updated TEXT);
        CREATE TABLE IF NOT EXISTS routines(id TEXT PRIMARY KEY, name TEXT, hour INTEGER, minute INTEGER, weekdays TEXT, steps TEXT, enabled INTEGER, next_run TEXT);
        CREATE TABLE IF NOT EXISTS routine_runs(routine_id TEXT, scheduled TEXT, task_id TEXT, PRIMARY KEY(routine_id,scheduled));
        CREATE TABLE IF NOT EXISTS messages(id TEXT PRIMARY KEY, role TEXT, text TEXT, created TEXT);
        CREATE TABLE IF NOT EXISTS metrics(id TEXT PRIMARY KEY, data TEXT);
        """)
        self.db.execute("UPDATE tasks SET status='unverified',updated=? WHERE status='running'", (now(),))
        self.db.execute(
            "UPDATE tasks SET status='blocked',result=?,updated=? WHERE status='waiting'",
            (
                json.dumps({"reason": "Reinício: pedido anterior pendente; reobserve e submeta novamente."}),
                now(),
            ),
        )
        self.db.commit()

    def query(self, sql: str, params=()) -> list[dict]:
        with self.lock:
            return [dict(row) for row in self.db.execute(sql, params).fetchall()]

    def write(self, sql: str, params=()) -> None:
        with self.lock, self.db:
            self.db.execute(sql, params)

    def note(self, title: str, body: str, source="user", note_id: str | None = None) -> dict:
        note_id = note_id or str(uuid.uuid4())
        self.write(
            "INSERT INTO notes VALUES(?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET title=excluded.title,body=excluded.body,source=excluded.source,updated=excluded.updated",
            (note_id, title, body, source, now()),
        )
        return self.query("SELECT * FROM notes WHERE id=?", (note_id,))[0]

    def notes(self, search: str = "") -> list[dict]:
        import re

        terms = re.findall(r"\w+", search, re.UNICODE)[:20]
        if not terms:
            return self.query("SELECT * FROM notes ORDER BY updated DESC LIMIT 200")
        match = " OR ".join('"' + t + '"' for t in terms)
        return self.query(
            "SELECT n.* FROM notes n JOIN notes_fts f ON n.rowid=f.rowid WHERE notes_fts MATCH ? ORDER BY rank LIMIT 30",
            (match,),
        )

    def message(self, role: str, text: str) -> dict:
        msg = {"id": str(uuid.uuid4()), "role": role, "text": text, "created": now()}
        self.write("INSERT INTO messages VALUES(:id,:role,:text,:created)", msg)
        return msg

    def task(self, action: str, args: dict) -> str:
        tid = str(uuid.uuid4())
        self.write(
            "INSERT INTO tasks VALUES(?,?,?,?,?,?,?)",
            (tid, action, json.dumps(args), "waiting", None, now(), now()),
        )
        return tid

    def task_status(self, tid: str, status: str, result=None):
        self.write(
            "UPDATE tasks SET status=?,result=?,updated=? WHERE id=?",
            (status, json.dumps(result, ensure_ascii=False), now(), tid),
        )

    def routine(self, name: str, hour: int, minute: int, weekdays: list[int], steps: list[dict]) -> dict:
        rid = str(uuid.uuid4())
        due = next_occurrence(hour, minute, weekdays, datetime.now(timezone.utc)).isoformat()
        self.write(
            "INSERT INTO routines VALUES(?,?,?,?,?,?,?,?)",
            (rid, name, hour, minute, json.dumps(weekdays), json.dumps(steps), 1, due),
        )
        return self.query("SELECT * FROM routines WHERE id=?", (rid,))[0]

    def due_routines(self, at: datetime) -> list[tuple[str, list[dict]]]:
        pending = []
        with self.lock, self.db:
            rows = self.db.execute(
                "SELECT * FROM routines WHERE enabled=1 AND next_run<=?", (at.isoformat(),)
            ).fetchall()
            for row in rows:
                tid = str(uuid.uuid4())
                claimed = self.db.execute(
                    "INSERT OR IGNORE INTO routine_runs VALUES(?,?,?)", (row["id"], row["next_run"], tid)
                ).rowcount
                due = next_occurrence(row["hour"], row["minute"], json.loads(row["weekdays"]), at).isoformat()
                self.db.execute("UPDATE routines SET next_run=? WHERE id=?", (due, row["id"]))
                # Missed runs older than 15 minutes are recorded, never silently replayed.
                missed = (at - datetime.fromisoformat(row["next_run"])).total_seconds() > 900
                if claimed:
                    self.db.execute(
                        "INSERT INTO tasks VALUES(?,?,?,?,?,?,?)",
                        (
                            tid,
                            "workflow",
                            row["steps"],
                            "blocked" if missed else "waiting",
                            json.dumps({"reason": "Execução perdida; retome manualmente."})
                            if missed
                            else None,
                            now(),
                            now(),
                        ),
                    )
                    if not missed:
                        pending.append((tid, json.loads(row["steps"])))
        return pending

    def edit_routine(self, rid, name, hour, minute, weekdays, steps):
        due = next_occurrence(hour, minute, weekdays, datetime.now(timezone.utc)).isoformat()
        self.write(
            "UPDATE routines SET name=?,hour=?,minute=?,weekdays=?,steps=?,next_run=? WHERE id=?",
            (name, hour, minute, json.dumps(weekdays), json.dumps(steps), due, rid),
        )
        return self.query("SELECT * FROM routines WHERE id=?", (rid,))[0]

    def close(self):
        self.db.close()
