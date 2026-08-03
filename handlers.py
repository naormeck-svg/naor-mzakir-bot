"""
All Telegram bot handlers.
"""
import io
import csv
import logging
from datetime import datetime, date, timedelta
from zoneinfo import ZoneInfo

_TZ = ZoneInfo("Asia/Jerusalem")
def _now(): return datetime.now(_TZ)
def _today(): return datetime.now(_TZ).date()
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
import llm
import db

logger = logging.getLogger(__name__)

TIPS = [
    "ð¡ ××× ×××××× ×× ××××¨ ×××××ª ×¢× ×¤×××ª â ××× ×××××ª ×¢× ×× ×©××©××.",
    "ð¡ ×¨×©××× ×©× 3 ××©××××ª ××©××××ª ×××× ×¢×××¤× ×¢× ×¨×©××× ×©× 20.",
    "ð¡ ×Ç¤× × ×©××ª× ×××¡××£ ××©××× â ×©××: ×× ×§××¨× ×× ×× ×ª×¢×©× ××ª ××?",
    "ð¡ ×¢×©× ××©××× ×××ª ×¢× ××¡××£ ××¤× × ×©××ª× ××ª××× ××××.",
    "ð¡ ××× ××ª×¨×××ª. ×× ×¢××××ª ×× ××××ª×¨ ××× ×©××ª× ×××©×.",
    "ð¡ ×¢×©× ××ª ×××©××× ××§×©× ××××ª×¨ ×©×××× × ××××§×¨.",
    "ð¡ ×ª×××ª ×××××¨ ×× ×× ×¡ ×©×× ××× ×¨×©×××ª ××¢×××¤××××ª ×©× ×××¨××. ×©×××  ×¢× ×©××.",
    "ð¡ '×××¨' ××× ×××§×× ×©×× ××ª××ª ×¨×× ×××©××××ª.",
    "ð¡ ×¤×××ª ×¢×××£ â ×××¨ ×¢×××§ ×¢× ×¤× × ×©××.",
    "ð¡ ××¤×¡×§× ×©× 5 ××§××ª ×× ×©×¢× ×××××× ×©×××× â ×× ××§××× ×.",
]
_tip_index = 0


# ââ Keyboards ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ

def main_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("ð ××©××××ª", callback_data="cmd:list"),
            InlineKeyboardButton("ð ××××", callback_data="cmd:today"),
        ],
        [
            InlineKeyboardButton("ð¤ ×××¦××", callback_data="cmd:export"),
            InlineKeyboardButton("â ×¢××¨×", callback_data="cmd:help"),
        ],
    ])

def save_confirm_keyboard(item_id, type_):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("ð ×××", callback_data=f"delete:{item_id}"),
            InlineKeyboardButton("ð ×¨×©×××", callback_data="cmd:list"),
        ],
    ])

def task_list_keyboard(items):
    buttons = []
    for row in items:
        item_id = row[0]
        content = row[3][:30] + ("â¦" if len(row[3]) > 30 else "")
        buttons.append([InlineKeyboardButton(f"â {content}", callback_data=f"done:{item_id}")])
    buttons.append([InlineKeyboardButton("ð ××××¨", callback_data="cmd:main")])
    return InlineKeyboardMarkup(buttons)

def smart_time_keyboard(suggestions: list):
    """3 smart suggestion buttons for new items (saves from pending)."""
    buttons = []
    for s in suggestions[:3]:
        label = s.get("label", "?")
        dt = s.get("date", "")
        tm = s.get("time") or "none"
        buttons.append([InlineKeyboardButton(f"ð {label}", callback_data=f"setdatetime:{dt}|{tm}")])
    return InlineKeyboardMarkup(buttons)

def reschedule_keyboard(item_id: int, suggestions: list):
    """Keyboard shown when a reminder fires: 3 reschedule options + done + cancel."""
    buttons = []
    for s in suggestions[:3]:
        label = s.get("label", "?")
        dt = s.get("date", "")
        tm = s.get("time") or "none"
        # callback: reschedule:ID|YYYY-MM-DD|HH:MM  (fits in 64 bytes for typical IDs)
        buttons.append([InlineKeyboardButton(f"ð {label}", callback_data=f"reschedule:{item_id}|{dt}|{tm}")])
    buttons.append([
        InlineKeyboardButton("â ×××¦×¢", callback_data=f"done:{item_id}"),
        InlineKeyboardButton("ð ×××××", callback_data=f"cancel_item:{item_id}"),
    ])
    return InlineKeyboardMarkup(buttons)


# ââ Command handlers âââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ

