import libsql_experimental as libsql
from datetime import datetime, date, timedelta
from config import TURSO_DATABASE_URL, TURSO_AUTH_TOKEN

_conn = None

def get_conn():
    global _conn
    if _conn is None:
        _conn = libsql.connect(TURSO_DATABASE_URL, auth_token=TURSO_AUTH_TOKEN)
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

def save_item(chat_id, type_, content, due_date=None, due_time=None, recurring=None):
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO items (chat_id, type, content, due_date, due_time, recurring) VALUES (?,?,?,?,?,?)",
        (chat_id, type_, content, due_date, due_time, recurring)
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
    if not row: return
    recurring = row[6]
    if not recurring: return
    due_date = date.fromisoformat(row[3]) if row[3] else None
    if not due_date: return
    if recurring == "daily":
        next_date = due_date + timedelta(days=1)
    elif recurring.startswith("weekly:"):
        next_date = due_date + timedelta(weeks=1)
    elif recurring == "monthly":
        next_date = due_date.replace(month=due_date.month % 12 + 1) if due_date.month < 12 else due_date.replace(year=due_date.year + 1, month=1)
    else:
        return
    conn.execute("UPDATE items SET due_date=?, reminded_at=NULL WHERE id=?", (next_date.isoformat(), item_id))
    conn.commit()

def get_all_chat_ids():
    conn = get_conn()
    rows = conn.execute("SELECT DISTINCT chat_id FROM items").fetchall()
    return [r[0] for r in rows]

def get_summary_for_digest(chat_id):
    today = date.today().isoformat()
    conn = get_conn()
    tasks_today = conn.execute("SELECT COUNT(*) FROM items WHERE chat_id=? AND type='task' AND due_date=? AND done=0", (chat_id, today)).fetchone()[0]
    reminders_today = conn.execute("SELECT COUNT(*) FROM items WHERE chat_id=? AND type='reminder' AND due_date=? AND done=0", (chat_id, today)).fetchone()[0]
    overdue = conn.execute("SELECT COUNT(*) FROM items WHERE chat_id=? AND done=0 AND due_date < ? AND due_date IS NOT NULL", (chat_id, today)).fetchone()[0]
    return tasks_today, reminders_today, overdue

def export_all(chat_id):
    conn = get_conn()
    return conn.execute(
        "SELECT id, type, content, due_date, due_time, recurring, done, created_at FROM items WHERE chat_id=? ORDER BY created_at DESC",
        (chat_id,)
    ).fetchall()
