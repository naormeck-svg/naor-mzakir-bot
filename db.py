"""
Database layer using Turso HTTP v2 API (no native libsql extension required).
"""
import httpx
from datetime import datetime, date, timedelta
from config import TURSO_DATABASE_URL, TURSO_AUTH_TOKEN

# Convert libsql:// URL to https:// for HTTP API
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
    """Execute a single SQL statement via Turso HTTP API. Returns (rows, lastrowid)."""
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


# --- Minimal cursor/connection shim so callers don't need to change ---

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
        pass  # HTTP API auto-commits each statement


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
            reminded_at TEXT,
            person TEXT
        )
    """)
    # Migration: add person column if not present
    try:
        conn.execute("ALTER TABLE items ADD COLUMN person TEXT")
    except Exception:
        pass  # Column already exists
    conn.execute("""
        CREATE TABLE IF NOT EXISTS user_profiles (
            chat_id INTEGER PRIMARY KEY,
            name TEXT NOT NULL
        )
    """)
    conn.commit()


def save_item(chat_id: int, type_: str, content: str,
              due_date: str = None, due_time: str = None, recurring: str = None,
              person: str = None) -> int:
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO items (chat_id, type, content, due_date, due_time, recurring, person) VALUES (?,?,?,?,?,?,?)",
        (chat_id, type_, content, due_date, due_time, recurring, person)
    )
    conn.commit()
    return cur.lastrowid


def get_items(chat_id: int, type_: str = None, done: int = 0):
    conn = get_conn()
    if type_:
        rows = conn.execute(
            "SELECT * FROM items WHERE chat_id=? AND type=? AND done=? ORDER BY due_date, due_time",
            (chat_id, type_, done)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM items WHERE chat_id=? AND done=? ORDER BY type, due_date, due_time",
            (chat_id, done)
        ).fetchall()
    return rows


def get_today_items(chat_id: int):
    today = date.today().isoformat()
    conn = get_conn()
    return conn.execute(
        "SELECT * FROM items WHERE chat_id=? AND due_date=? AND done=0 ORDER BY due_time",
        (chat_id, today)
    ).fetchall()


def get_tomorrow_items(chat_id: int):
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    conn = get_conn()
    return conn.execute(
        "SELECT * FROM items WHERE chat_id=? AND due_date=? AND done=0 ORDER BY due_time",
        (chat_id, tomorrow)
    ).fetchall()

def get_overdue_items(chat_id: int):
    """Return items past their due date not yet reminded (or reminded >20h ago)."""
    today = date.today().isoformat()
    conn = get_conn()
    return conn.execute(
        """SELECT * FROM items WHERE chat_id=? AND done=0
        AND due_date IS NOT NULL AND due_date < ?
        AND (reminded_at IS NULL OR reminded_at < datetime('now', '-20 hours'))
        ORDER BY due_date""",
        (chat_id, today)
    ).fetchall()


def get_user_name(chat_id: int):
    conn = get_conn()
    row = conn.execute("SELECT name FROM user_profiles WHERE chat_id=?", (chat_id,)).fetchone()
    return row[0] if row else None


def set_user_name(chat_id: int, name: str):
    conn = get_conn()
    conn.execute(
        "INSERT INTO user_profiles (chat_id, name) VALUES (?,?) "
        "ON CONFLICT(chat_id) DO UPDATE SET name=excluded.name",
        (chat_id, name)
    )
    conn.commit()


def get_people(chat_id: int):
    """Return list of (person_name, count) for pending agenda items."""
    conn = get_conn()
    rows = conn.execute(
        "SELECT person, COUNT(*) FROM items WHERE chat_id=? AND type='agenda' AND done=0 "
        "AND person IS NOT NULL GROUP BY person ORDER BY person",
        (chat_id,)
    ).fetchall()
    return [(row[0], row[1]) for row in rows]


def get_items_by_person(chat_id: int, person: str):
    conn = get_conn()
    return conn.execute(
        "SELECT * FROM items WHERE chat_id=? AND type='agenda' AND person=? AND done=0 ORDER BY created_at",
        (chat_id, person)
    ).fetchall()


def find_similar_person(chat_id: int, name: str):
    """Find an existing person with a similar name (for deduplication). Returns None if exact match or no similar."""
    conn = get_conn()
    rows = conn.execute(
        "SELECT DISTINCT person FROM items WHERE chat_id=? AND type='agenda' AND done=0 AND person IS NOT NULL",
        (chat_id,)
    ).fetchall()
    name_lower = name.strip().lower()
    for row in rows:
        existing = row[0]
        if not existing:
            continue
        ex_lower = existing.strip().lower()
        if ex_lower == name_lower:
            return None  # Exact match â no dedup dialog needed
        # Similar if first name matches (3+ chars)
        if len(name_lower) >= 3 and len(ex_lower) >= 3:
            if ex_lower.startswith(name_lower[:3]) or name_lower.startswith(ex_lower[:3]):
                return existing
    return None


def mark_done(item_id: int):
    conn = get_conn()
    conn.execute("UPDATE items SET done=1 WHERE id=?", (item_id,))
    conn.commit()


def mark_undone(item_id: int):
    conn = get_conn()
    conn.execute("UPDATE items SET done=0 WHERE id=?", (item_id,))
    conn.commit()


def delete_item(item_id: int):
    conn = get_conn()
    conn.execute("DELETE FROM items WHERE id=?", (item_id,))
    conn.commit()


def count_items_by_type(chat_id: int, type_: str = None) -> int:
    conn = get_conn()
    if type_ is None or type_ == "all":
        row = conn.execute("SELECT COUNT(*) FROM items WHERE chat_id=?", (chat_id,)).fetchone()
    else:
        row = conn.execute(
            "SELECT COUNT(*) FROM items WHERE chat_id=? AND type=?", (chat_id, type_)
        ).fetchone()
    return row[0] if row else 0


def delete_items_by_type(chat_id: int, type_: str = None) -> int:
    conn = get_conn()
    if type_ is None or type_ == "all":
        count = conn.execute("SELECT COUNT(*) FROM items WHERE chat_id=?", (chat_id,)).fetchone()[0] or 0
        conn.execute("DELETE FROM items WHERE chat_id=?", (chat_id,))
    else:
        count = conn.execute(
            "SELECT COUNT(*) FROM items WHERE chat_id=? AND type=?", (chat_id, type_)
        ).fetchone()[0] or 0
        conn.execute("DELETE FROM items WHERE chat_id=? AND type=?", (chat_id, type_))
    conn.commit()
    return count


def snooze_item(item_id: int, hours: int = 1):
    """Snooze by N hours from now."""
    conn = get_conn()
    row = conn.execute("SELECT due_date, due_time FROM items WHERE id=?", (item_id,)).fetchone()
    if not row:
        return
    now = datetime.now()
    new_dt = now + timedelta(hours=hours)
    conn.execute(
        "UPDATE items SET due_date=?, due_time=?, reminded_at=NULL WHERE id=?",
        (new_dt.date().isoformat(), new_dt.strftime("%H:%M"), item_id)
    )
    conn.commit()


def postpone_to_tomorrow(item_id: int):
    conn = get_conn()
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    conn.execute(
        "UPDATE items SET due_date=?, reminded_at=NULL WHERE id=?",
        (tomorrow, item_id)
    )
    conn.commit()


def get_due_reminders():
    """Return items due now (within the current minute) that haven't been reminded yet."""
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


def mark_reminded(item_id: int):
    conn = get_conn()
    conn.execute(
        "UPDATE items SET reminded_at=datetime('now') WHERE id=?", (item_id,)
    )
    conn.commit()


def handle_recurring(item_id: int):
    """After a recurring reminder fires, schedule next occurrence."""
    conn = get_conn()
    row = conn.execute("SELECT * FROM items WHERE id=?", (item_id,)).fetchone()
    if not row:
        return
    recurring = row[6]
    if not recurring:
        return
    due_date_str = row[4]
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


def get_summary_for_digest(chat_id: int):
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


def export_all(chat_id: int):
    conn = get_conn()
    return conn.execute(
        "SELECT id, type, content, due_date, due_time, recurring, done, created_at FROM items WHERE chat_id=? ORDER BY created_at DESC",
        (chat_id,)
    ).fetchall()