async def start(update, context):
    await update.message.reply_text(
        "×©×××! ×× × ××××××¨ ×©×× ð¤\n\n"
        "×©×× ×× ×§××, ××§×¡× ×× ×ª××× × â ××©×××¨ ××× ××××.\n"
        "×× ×¦×¨×× ×××§×© ××× × ××©×××¨, ×× ×§××¨× ××××××××ª.",
        reply_markup=main_keyboard(),
    )

async def help_cmd(update, context):
    await update.effective_message.reply_text(
        "×× ×× × ×××× ××¢×©××ª:\n\n"
        "ð¤ *×§××* â ××××¨ ×××¡××× ××××××××ª\n"
        "ð¬ *××§×¡×* â ×××ª× ×××¨\n"
        "ð¼ *×ª××× ×* â ×ª××××¨ ××©×××¨×\n\n"
        "×¤×§××××ª:\n"
        "/list â ××©××××ª ×¤×ª××××ª\n"
        "/today â ××©××××ª ×××××\n"
        "/notes â ××¢×¨××ª ×©×××¨××ª\n"
        "/reminders â ×ª××××¨××ª ×¤×¢××××ª\n"
        "/focus â ××××§×× ×©× ××××\n"
        "/focusblock â ××××§ ×¢×××× ××××§××ª\n"
        "/history â ×× ×©×××¦×¢\n"
        "/tip â ×××¤ ××× ××××××\n"
        "/export â ×××¦×× ×-CSV\n"
        "/menu â ×ª×¤×¨×× ××¤×ª××¨××",
        parse_mode="Markdown",
        reply_markup=main_keyboard(),
    )

async def menu_cmd(update, context):
    await update.effective_message.reply_text("×ª×¤×¨××:", reply_markup=main_keyboard())

async def list_cmd(update, context):
    chat_id = update.effective_chat.id
    items = db.get_items(chat_id, type_="task", done=0)
    if not items:
        await update.effective_message.reply_text("××× ××©××××ª ×¤×ª××××ª ð", reply_markup=main_keyboard())
        return
    text = "ð *××©××××ª ×¤×ª××××ª:*\n\n"
    for row in items:
        content = row[3]
        due = f" â {row[4]}" if row[4] else ""
        text += f"â¢ {content}{due}\n"
    await update.effective_message.reply_text(text, parse_mode="Markdown", reply_markup=task_list_keyboard(items))

async def today_cmd(update, context):
    chat_id = update.effective_chat.id
    items = db.get_today_items(chat_id)
    if not items:
        await update.effective_message.reply_text("××× ×¤×¨×××× ××××× â¨", reply_markup=main_keyboard())
        return
    text = f"ð *×××× â {_today().strftime('%d/%m/%Y')}:*\n\n"
    for row in items:
        emoji = {"task": "â", "note": "ð", "reminder": "â°"}.get(row[2], "â¢")
        time_str = f" {row[5]}" if row[5] else ""
        text += f"{emoji} {row[3]}{time_str}\n"
    await update.effective_message.reply_text(text, parse_mode="Markdown", reply_markup=task_list_keyboard(items))

async def notes_cmd(update, context):
    chat_id = update.effective_chat.id
    items = db.get_items(chat_id, type_="note", done=0)
    if not items:
        await update.effective_message.reply_text("××× ××¢×¨××ª ×©×××¨××ª.", reply_markup=main_keyboard())
        return
    text = "ð *××¢×¨××ª ×©×××¨××ª:*\n\n"
    for row in items:
        text += f"â¢ {row[3]}\n"
    await update.effective_message.reply_text(text, parse_mode="Markdown", reply_markup=main_keyboard())

async def reminders_cmd(update, context):
    chat_id = update.effective_chat.id
    items = db.get_items(chat_id, type_="reminder", done=0)
    if not items:
        await update.effective_message.reply_text("××× ×ª××××¨××ª ×¤×¢××××ª.", reply_markup=main_keyboard())
        return
    text = "â° *×ª××××¨××ª ×¤×¢××××ª:*\n\n"
    for row in items:
        date_str = f" {row[4]}" if row[4] else ""
        time_str = f" {row[5]}" if row[5] else ""
        text += f"â¢ {row[3]}{date_str}{time_str}\n"
    await update.effective_message.reply_text(text, parse_mode="Markdown", reply_markup=main_keyboard())

