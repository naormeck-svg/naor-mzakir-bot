"""
Database layer using Turso HTTP v2 API (no native libsql extension required).
"""
import httpx
from datetime import datetime, date, timedelta
from config import TURSO_DATABASE_URL, TURSO_AUTH_TOKEN


def _http_url():
    url = TURSO_DATABASE_URL
    for prefix in ("libsql://", "wss://", "ws://"):
        if url.startswith(prefix):
            url = "https://" + url[len(prefix):]
            break
    return url.rstrip("/") + "/v2/pipeline"


def _to_arg(v):
    if v is None:
        return {"type": "null", "value": None}
    if isinstance(v, bool):
        return {"type": "integer", "value": str(int(v))}
    if isinstance(v, int):
        return {"type": "integer", "value": str(v)}
    if isinstance(v, float):
        return {"type": "real", "value": str(v)}
    return {"type": "text", "value": str(v)}


def _from_cell(cell):
    if cell is None or cell.get("type") == "null":
        return None
    t = cell.get("type")
    v = cell.get("value")
    if t == "integer":
        return int(v)
    if t == "real":
        return float(v)
    return v


def _run(sql, params=()):
    payload = {
        "requests": [
            {
                "type": "execute",
                "stmt": {
                    "sql": sql,
                    "args": [_to_arg(p) for p in params],
                }
            },
            {"type": "close"}
        ]
    }
    resp = httpx.post(
        _http_url(),
        headers={
            "Authorization": f"Bearer {TURSO_AUTH_TOKEN}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    result_entry = data["results"][0]
    if result_entry.get("type") == "error":
        raise RuntimeError(result_entry["error"]["message"])
    result = result_entry["response"]["result"]
    raw_rows = result.get("rows", [])
    rows = [tuple(_from_cell(cell) for cell in row) for row in raw_rows]
    last_id = result.get("last_insert_rowid")
    return rows, (int(last_id) if last_id is not None else None)


class _Cursor:
    def __init__(self, rows, lastrowid):
        self._rows = rows
        self.lastrowid = lastrowid

    def fetchall(self):
        return self._rows

    def fetchone(self):
        return self._rows[0] if self._rows else None


class _Conn:
    def execute(self, sql, params=()):
        rows, lastrowid = _run(sql, params)
        return _Cursor(rows, lastrowid)

    def commit(self):
        pass


_conn = None


def get_conn():
    global _conn
    if _conn is None:
        _conn = _Conn()
    return _conn


def init_db():
    conn = get_conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER NOT NULL,
            type TEXT NOT NULL,
            content TEXT NOT NULL,
            due_date TEXT,
            due_time TEXT,
            recurring TEXT,
            done INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now')),
            reminded_at TEXT
        )
    """)
    conn.commit()
    # Add person column if not yet present (idempotent migration)
    try:
        conn.execute("ALTER TABLE items ADD COLUMN person TEXT")
        conn.commit()
    except Exception:
        pass  # Column already exists


def save_item(chat_id, type_, content, due_date=None, due_time=None, recurring=None, person=None):
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO items (chat_id, type, content, due_date, due_time, recurring, person) VALUES (?,?,?,?,?,?,?)",
        (chat_id, type_, content, due_date, due_time, recurring, person)
    )
    conn.commit()
    return cur.lastrowid


def get_items(chat_id, type_=None, done=0):
    conn = get_conn()
    if type_:
        return conn.execute(
            "SELECT * FROM items WHERE chat_id=? AND type=? AND done=? ORDER BY due_date, due_time",
            (chat_id, type_, done)
        ).fetchall()
    return conn.execute(
        "SELECT * FROM items WHERE chat_id=? AND done=? ORDER BY type, due_date, due_time",
        (chat_id, done)
    ).fetchall()


def get_today_items(chat_id):
    today = date.today().isoformat()
    conn = get_conn()
    return conn.execute(
        "SELECT * FROM items WHERE chat_id=? AND due_date=? AND done=0 ORDER BY due_time",
        (chat_id, today)
    ).fetchall()


def mark_done(item_id):
    conn = get_conn()
    conn.execute("UPDATE items SET done=1 WHERE id=?", (item_id,))
    conn.commit()


def snooze_item(item_id, hours=1):
    conn = get_conn()
    now = datetime.now()
    new_dt = now + timedelta(hours=hours)
    conn.execute(
        "UPDATE items SET due_date=?, due_time=?, reminded_at=NULL WHERE id=?",
        (new_dt.date().isoformat(), new_dt.strftime("%H:%M"), item_id)
    )
    conn.commit()


def postpone_to_tomorrow(item_id):
    conn = get_conn()
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    conn.execute("UPDATE items SET due_date=?, reminded_at=NULL WHERE id=?", (tomorrow, item_id))
    conn.commit()


def get_due_reminders():
    conn = get_conn()
    now = datetime.now()
    today = now.date().isoformat()
    current_time = now.strftime("%H:%M")
    return conn.execute(
        """SELECT * FROM items WHERE type='reminder' AND done=0
        AND due_date <= ? AND (due_time IS NULL OR due_time <= ?)
        AND (reminded_at IS NULL OR reminded_at < date('now', '-23 hours'))""",
        (today, current_time)
    ).fetchall()


def mark_reminded(item_id):
    conn = get_conn()
    conn.execute("UPDATE items SET reminded_at=datetime('now') WHERE id=?", (item_id,))
    conn.commit()


def handle_recurring(item_id):
    conn = get_conn()
    row = conn.execute("SELECT * FROM items WHERE id=?", (item_id,)).fetchone()
    if not row:
        return
    recurring = row[6]
    if not recurring:
        return
    due_date_str = row[3]
    if not due_date_str:
        return
    due_date_val = date.fromisoformat(due_date_str)
    if recurring == "daily":
        next_date = due_date_val + timedelta(days=1)
    elif recurring.startswith("weekly:"):
        next_date = due_date_val + timedelta(weeks=1)
    elif recurring == "monthly":
        next_date = (due_date_val.replace(month=due_date_val.month % 12 + 1)
                     if due_date_val.month < 12
                     else due_date_val.replace(year=due_date_val.year + 1, month=1))
    else:
        return
    conn.execute(
        "UPDATE items SET due_date=?, reminded_at=NULL WHERE id=?",
        (next_date.isoformat(), item_id)
    )
    conn.commit()


def get_all_chat_ids():
    conn = get_conn()
    rows = conn.execute("SELECT DISTINCT chat_id FROM items").fetchall()
    return [r[0] for r in rows]


def get_summary_for_digest(chat_id):
    today = date.today().isoformat()
    conn = get_conn()
    tasks_today = conn.execute(
        "SELECT COUNT(*) FROM items WHERE chat_id=? AND type='task' AND due_date=? AND done=0",
        (chat_id, today)
    ).fetchone()[0]
    reminders_today = conn.execute(
        "SELECT COUNT(*) FROM items WHERE chat_id=? AND type='reminder' AND due_date=? AND done=0",
        (chat_id, today)
    ).fetchone()[0]
    overdue = conn.execute(
        "SELECT COUNT(*) FROM items WHERE chat_id=? AND done=0 AND due_date < ? AND due_date IS NOT NULL",
        (chat_id, today)
    ).fetchone()[0]
    return tasks_today, reminders_today, overdue


def export_all(chat_id):
    conn = get_conn()
    return conn.execute(
        "SELECT id, type, content, due_date, due_time, recurring, done, created_at FROM items WHERE chat_id=? ORDER BY created_at DESC",
        (chat_id,)
    ).fetchall()


def count_items_by_type(chat_id: int, type_: str = None) -> int:
    """Count open items by type (or all if type_ is None/all)."""
    conn = get_conn()
    if type_ is None or type_ == "all":
        row = conn.execute(
            "SELECT COUNT(*) FROM items WHERE chat_id=? AND done=0",
            (chat_id,)
        ).fetchone()
    else:
        row = conn.execute(
            "SELECT COUNT(*) FROM items WHERE chat_id=? AND type=? AND done=0",
            (chat_id, type_)
        ).fetchone()
    return row[0] if row else 0


def delete_items_by_type(chat_id: int, type_: str = None) -> int:
    """Delete open items by type. Returns count deleted."""
    count = count_items_by_type(chat_id, type_)
    conn = get_conn()
    if type_ is None or type_ == "all":
        conn.execute(
            "DELETE FROM items WHERE chat_id=? AND done=0",
            (chat_id,)
        )
    else:
        conn.execute(
            "DELETE FROM items WHERE chat_id=? AND type=? AND done=0",
            (chat_id, type_)
        )
    return count


def delete_item(item_id: int):
    """Permanently delete a single item by ID."""
    conn = get_conn()
    conn.execute("DELETE FROM items WHERE id=?", (item_id,))


# ── People Agenda ──────────────────────────────────────────────

def get_people(chat_id):
    """Return list of (person_name, count) for persons with open agenda items."""
    conn = get_conn()
    return conn.execute(
        "SELECT person, COUNT(*) FROM items WHERE chat_id=? AND type='agenda' AND person IS NOT NULL AND done=0 GROUP BY person ORDER BY person",
        (chat_id,)
    ).fetchall()


def get_items_by_person(chat_id, person):
    """Return open agenda items for a specific person."""
    conn = get_conn()
    return conn.execute(
        "SELECT * FROM items WHERE chat_id=? AND type='agenda' AND person=? AND done=0 ORDER BY created_at",
        (chat_id, person)
    ).fetchall()


def find_similar_person(chat_id, name):
    """Return an existing person name if a similar (but not identical) one exists, else None."""
    conn = get_conn()
    rows = conn.execute(
        "SELECT DISTINCT person FROM items WHERE chat_id=? AND person IS NOT NULL",
        (chat_id,)
    ).fetchall()
    name_lower = name.strip().lower()
    for row in rows:
        existing = row[0]
        existing_lower = existing.strip().lower()
        if existing_lower == name_lower:
            return None  # Exact match — no dedup question needed
        if name_lower in existing_lower or existing_lower in name_lower:
            return existing
    return None


def merge_person(chat_id, old_name, new_name):
    """Rename all items from old_name to new_name for this chat."""
    conn = get_conn()
    conn.execute(
        "UPDATE items SET person=? WHERE chat_id=? AND person=?",
        (new_name, chat_id, old_name)
    )
    conn.commit()
