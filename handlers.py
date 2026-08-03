"""
All Telegram bot handlers.
"""
import io
import csv
import logging
from datetime import date, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
import llm
import db

logger = logging.getLogger(__name__)

TIPS = [
    "💡 מינימליזם לא אומר לחיות עם פחות — אלא לחיות עם מה שחשוב.",
    "💡 רשימה של 3 משימות חשובות ביום עדיפה על רשימה של 20.",
    "💡 לפני שאתה מוסיף משימה — שאל: מה קורה אם לא תעשה את זה?",
    "💡 ה\'לא\' שאתה אומר לדברים לא חשובים הוא ה\'כן\' שאתה אומר לדברים שחשובים.",
    "💡 עשה משימה אחת עד הסוף לפני שאתה מתחיל הבאה.",
    "💡 תיבת הדואר הנכנס שלך היא רשימת העדיפויות של אחרים. שמור על שלך.",
    "💡 כבה התראות. הן עולות לך ביותר ממה שאתה חושב.",
    "💡 עשה את המשימה הקשה ביותר ראשונה בבוקר.",
    "💡 \'מחר\' הוא המקום שבו מתות רוב המשימות.",
    "💡 פחות עדיף — בחר עמוק על פני רחב.",
]
_tip_index = 0


# ── Keyboards ──────────────────────────────────────────────────────────────────

def main_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📋 משימות", callback_data="cmd:list"),
            InlineKeyboardButton("📅 היום", callback_data="cmd:today"),
        ],
        [
            InlineKeyboardButton("📤 ייצוא", callback_data="cmd:export"),
            InlineKeyboardButton("❓ עזרה", callback_data="cmd:help"),
        ],
    ])

def save_confirm_keyboard(item_id, type_):
    type_label = {"task": "✅ משימה", "note": "📝 הערה", "reminder": "⏰ תזכורת"}.get(type_, type_)
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"נשמר כ{type_label} ✓", callback_data=f"saved:{item_id}")],
        [
            InlineKeyboardButton("🗑 מחק", callback_data=f"delete:{item_id}"),
            InlineKeyboardButton("📋 כל המשימות", callback_data="cmd:list"),
        ],
    ])

def reminder_keyboard(item_id):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ סיימתי", callback_data=f"done:{item_id}")],
        [
            InlineKeyboardButton("⏰ דחה שעה", callback_data=f"snooze1h:{item_id}"),
            InlineKeyboardButton("📅 למחר", callback_data=f"tomorrow:{item_id}"),
        ],
    ])

def task_list_keyboard(items):
    buttons = []
    for row in items:
        item_id = row[0]
        content = row[3][:30] + ("…" if len(row[3]) > 30 else "")
        buttons.append([InlineKeyboardButton(f"✅ {content}", callback_data=f"done:{item_id}")])
    buttons.append([InlineKeyboardButton("🔙 חזור", callback_data="cmd:main")])
    return InlineKeyboardMarkup(buttons)

def ask_date_keyboard():
    today = date.today()
    tomorrow = today + timedelta(days=1)
    day_after = today + timedelta(days=2)
    days_to_friday = (4 - today.weekday()) % 7 or 7
    this_friday = today + timedelta(days=days_to_friday)
    days_to_monday = (0 - today.weekday()) % 7 or 7
    next_monday = today + timedelta(days=days_to_monday)
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(f"📅 היום ({today.strftime('%d/%m')})", callback_data=f"setdate:{today.isoformat()}"),
            InlineKeyboardButton(f"📅 מחר ({tomorrow.strftime('%d/%m')})", callback_data=f"setdate:{tomorrow.isoformat()}"),
        ],
        [
            InlineKeyboardButton(f"📅 מחרתיים ({day_after.strftime('%d/%m')})", callback_data=f"setdate:{day_after.isoformat()}"),
            InlineKeyboardButton(f"📅 שישי ({this_friday.strftime('%d/%m')})", callback_data=f"setdate:{this_friday.isoformat()}"),
        ],
        [
            InlineKeyboardButton(f"📅 שבוע הבא ({next_monday.strftime('%d/%m')})", callback_data=f"setdate:{next_monday.isoformat()}"),
            InlineKeyboardButton("⏭ ללא תאריך", callback_data="setdate:none"),
        ],
    ])

def ask_time_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🌅 07:00", callback_data="settime:07:00"),
            InlineKeyboardButton("☀️ 09:00", callback_data="settime:09:00"),
        ],
        [
            InlineKeyboardButton("🕛 12:00", callback_data="settime:12:00"),
            InlineKeyboardButton("🌆 17:00", callback_data="settime:17:00"),
        ],
        [
            InlineKeyboardButton("🌙 20:00", callback_data="settime:20:00"),
            InlineKeyboardButton("⏭ ללא שעה", callback_data="settime:none"),
        ],
    ])