async def focus_cmd(update, context):
    chat_id = update.effective_chat.id
    today_items = db.get_today_items(chat_id)
    all_tasks = db.get_items(chat_id, type_="task", done=0)
    top_today = today_items[:3]
    today_ids = {r[0] for r in today_items}
    upcoming = [t for t in all_tasks if t[0] not in today_ids][:3]
    if not top_today and not upcoming:
        text = "ð¯ ××× ××©××××ª ×¤×ª××××ª â ××× ×¤× ××! â¨"
    else:
        text = "ð¯ *×××§××:*\n\n"
        if top_today:
            text += "*××××:*\n"
            for item in top_today:
                time_str = f" {item[5]}" if item[5] else ""
                text += f"â¢ {item[3]}{time_str}\n"
        if upcoming:
            text += "\n*××§×¨××:*\n"
            for item in upcoming:
                date_str = f" ({item[4]})" if item[4] else ""
                text += f"â¢ {item[3]}{date_str}\n"
    await update.effective_message.reply_text(text, parse_mode="Markdown", reply_markup=main_keyboard())

async def focusblock_cmd(update, context):
    text = (
        "ð *××××§ ×××§×× â 25 ××§××ª*\n\n"
        "××× ××ª×¨×××ª. ×¡×××¨ ××××× ××××ª×¨××.\n"
        "×××¨ ××©××× ×××ª â ××¢×©× ×©×§ ×××ª×.\n\n"
        "â± × ×¤××©×× ××¢×× 25 ××§××ª.\n\n"
        "_××¤××§××¡ ×©×× = ×××× ×©××._"
    )
    await update.effective_message.reply_text(text, parse_mode="Markdown", reply_markup=main_keyboard())

async def tip_cmd(update, context):
    global _tip_index
    tip = TIPS[_tip_index % len(TIPS)]
    _tip_index += 1
    await update.effective_message.reply_text(tip, reply_markup=main_keyboard())

async def history_cmd(update, context):
    chat_id = update.effective_chat.id
    items = db.get_items(chat_id, done=1)
    if not items:
        await update.effective_message.reply_text("××× ×××¡×××¨×× ×¢××××.", reply_markup=main_keyboard())
        return
    recent = list(items)[-20:]
    text = "â *×××¦×¢ ××××¨×× ×:*\n\n"
    for row in recent:
        emoji = {"task": "â", "note": "ð", "reminder": "â°"}.get(row[2], "â¢")
        text += f"{emoji} {row[3]}\n"
    await update.effective_message.reply_text(text, parse_mode="Markdown", reply_markup=main_keyboard())

async def export_cmd(update, context):
    chat_id = update.effective_chat.id
    rows = db.export_all(chat_id)
    if not rows:
        await update.effective_message.reply_text("××× × ×ª×× ×× ××××¦×× ×¢××××.", reply_markup=main_keyboard())
        return
    buf = io.StringIO()
    buf.write("ï»¿")
    writer = csv.writer(buf)
    writer.writerow(["ID", "×¡××", "×ª×××", "×ª××¨××", "×©×¢×", "××××¨", "×××¦×¢", "× ××¦×¨"])
    for row in rows:
        done_str = "××" if row[6] else "××"
        writer.writerow([row[0], row[1], row[2], row[3] or "", row[4] or "", row[5] or "", done_str, row[7]])
    buf.seek(0)
    file_bytes = buf.getvalue().encode("utf-8-sig")
    await update.effective_message.reply_document(
        document=io.BytesIO(file_bytes),
        filename=f"×××××¨_{date.today().isoformat()}.csv",
        caption="×× × ×× ×× ×ª×× ×× ×©×× ð",
    )


# ââ Message handlers âââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ

async def handle_text(update, context):
    text = update.message.text.strip()
    chat_id = update.effective_chat.id
    if text in ("/list", "×¨×©×××"):
        return await list_cmd(update, context)
    if text in ("/today", "××××"):
        return await today_cmd(update, context)
    if text in ("/export", "×××¦××"):
        return await export_cmd(update, context)
    await _process_content(update, chat_id, text, context=context)

async def handle_voice(update, context):
    chat_id = update.effective_chat.id
    voice = update.message.voice
    file = await context.bot.get_file(voice.file_id)
    audio_bytes = bytes(await file.download_as_bytearray())
    await update.message.reply_text("ð¤ ××ª×××â¦")
    try:
        text = await llm.transcribe(audio_bytes, "audio.ogg")
    except Exception as e:
        logger.error(f"Transcription error: {e}")
        await update.message.reply_text("×× ××¦×××ª× ××ª×××. × ×¡× ×©××.", reply_markup=main_keyboard())
        return
    await _process_content(update, chat_id, text, voice_text=text, context=context)