# ── Command handlers ───────────────────────────────────────────────────────────

async def start(update, context):
    await update.message.reply_text(
        "שלום! אני המזכיר שלך 🤖\n\n"
        "שלח לי קול, טקסט או תמונה — אשמור הכל מייד.\n"
        "לא צריך לבקש ממני לשמור, זה קורה אוטומטית.",
        reply_markup=main_keyboard(),
    )

async def help_cmd(update, context):
    await update.effective_message.reply_text(
        "מה אני יכול לעשות:\n\n"
        "🎤 *קול* — אוגר ומסווג אוטומטית\n"
        "💬 *טקסט* — אותו דבר\n"
        "🖼 *תמונה* — תיאור ושמירה\n\n"
        "פקודות:\n"
        "/list — משימות פתוחות\n"
        "/today — משימות להיום\n"
        "/notes — הערות שמורות\n"
        "/reminders — תזכורות פעילות\n"
        "/focus — המיקוד של היום\n"
        "/focusblock — בלוק עבודה ממוקדת\n"
        "/history — מה שבוצע\n"
        "/tip — טיפ מינימליזם\n"
        "/export — ייצוא ל-CSV\n"
        "/menu — תפריט כפתורים",
        parse_mode="Markdown",
        reply_markup=main_keyboard(),
    )

async def menu_cmd(update, context):
    await update.effective_message.reply_text("תפריט:", reply_markup=main_keyboard())

async def list_cmd(update, context):
    chat_id = update.effective_chat.id
    items = db.get_items(chat_id, type_="task", done=0)
    if not items:
        await update.effective_message.reply_text("אין משימות פתוחות 🎉", reply_markup=main_keyboard())
        return
    text = "📋 *משימות פתוחות:*\n\n"
    for row in items:
        content = row[3]
        due = f" — {row[4]}" if row[4] else ""
        text += f"• {content}{due}\n"
    await update.effective_message.reply_text(text, parse_mode="Markdown", reply_markup=task_list_keyboard(items))

async def today_cmd(update, context):
    chat_id = update.effective_chat.id
    items = db.get_today_items(chat_id)
    if not items:
        await update.effective_message.reply_text("אין פריטים להיום ✨", reply_markup=main_keyboard())
        return
    text = f"📅 *היום — {date.today().strftime('%d/%m/%Y')}:*\n\n"
    for row in items:
        emoji = {"task": "☐", "note": "📝", "reminder": "⏰"}.get(row[2], "•")
        time_str = f" {row[5]}" if row[5] else ""
        text += f"{emoji} {row[3]}{time_str}\n"
    await update.effective_message.reply_text(text, parse_mode="Markdown", reply_markup=task_list_keyboard(items))

async def notes_cmd(update, context):
    chat_id = update.effective_chat.id
    items = db.get_items(chat_id, type_="note", done=0)
    if not items:
        await update.effective_message.reply_text("אין הערות שמורות.", reply_markup=main_keyboard())
        return
    text = "📝 *הערות שמורות:*\n\n"
    for row in items:
        text += f"• {row[3]}\n"
    await update.effective_message.reply_text(text, parse_mode="Markdown", reply_markup=main_keyboard())

async def reminders_cmd(update, context):
    chat_id = update.effective_chat.id
    items = db.get_items(chat_id, type_="reminder", done=0)
    if not items:
        await update.effective_message.reply_text("אין תזכורות פעילות.", reply_markup=main_keyboard())
        return
    text = "⏰ *תזכורות פעילות:*\n\n"
    for row in items:
        date_str = f" {row[4]}" if row[4] else ""
        time_str = f" {row[5]}" if row[5] else ""
        text += f"• {row[3]}{date_str}{time_str}\n"
    await update.effective_message.reply_text(text, parse_mode="Markdown", reply_markup=main_keyboard())

async def focus_cmd(update, context):
    chat_id = update.effective_chat.id
    today_items = db.get_today_items(chat_id)
    all_tasks = db.get_items(chat_id, type_="task", done=0)
    focus_item = None
    if today_items:
        focus_item = today_items[0][3]
    elif all_tasks:
        focus_item = all_tasks[0][3]
    if focus_item:
        text = f"🎯 *מיקוד היום:*\n\n_{focus_item}_\n\nהתמקד במשימה הזאת עכשיו."
    else:
        text = "🎯 אין משימות פתוחות — יום פנוי! ✨"
    await update.effective_message.reply_text(text, parse_mode="Markdown", reply_markup=main_keyboard())