async def handle_photo(update, context):
    chat_id = update.effective_chat.id
    photo = update.message.photo[-1]
    file = await context.bot.get_file(photo.file_id)
    image_bytes = bytes(await file.download_as_bytearray())
    await update.message.reply_text("ð¼ ×× ×ª× ×ª××× ×â¦")
    try:
        description = await llm.describe_image(image_bytes)
    except Exception as e:
        logger.error(f"Vision error: {e}")
        await update.message.reply_text("×× ××¦×××ª× ×× ×ª× ××ª ××ª××× ×.", reply_markup=main_keyboard())
        return
    item_id = db.save_item(chat_id, "note", f"[×ª××× ×] {description}")
    await update.message.reply_text(
        f"ð ×©××¨×ª×:\n_{description}_",
        parse_mode="Markdown",
        reply_markup=save_confirm_keyboard(item_id, "note"),
    )

async def _process_content(update, chat_id, text, voice_text=None, context=None):
    try:
        result = await llm.classify(text)
    except Exception as e:
        logger.error(f"Classification error: {e}")
        await update.message.reply_text("×××¤×¡, ×©××××. × ×¡× ×©××.", reply_markup=main_keyboard())
        return

    msg_type = result.get("type", "note")
    content = result.get("content", text)
    due_date = result.get("date")
    due_time = result.get("time")
    recurring = result.get("recurring")

    if msg_type == "chat":
        data_keywords = ["××©××××ª", "×ª××××¨××ª", "××××", "×××", "××© ××", "××¢×¨××ª", "×¤×ª××××ª", "×¨×©×××", "×× ××©"]
        if any(kw in text for kw in data_keywords):
            tasks = db.get_items(chat_id, type_="task", done=0)
            reminders = db.get_items(chat_id, type_="reminder", done=0)
            notes = db.get_items(chat_id, type_="note", done=0)
            today_items = db.get_today_items(chat_id)
            summary = (
                f"××©××××ª ×¤×ª××××ª ({len(tasks)}): {', '.join(r[3][:30] for r in tasks[:8])}\n"
                f"×ª××××¨××ª ×¤×¢××××ª ({len(reminders)}): {', '.join(r[3][:30] for r in reminders[:5])}\n"
                f"××¢×¨××ª ({len(notes)}): {', '.join(r[3][:30] for r in notes[:5])}\n"
                f"×××× ({len(today_items)}): {', '.join(r[3][:30] for r in today_items[:5])}"
            )
            try:
                reply = await llm.chat_with_context(text, summary)
            except Exception as e:
                logger.error(f"Chat error: {e}")
                reply = "×× ××¦×××ª× ××¢× ××ª, × ×¡× ×©××."
        else:
            try:
                reply = await llm.chat(text)
            except Exception as e:
                logger.error(f"Chat error: {e}")
                reply = "×× ××¦×××ª× ××¢× ××ª, × ×¡× ×©××."
        await update.message.reply_text(reply, reply_markup=main_keyboard())
        return

    # Ask for timing with 3 smart suggestions
    # Auto-set today for tasks if time was given but no date
    if msg_type in ("task", "reminder") and due_time and not due_date:
        now = _now()
        try:
            hour, minute = map(int, due_time.split(":"))
            today_dt = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if today_dt > now:
                due_date = now.date().isoformat()  # time is still future today
            else:
                due_date = (now.date() + timedelta(days=1)).isoformat()  # already passed → tomorrow
        except Exception:
            due_date = now.date().isoformat()  # fallback to today

    # Show picker: task needs a date; reminder needs both date and time
    if (msg_type == "task" and not due_date) or (msg_type == "reminder" and not due_date and not due_time):
        if context is not None:
            context.user_data["pending"] = {
                "type": msg_type, "content": content,
                "recurring": recurring, "voice_text": voice_text,
            }
        emoji = "â" if msg_type == "task" else "â°"
        await update.message.reply_text("â³ ×××©× ×¢× ×××¢×××â¦")
        try:
            suggestions = await llm.suggest_times(content)
        except Exception:
            suggestions = llm._fallback_suggestions()
        await update.message.reply_text(
            f"{emoji} *{content}*\n\n××ª× ××××××¨ ××?",
            parse_mode="Markdown",
            reply_markup=smart_time_keyboard(suggestions),
        )
        return

    await _save_and_confirm(update, chat_id, msg_type, content, due_date, due_time, recurring, voice_text)

async def _save_and_confirm(update, chat_id, msg_type, content, due_date, due_time, recurring, voice_text=None):
    item_id = db.save_item(chat_id, msg_type, content, due_date, due_time, recurring)
    emoji = {"task": "â", "note": "ð", "reminder": "â°"}.get(msg_type, "ð¾")
    details = ""
    if voice_text and voice_text != content:
        details += f"\nð¤ _{voice_text}_"
    if due_date:
        details += f"\nð {due_date}"
    if due_time:
        details += f" â° {due_time}"
    if recurring:
        recurring_labels = {
            "daily": "×× ×××", "weekly:sun": "×× ×¨××©××",
            "weekly:mon": "×× ×©× ×", "weekly:fri": "×× ×©××©×", "monthly": "×× ××××©",
        }
        details += f"\nð {recurring_labels.get(recurring, recurring)}"
    reply_target = update.message or update.effective_message
    await reply_target.reply_text(
        f"{emoji} *{content}*{details}",
        parse_mode="Markdown",
        reply_markup=save_confirm_keyboard(item_id, msg_type),
    )


# ââ Callback query handler âââââââââââââââââââââââââââââââââââââââââââââââââââââ

async def handle_callback(update, context):
    query = update.callback_query
    await query.answer()
    data = query.data
    chat_id = update.effective_chat.id

    if data == "cmd:list":   return await list_cmd(update, context)
    if data == "cmd:today":  return await today_cmd(update, context)
    if data == "cmd:export": return await export_cmd(update, context)
    if data == "cmd:help":   return await help_cmd(update, context)
    if data == "cmd:main":
        await query.edit_message_text("×ª×¤×¨×× ×¨××©×:", reply_markup=main_keyboard())
        return

    parts = data.split(":", 1)
    if len(parts) != 2:
        return
    action, param = parts

    # ââ New item: smart date+time selection ââ
    if action == "setdatetime":
        pending = context.user_data.get("pending")
        if not pending:
            await query.edit_message_text("×× × ××¦× ×¤×¨×× ×××ª××.", reply_markup=main_keyboard())
            return
        dt_parts = param.split("|", 1)
        selected_date = dt_parts[0] if dt_parts[0] else None
        selected_time = dt_parts[1] if len(dt_parts) > 1 and dt_parts[1] != "none" else None
        item_id = db.save_item(chat_id, pending["type"], pending["content"],
                               selected_date, selected_time, pending.get("recurring"))
        context.user_data.pop("pending", None)
        emoji = "â" if pending["type"] == "task" else "â°"
        label = "××©×××" if pending["type"] == "task" else "×ª××××¨×ª"
        details = ""
        if selected_date:
            details += f"\nð {selected_date}"
        if selected_time:
            details += f" â° {selected_time}"
        await query.edit_message_text(
            f"{emoji} × ×©××¨ ×*{label}*: {pending['content']}{details}",
            parse_mode="Markdown",
            reply_markup=save_confirm_keyboard(item_id, pending["type"]),
        )
        return

    # ââ Existing item: reschedule to new future time ââ
    if action == "reschedule":
        # param format: "ID|YYYY-MM-DD|HH:MM"
        rp = param.split("|", 2)
        if len(rp) < 2:
            return
        try:
            item_id = int(rp[0])
        except ValueError:
            return
        new_date = rp[1] if rp[1] else None
        new_time = rp[2] if len(rp) > 2 and rp[2] != "none" else None
        conn = db.get_conn()
        conn.execute(
            "UPDATE items SET due_date=?, due_time=?, reminded_at=NULL, done=0 WHERE id=?",
            (new_date, new_time, item_id)
        )
        details = ""
        if new_date:
            details += f"\nð {new_date}"
        if new_time:
            details += f" â° {new_time}"
        await query.edit_message_text(
            f"ð ×ª××××¨×ª × ×××ª×!{details}",
            parse_mode="Markdown",
            reply_markup=main_keyboard(),
        )
        return

    # ââ Cancel item (mark done / dismiss) ââ
    if action == "cancel_item":
        try:
            item_id = int(param)
        except ValueError:
            return
        db.mark_done(item_id)
        await query.edit_message_text("ð ××©××× ×××××.", reply_markup=main_keyboard())
        return

    try:
        item_id = int(param)
    except ValueError:
        return

    if action == "done":
        db.mark_done(item_id)
        await query.edit_message_text("â ×¡××× ××××¦×¢!", reply_markup=main_keyboard())
    elif action == "delete":
        db.mark_done(item_id)
        await query.edit_message_text("ð × ×××§.", reply_markup=main_keyboard())
    elif action == "snooze1h":
        db.snooze_item(item_id, hours=1)
        await query.edit_message_text("â° × ××× ××©×¢× ×××ª.", reply_markup=main_keyboard())
    elif action == "tomorrow":
        db.postpone_to_tomorrow(item_id)
        await query.edit_message_text("ð × ××× ××××¨.", reply_markup=main_keyboard())
    elif action == "saved":
        await query.answer("×××¨ × ×©××¨ â", show_alert=False)