async def focusblock_cmd(update, context):
    text = (
        "🔒 *בלוק מיקוד — 25 דקות*\n\n"
        "כבה התראות. סגור טאבים מיותרים.\n"
        "בחר משימה אחת — ועשה רק אותה.\n\n"
        "⏱ נפגשים בעוד 25 דקות.\n\n"
        "_הפוקוס שלך = הכוח שלך._"
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
        await update.effective_message.reply_text("אין היסטוריה עדיין.", reply_markup=main_keyboard())
        return
    recent = list(items)[-20:]
    text = "✅ *בוצע לאחרונה:*\n\n"
    for row in recent:
        emoji = {"task": "✅", "note": "📝", "reminder": "⏰"}.get(row[2], "•")
        text += f"{emoji} {row[3]}\n"
    await update.effective_message.reply_text(text, parse_mode="Markdown", reply_markup=main_keyboard())

async def export_cmd(update, context):
    chat_id = update.effective_chat.id
    rows = db.export_all(chat_id)
    if not rows:
        await update.effective_message.reply_text("אין נתונים לייצוא עדיין.", reply_markup=main_keyboard())
        return
    buf = io.StringIO()
    buf.write("\ufeff")
    writer = csv.writer(buf)
    writer.writerow(["ID", "סוג", "תוכן", "תאריך", "שעה", "חוזר", "בוצע", "נוצר"])
    for row in rows:
        done_str = "כן" if row[6] else "לא"
        writer.writerow([row[0], row[1], row[2], row[3] or "", row[4] or "", row[5] or "", done_str, row[7]])
    buf.seek(0)
    file_bytes = buf.getvalue().encode("utf-8-sig")
    await update.effective_message.reply_document(
        document=io.BytesIO(file_bytes),
        filename=f"מזכיר_{date.today().isoformat()}.csv",
        caption="הנה כל הנתונים שלך 📊",
    )


# ── Message handlers ───────────────────────────────────────────────────────────

async def handle_text(update, context):
    text = update.message.text.strip()
    chat_id = update.effective_chat.id
    if text in ("/list", "רשימה"):
        return await list_cmd(update, context)
    if text in ("/today", "היום"):
        return await today_cmd(update, context)
    if text in ("/export", "ייצוא"):
        return await export_cmd(update, context)
    await _process_content(update, chat_id, text, context=context)

async def handle_voice(update, context):
    chat_id = update.effective_chat.id
    voice = update.message.voice
    file = await context.bot.get_file(voice.file_id)
    audio_bytes = bytes(await file.download_as_bytearray())
    await update.message.reply_text("🎤 מתמלל…")
    try:
        text = await llm.transcribe(audio_bytes, "audio.ogg")
    except Exception as e:
        logger.error(f"Transcription error: {e}")
        await update.message.reply_text("לא הצלחתי לתמלל. נסה שוב.", reply_markup=main_keyboard())
        return
    await _process_content(update, chat_id, text, voice_text=text, context=context)

async def handle_photo(update, context):
    chat_id = update.effective_chat.id
    photo = update.message.photo[-1]
    file = await context.bot.get_file(photo.file_id)
    image_bytes = bytes(await file.download_as_bytearray())
    await update.message.reply_text("🖼 מנתח תמונה…")
    try:
        description = await llm.describe_image(image_bytes)
    except Exception as e:
        logger.error(f"Vision error: {e}")
        await update.message.reply_text("לא הצלחתי לנתח את התמונה.", reply_markup=main_keyboard())
        return
    item_id = db.save_item(chat_id, "note", f"[תמונה] {description}")
    await update.message.reply_text(
        f"📝 שמרתי:\n_{description}_",
        parse_mode="Markdown",
        reply_markup=save_confirm_keyboard(item_id, "note"),
    )

async def _process_content(update, chat_id, text, voice_text=None, context=None):
    try:
        result = await llm.classify(text)
    except Exception as e:
        logger.error(f"Classification error: {e}")
        await update.message.reply_text("אופס, שגיאה. נסה שוב.", reply_markup=main_keyboard())
        return

    msg_type = result.get("type", "note")
    content = result.get("content", text)
    due_date = result.get("date")
    due_time = result.get("time")
    recurring = result.get("recurring")

    if msg_type == "chat":
        try:
            reply = await llm.chat(text)
        except Exception as e:
            logger.error(f"Chat error: {e}")
            reply = "לא הצלחתי לענות, נסה שוב."
        await update.message.reply_text(reply, reply_markup=main_keyboard())
        return

    if msg_type in ("task", "reminder") and not due_date:
        if context is not None:
            context.user_data["pending"] = {
                "type": msg_type, "content": content,
                "time": due_time, "recurring": recurring, "voice_text": voice_text,
            }
        emoji = "✅" if msg_type == "task" else "⏰"
        await update.message.reply_text(
            f"{emoji} *{content}*\n\nמתי?",
            parse_mode="Markdown",
            reply_markup=ask_date_keyboard(),
        )
        return

    if msg_type == "reminder" and not due_time:
        if context is not None:
            context.user_data["pending"] = {
                "type": msg_type, "content": content,
                "date": due_date, "recurring": recurring, "voice_text": voice_text,
            }
        await update.message.reply_text(
            f"⏰ *{content}*\n📅 {due_date}\n\nבאיזו שעה?",
            parse_mode="Markdown",
            reply_markup=ask_time_keyboard(),
        )
        return

    await _save_and_confirm(update, chat_id, msg_type, content, due_date, due_time, recurring, voice_text)

async def _save_and_confirm(update, chat_id, msg_type, content, due_date, due_time, recurring, voice_text=None):
    item_id = db.save_item(chat_id, msg_type, content, due_date, due_time, recurring)
    emoji = {"task": "✅", "note": "📝", "reminder": "⏰"}.get(msg_type, "💾")
    label = {"task": "משימה", "note": "הערה", "reminder": "תזכורת"}.get(msg_type, "פריט")
    details = ""
    if voice_text and voice_text != content:
        details += f"\n🎤 _{voice_text}_"
    if due_date:
        details += f"\n📅 {due_date}"
    if due_time:
        details += f" ⏰ {due_time}"
    if recurring:
        recurring_labels = {
            "daily": "כל יום", "weekly:sun": "כל ראשון",
            "weekly:mon": "כל שני", "weekly:fri": "כל שישי", "monthly": "כל חודש",
        }
        details += f"\n🔄 {recurring_labels.get(recurring, recurring)}"
    reply_target = update.message or update.effective_message
    await reply_target.reply_text(
        f"{emoji} נשמר כ*{label}*: {content}{details}",
        parse_mode="Markdown",
        reply_markup=save_confirm_keyboard(item_id, msg_type),
    )


# ── Callback query handler ─────────────────────────────────────────────────────

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
        await query.edit_message_text("תפריט ראשי:", reply_markup=main_keyboard())
        return

    parts = data.split(":", 1)
    if len(parts) != 2:
        return
    action, param = parts

    if action == "setdate":
        pending = context.user_data.get("pending")
        if not pending:
            await query.edit_message_text("לא נמצא פריט ממתין.", reply_markup=main_keyboard())
            return
        selected_date = None if param == "none" else param
        pending["date"] = selected_date
        if pending["type"] == "reminder":
            context.user_data["pending"] = pending
            date_str = f"\n📅 {selected_date}" if selected_date else ""
            await query.edit_message_text(
                f"⏰ *{pending['content']}*{date_str}\n\nבאיזו שעה?",
                parse_mode="Markdown",
                reply_markup=ask_time_keyboard(),
            )
        else:
            item_id = db.save_item(chat_id, pending["type"], pending["content"],
                                   selected_date, pending.get("time"), pending.get("recurring"))
            context.user_data.pop("pending", None)
            date_str = f"\n📅 {selected_date}" if selected_date else ""
            await query.edit_message_text(
                f"✅ נשמר כ*משימה*: {pending['content']}{date_str}",
                parse_mode="Markdown",
                reply_markup=save_confirm_keyboard(item_id, pending["type"]),
            )
        return

    if action == "settime":
        pending = context.user_data.get("pending")
        if not pending:
            await query.edit_message_text("לא נמצא פריט ממתין.", reply_markup=main_keyboard())
            return
        selected_time = None if param == "none" else param
        item_id = db.save_item(chat_id, pending["type"], pending["content"],
                               pending.get("date"), selected_time, pending.get("recurring"))
        context.user_data.pop("pending", None)
        details = ""
        if pending.get("date"):
            details += f"\n📅 {pending['date']}"
        if selected_time:
            details += f" ⏰ {selected_time}"
        await query.edit_message_text(
            f"⏰ נשמר כ*תזכורת*: {pending['content']}{details}",
            parse_mode="Markdown",
            reply_markup=save_confirm_keyboard(item_id, pending["type"]),
        )
        return

    try:
        item_id = int(param)
    except ValueError:
        return

    if action == "done":
        db.mark_done(item_id)
        await query.edit_message_text("✅ סומן כבוצע!", reply_markup=main_keyboard())
    elif action == "delete":
        db.mark_done(item_id)
        await query.edit_message_text("🗑 נמחק.", reply_markup=main_keyboard())
    elif action == "snooze1h":
        db.snooze_item(item_id, hours=1)
        await query.edit_message_text("⏰ נדחה בשעה אחת.", reply_markup=main_keyboard())
    elif action == "tomorrow":
        db.postpone_to_tomorrow(item_id)
        await query.edit_message_text("📅 נדחה למחר.", reply_markup=main_keyboard())
    elif action == "saved":
        await query.answer("כבר נשמר ✓", show_alert=False)
