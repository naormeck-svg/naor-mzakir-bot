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
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import ContextTypes
import llm
import db

logger = logging.getLogger(__name__)

TIPS = [
    "💡 מינימליזם לא אומר לחיות עם פחות — אלא לחיות עם מה שחשוב.",
    "💡 רשימה של 3 משימות חשובות ביום עדיפה על רשימה של 20.",
    "💡 לפני שאתה מוסיף משימה — שאל: מה קורה אם לא תעשה את זה?",
    "💡 עשה משימה אחת עד הסוף לפני שאתה מתחיל הבאה.",
    "💡 כבה התראות. הן עולות לך ביותר ממה שאתה חושב.",
    "💡 עשה את המשימה הקשה ביותר שלך בבוקר.",
    "💡 תיבת הדואר הנכנס שלך היא רשימת העדיפויות של אחרים. שמור על שלך.",
    "💡 'מחר' הוא המקום שבו מתות רוב המשימות.",
    "💡 פחות עדיף — בחר עמוק על פני רחב.",
    "💡 הפסקה של 5 דקות כל שעה מגדילה ריכוז — לא מקטינה.",
]
_tip_index = 0

# ── Keyboards ──────────────────────────────────────────────────────────────────

def main_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📋 משימות", callback_data="cmd:list"),
            InlineKeyboardButton("📅 היום", callback_data="cmd:today"),
            InlineKeyboardButton("📅 מחר", callback_data="cmd:tomorrow"),
        ],
        [
            InlineKeyboardButton("👥 אנשים", callback_data="cmd:people"),
            InlineKeyboardButton("📤 ייצוא", callback_data="cmd:export"),
        ],
        [
            InlineKeyboardButton("❓ עזרה", callback_data="cmd:help"),
        ],
    ])


def reply_keyboard():
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton("📅 היום"), KeyboardButton("📅 מחר")],
            [KeyboardButton("📋 משימות"), KeyboardButton("👥 אנשים")],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )
def save_confirm_keyboard(item_id, type_):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🗑 בטל", callback_data=f"delete:{item_id}"),
            InlineKeyboardButton("📋 רשימה", callback_data="cmd:list"),
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

def smart_time_keyboard(suggestions: list):
    """3 smart suggestion buttons for new items (saves from pending)."""
    buttons = []
    for s in suggestions[:3]:
        label = s.get("label", "?")
        dt = s.get("date", "")
        tm = s.get("time") or "none"
        buttons.append([InlineKeyboardButton(f"📅 {label}", callback_data=f"setdatetime:{dt}|{tm}")])
    return InlineKeyboardMarkup(buttons)

def reschedule_keyboard(item_id: int, suggestions: list):
    """Keyboard shown when a reminder fires: 3 reschedule options + done + cancel."""
    buttons = []
    for s in suggestions[:3]:
        label = s.get("label", "?")
        dt = s.get("date", "")
        tm = s.get("time") or "none"
        buttons.append([InlineKeyboardButton(f"📅 {label}", callback_data=f"reschedule:{item_id}|{dt}|{tm}")])
    buttons.append([
        InlineKeyboardButton("✅ בוצע", callback_data=f"done:{item_id}"),
        InlineKeyboardButton("🗑 ביטול", callback_data=f"cancel_item:{item_id}"),
    ])
    return InlineKeyboardMarkup(buttons)

def people_keyboard(people_list):
    """Inline keyboard with one button per person with open agenda items."""
    buttons = []
    for name, count in people_list:
        label = f"👤 {name} ({count})"
        buttons.append([InlineKeyboardButton(label, callback_data=f"people_show:{name}")])
    buttons.append([InlineKeyboardButton("🔙 חזור", callback_data="cmd:main")])
    return InlineKeyboardMarkup(buttons)

def person_items_keyboard(items, person):
    """One ✅ button per agenda item; tapping marks it done."""
    buttons = []
    for row in items:
        item_id = row[0]
        content = row[3][:35] + ("…" if len(row[3]) > 35 else "")
        buttons.append([InlineKeyboardButton(f"✅ {content}", callback_data=f"people_done:{item_id}")])
    buttons.append([InlineKeyboardButton("🔙 רשימת אנשים", callback_data="cmd:people")])
    return InlineKeyboardMarkup(buttons)

# ── Command handlers ───────────────────────────────────────────────────────────

async def start(update, context):
    chat_id = update.effective_chat.id
    name = db.get_user_name(chat_id)
    if name:
        await update.effective_message.reply_text(
            f"היי {name}! 👋 אני כאן ומוכן.\n"
            "שלח לי קול, טקסט או תמונה — אשמור הכל מייד.",
            reply_markup=reply_keyboard(),
        )
    else:
        context.user_data['awaiting_name'] = True
        await update.effective_message.reply_text(
            "היי! אני המזכיר שלך 🤖\n\nלפני שמתחילים — איך קוראים לך?"
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
        "/people — אנשים עם נושאים\n"
        "/notes — הערות שמורות\n"
        "/reminders — תזכורות פעילות\n"
        "/focus — המיקוד של היום\n"
        "/focusblock — בלוק עבודה ממוקדת\n"
        "/history — מה שבוצע\n"
        "/tip — טיפ מינימליזם\n"
        "/export — ייצוא ל-CSV\n"
        "/menu — תפריט כפתורים",
        parse_mode="Markdown",
        reply_markup=reply_keyboard(),
    )

async def menu_cmd(update, context):
    await update.effective_message.reply_text("תפריט:", reply_markup=reply_keyboard())

async def list_cmd(update, context):
    chat_id = update.effective_chat.id
    items = db.get_items(chat_id, type_="task", done=0)
    if not items:
        await update.effective_message.reply_text("אין משימות פתוחות 🎉", reply_markup=reply_keyboard())
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
        await update.effective_message.reply_text("אין פריטים להיום ✨", reply_markup=reply_keyboard())
        return
    text = f"📅 *היום — {_today().strftime('%d/%m/%Y')}:*\n\n"
    for row in items:
        emoji = {"task": "☐", "note": "📝", "reminder": "⏰"}.get(row[2], "•")
        time_str = f" {row[5]}" if row[5] else ""
        text += f"{emoji} {row[3]}{time_str}\n"
    await update.effective_message.reply_text(text, parse_mode="Markdown", reply_markup=task_list_keyboard(items))

async def tomorrow_cmd(update, context):
    chat_id = update.effective_chat.id
    tomorrow = date.today() + timedelta(days=1)
    items = db.get_tomorrow_items(chat_id)
    if not items:
        await update.effective_message.reply_text("אין פריטים למחר 🎉", reply_markup=reply_keyboard())
        return
    text = f"📅 *מחר — {tomorrow.strftime('%d/%m/%Y')}:*\n\n"
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
    top_today = today_items[:3]
    today_ids = {r[0] for r in today_items}
    upcoming = [t for t in all_tasks if t[0] not in today_ids][:3]
    if not top_today and not upcoming:
        text = "🎯 אין משימות פתוחות — יום פנוי! ✨"
    else:
        text = "🎯 *מיקוד:*\n\n"
        if top_today:
            text += "*היום:*\n"
            for item in top_today:
                time_str = f" {item[5]}" if item[5] else ""
                text += f"• {item[3]}{time_str}\n"
        if upcoming:
            text += "\n*בקרוב:*\n"
            for item in upcoming:
                date_str = f" ({item[4]})" if item[4] else ""
                text += f"• {item[3]}{date_str}\n"
    await update.effective_message.reply_text(text, parse_mode="Markdown", reply_markup=main_keyboard())

async def focusblock_cmd(update, context):
    text = (
        "🔒 *בלוק מיקוד — 25 דקות*\n\n"
        "כבה התראות. סגור טאבים מיותרים.\n"
        "בחר משימה אחת — ועשה שק אותה.\n\n"
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
        emoji = {"task": "✅", "note": "📝", "reminder": "⏰", "agenda": "👤"}.get(row[2], "•")
        text += f"{emoji} {row[3]}\n"
    await update.effective_message.reply_text(text, parse_mode="Markdown", reply_markup=main_keyboard())

async def export_cmd(update, context):
    chat_id = update.effective_chat.id
    rows = db.export_all(chat_id)
    if not rows:
        await update.effective_message.reply_text("אין נתונים לייצוא עדיין.", reply_markup=main_keyboard())
        return
    buf = io.StringIO()
    buf.write("﻿")
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

async def people_cmd(update, context):
    """Show list of people with pending agenda items."""
    chat_id = update.effective_chat.id
    people = db.get_people(chat_id)
    if not people:
        await update.effective_message.reply_text(
            "אין אנשים עם נושאים ממתינים 👥\n\n"
            "כדי להוסיף: 'רוצה לדבר עם [שם] על [נושא]'",
            reply_markup=main_keyboard(),
        )
        return
    await update.effective_message.reply_text(
        "👥 *אנשים עם נושאים:*\n\nבחר אדם:",
        parse_mode="Markdown",
        reply_markup=people_keyboard(people),
    )

# ── Message handlers ───────────────────────────────────────────────────────────

async def handle_text(update, context):
    text = update.effective_message.text.strip()
    chat_id = update.effective_chat.id
    logger.info(f"TEXT from {chat_id}: {text[:60]}")
    # Name capture flow
    if context.user_data.get('awaiting_name'):
        name = text.strip().split()[0]  # take first word as first name
        db.set_user_name(chat_id, name)
        context.user_data['awaiting_name'] = False
        await update.effective_message.reply_text(
            f"נעים מאוד {name}! 🙌 מעכשיו אני מכיר אותך.\n"
            "שלח לי קול, טקסט או תמונה — אשמור הכל מייד.",
            reply_markup=reply_keyboard(),
        )
        return
    if text in ("/list", "רשימה", "📋 משימות"):
        return await list_cmd(update, context)
    if text in ("/today", "היום", "📅 היום"):
        return await today_cmd(update, context)
    if text in ("/tomorrow", "מחר", "📅 מחר"):
        return await tomorrow_cmd(update, context)
    if text in ("/export", "ייצוא"):
        return await export_cmd(update, context)
    if text in ("/people", "אנשים", "👥 אנשים"):
        return await people_cmd(update, context)
    await _process_content(update, chat_id, text, context=context)

async def handle_voice(update, context):
    chat_id = update.effective_chat.id
    logger.info(f"VOICE from {chat_id}")
    voice = update.message.voice
    file = await context.bot.get_file(voice.file_id)
    audio_bytes = bytes(await file.download_as_bytearray())
    await update.effective_message.reply_text("🎤 מתמלל…")
    try:
        text = await llm.transcribe(audio_bytes, "audio.ogg")
    except Exception as e:
        logger.error(f"Transcription error: {e}")
        await update.effective_message.reply_text("לא הצלחתי לתמלל. נסה שוב.", reply_markup=main_keyboard())
        return
    await _process_content(update, chat_id, text, voice_text=text, context=context)

async def handle_photo(update, context):
    chat_id = update.effective_chat.id
    photo = update.message.photo[-1]
    file = await context.bot.get_file(photo.file_id)
    image_bytes = bytes(await file.download_as_bytearray())
    await update.effective_message.reply_text("🖼 מנתח תמונה…")
    try:
        description = await llm.describe_image(image_bytes)
    except Exception as e:
        logger.error(f"Vision error: {e}")
        await update.effective_message.reply_text("לא הצלחתי לנתח את התמונה.", reply_markup=main_keyboard())
        return
    item_id = db.save_item(chat_id, "note", f"[תמונה] {description}")
    await update.effective_message.reply_text(
        f"📝 שמרתי:\n_{description}_",
        parse_mode="Markdown",
        reply_markup=save_confirm_keyboard(item_id, "note"),
    )

async def _process_content(update, chat_id, text, voice_text=None, context=None):
    try:
        result = await llm.classify(text)
        _ct = result.get('type'); _cc = str(result.get('content',''))[:40]
        logger.info(f"Classify: type={_ct}, content={_cc}")
    except Exception as e:
        logger.error(f"Classification error: {e}")
        await update.effective_message.reply_text("אופס, שגיאה. נסה שוב.", reply_markup=main_keyboard())
        return

    msg_type = result.get("type", "note")
    content = result.get("content", text)
    due_date = result.get("date")
    due_time = result.get("time")
    recurring = result.get("recurring")

    # ── Agenda item: something to discuss with a named person ──
    if msg_type == "agenda":
        person = (result.get("person") or "").strip()
        if not person:
            item_id = db.save_item(chat_id, "note", content)
            await update.effective_message.reply_text(
                f"📝 שמרתי: *{content}*",
                parse_mode="Markdown",
                reply_markup=main_keyboard(),
            )
            return
        similar = db.find_similar_person(chat_id, person)
        if similar:
            context.user_data["pending_agenda"] = {
                "content": content, "person": person, "similar": similar
            }
            keyboard = InlineKeyboardMarkup([[
                InlineKeyboardButton("כן, אחד הם", callback_data="people_merge_yes"),
                InlineKeyboardButton("לא, אדם אחר", callback_data="people_merge_no"),
            ]])
            await update.effective_message.reply_text(
                f"האם *{person}* הוא אותו אדם כמו *{similar}*?",
                parse_mode="Markdown",
                reply_markup=keyboard,
            )
            return
        item_id = db.save_item(chat_id, "agenda", content, person=person)
        await update.effective_message.reply_text(
            f"👤 *{person}* — {content}\n\nנשמר לאג'נדה!",
            parse_mode="Markdown",
            reply_markup=save_confirm_keyboard(item_id, "agenda"),
        )
        return

    # ── People query: "מה רציתי לדבר עם X?" ──
    if msg_type == "chat_people_query":
        person = (result.get("person") or "").strip()
        if not person:
            reply = await llm.chat(text)
            await update.effective_message.reply_text(reply, reply_markup=main_keyboard())
            return
        items = db.get_items_by_person(chat_id, person)
        if not items:
            similar = db.find_similar_person(chat_id, person)
            if similar:
                items = db.get_items_by_person(chat_id, similar)
                person = similar
        if not items:
            await update.effective_message.reply_text(
                f"אין נושאים ממתינים עם {person} 🎉",
                reply_markup=main_keyboard(),
            )
            return
        msg_text = f"👤 *{person}:*\n\n"
        for row in items:
            msg_text += f"• {row[3]}\n"
        await update.effective_message.reply_text(
            msg_text,
            parse_mode="Markdown",
            reply_markup=person_items_keyboard(items, person),
        )
        return

    if msg_type == "chat":
        data_keywords = ["משימות", "תזכורות", "היום", "כמה", "יש לי", "הערות", "פתוחות", "רשימה", "מה יש"]
        if any(kw in text for kw in data_keywords):
            tasks = db.get_items(chat_id, type_="task", done=0)
            reminders = db.get_items(chat_id, type_="reminder", done=0)
            notes = db.get_items(chat_id, type_="note", done=0)
            today_items = db.get_today_items(chat_id)
            summary = (
                f"משימות פתוחות ({len(tasks)}): {', '.join(r[3][:30] for r in tasks[:8])}\n"
                f"תזכורות פעילות ({len(reminders)}): {', '.join(r[3][:30] for r in reminders[:5])}\n"
                f"הערות ({len(notes)}): {', '.join(r[3][:30] for r in notes[:5])}\n"
                f"היום ({len(today_items)}): {', '.join(r[3][:30] for r in today_items[:5])}"
            )
            try:
                reply = await llm.chat_with_context(text, summary)
            except Exception as e:
                logger.error(f"Chat error: {e}")
                reply = "לא הצלחתי לענות, נסה שוב."
        else:
            try:
                reply = await llm.chat(text)
            except Exception as e:
                logger.error(f"Chat error: {e}")
                reply = "לא הצלחתי לענות, נסה שוב."
        await update.effective_message.reply_text(reply, reply_markup=main_keyboard())
        return

    if msg_type in ("task", "reminder") and due_time and not due_date:
        now = _now()
        try:
            hour, minute = map(int, due_time.split(":"))
            today_dt = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if today_dt > now:
                due_date = now.date().isoformat()
            else:
                context.user_data["pending"] = {
                    "type": msg_type, "content": content,
                    "recurring": recurring, "voice_text": voice_text,
                }
                try:
                    suggestions = await llm.suggest_times(content)
                except Exception:
                    suggestions = llm._fallback_suggestions()
                msg = f"השעה {due_time} כבר עברה היום.\nבחר מועד אחר:"
                await update.effective_message.reply_text(msg, reply_markup=smart_time_keyboard(suggestions))
                return
        except Exception:
            due_date = now.date().isoformat()

    if (msg_type == "task" and not due_date) or (msg_type == "reminder" and not due_date and not due_time):
        if context is not None:
            context.user_data["pending"] = {
                "type": msg_type, "content": content,
                "recurring": recurring, "voice_text": voice_text,
            }
        emoji = "✅" if msg_type == "task" else "⏰"
        await update.effective_message.reply_text("⏳ חושב על מועדים…")
        try:
            suggestions = await llm.suggest_times(content)
        except Exception:
            suggestions = llm._fallback_suggestions()
        await update.effective_message.reply_text(
            f"{emoji} *{content}*\n\nמתי להזכיר לך?",
            parse_mode="Markdown",
            reply_markup=smart_time_keyboard(suggestions),
        )
        return

    await _save_and_confirm(update, chat_id, msg_type, content, due_date, due_time, recurring, voice_text)

async def _save_and_confirm(update, chat_id, msg_type, content, due_date, due_time, recurring, voice_text=None):
    item_id = db.save_item(chat_id, msg_type, content, due_date, due_time, recurring)
    emoji = {"task": "✅", "note": "📝", "reminder": "⏰", "agenda": "👤"}.get(msg_type, "💾")
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
        f"{emoji} *{content}*{details}",
        parse_mode="Markdown",
        reply_markup=save_confirm_keyboard(item_id, msg_type),
    )

# ── Callback query handler ─────────────────────────────────────────────────────

async def handle_callback(update, context):
    query = update.callback_query
    await query.answer()
    data = query.data
    chat_id = update.effective_chat.id

    if data == "cmd:list": return await list_cmd(update, context)
    if data == "cmd:today": return await today_cmd(update, context)
    if data == "cmd:tomorrow": return await tomorrow_cmd(update, context)
    if data == "cmd:export": return await export_cmd(update, context)
    if data == "cmd:help": return await help_cmd(update, context)
    if data == "cmd:people": return await people_cmd(update, context)
    if data == "cmd:main":
        await query.edit_message_text("תפריט ראשי:", reply_markup=main_keyboard())
        return
    if data == "clear_cancel":
        await query.edit_message_text("ביטול. לא נמחק כלום.", reply_markup=main_keyboard())
        return
    if data == "noop":
        return

    # ── People deduplication answers ──
    if data == "people_merge_yes":
        pending = context.user_data.pop("pending_agenda", None)
        if not pending:
            await query.edit_message_text("לא נמצא פריט ממתין.", reply_markup=main_keyboard())
            return
        item_id = db.save_item(chat_id, "agenda", pending["content"], person=pending["similar"])
        await query.edit_message_text(
            f"👤 נשמר תחת *{pending['similar']}*: {pending['content']}",
            parse_mode="Markdown",
            reply_markup=save_confirm_keyboard(item_id, "agenda"),
        )
        return

    if data == "people_merge_no":
        pending = context.user_data.pop("pending_agenda", None)
        if not pending:
            await query.edit_message_text("לא נמצא פריט ממתין.", reply_markup=main_keyboard())
            return
        item_id = db.save_item(chat_id, "agenda", pending["content"], person=pending["person"])
        await query.edit_message_text(
            f"👤 נשמר תחת *{pending['person']}*: {pending['content']}",
            parse_mode="Markdown",
            reply_markup=save_confirm_keyboard(item_id, "agenda"),
        )
        return

    parts = data.split(":", 1)
    if len(parts) != 2:
        return
    action, param = parts

    if action == "setdatetime":
        pending = context.user_data.get("pending")
        if not pending:
            await query.edit_message_text("לא נמצא פריט ממתין.", reply_markup=main_keyboard())
            return
        dt_parts = param.split("|", 1)
        selected_date = dt_parts[0] if dt_parts[0] else None
        selected_time = dt_parts[1] if len(dt_parts) > 1 and dt_parts[1] != "none" else None
        item_id = db.save_item(chat_id, pending["type"], pending["content"],
                               selected_date, selected_time, pending.get("recurring"))
        context.user_data.pop("pending", None)
        emoji = "✅" if pending["type"] == "task" else "⏰"
        label = "משימה" if pending["type"] == "task" else "תזכורת"
        details = ""
        if selected_date:
            details += f"\n📅 {selected_date}"
        if selected_time:
            details += f" ⏰ {selected_time}"
        await query.edit_message_text(
            f"{emoji} נשמר כ*{label}*: {pending['content']}{details}",
            parse_mode="Markdown",
            reply_markup=save_confirm_keyboard(item_id, pending["type"]),
        )
        return

    if action == "reschedule":
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
            details += f"\n📅 {new_date}"
        if new_time:
            details += f" ⏰ {new_time}"
        await query.edit_message_text(
            f"📅 תזכורת נדחתה!{details}",
            parse_mode="Markdown",
            reply_markup=main_keyboard(),
        )
        return

    if action == "cancel_item":
        try:
            item_id = int(param)
        except ValueError:
            return
        db.mark_done(item_id)
        await query.edit_message_text("🗑 משימה בוטלה.", reply_markup=main_keyboard())
        return

    if action == "people_show":
        person = param
        items = db.get_items_by_person(chat_id, person)
        if not items:
            await query.edit_message_text(
                f"אין נושאים פתוחים עם {person} 🎉",
                reply_markup=people_keyboard(db.get_people(chat_id)),
            )
            return
        msg_text = f"👤 *{person}:*\n\n"
        for row in items:
            msg_text += f"• {row[3]}\n"
        await query.edit_message_text(
            msg_text,
            parse_mode="Markdown",
            reply_markup=person_items_keyboard(items, person),
        )
        return

    if action == "people_done":
        try:
            item_id = int(param)
        except ValueError:
            return
        conn = db.get_conn()
        row = conn.execute("SELECT person FROM items WHERE id=?", (item_id,)).fetchone()
        person = row[0] if row else None
        db.mark_done(item_id)
        if person:
            remaining = db.get_items_by_person(chat_id, person)
            if remaining:
                msg_text = f"✅ סומן כבוצע!\n\n👤 *{person}:*\n\n" + "".join(f"• {r[3]}\n" for r in remaining)
                await query.edit_message_text(
                    msg_text,
                    parse_mode="Markdown",
                    reply_markup=person_items_keyboard(remaining, person),
                )
                return
        people = db.get_people(chat_id)
        if people:
            await query.edit_message_text(
                "✅ סומן כבוצע!\n\n👥 *אנשים עם נושאים:*",
                parse_mode="Markdown",
                reply_markup=people_keyboard(people),
            )
        else:
            await query.edit_message_text("✅ סומן כבוצע! אין עוד נושאים ממתינים 🎉", reply_markup=main_keyboard())
        return

    try:
        item_id = int(param)
    except ValueError:
        return

    if action == "done":
        db.mark_done(item_id)
        undo_kb = InlineKeyboardMarkup([[InlineKeyboardButton("↩️ בטל", callback_data=f"undo:{item_id}")]])
        await query.edit_message_text("✅ סומן כבוצע!", reply_markup=undo_kb)
    elif action == "undo":
        db.mark_undone(item_id)
        await query.edit_message_text("↩️ המשימה הוחזרה לרשימה.", reply_markup=main_keyboard())
    elif action == "delete":
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔴 כן, מחק", callback_data=f"delete_confirm:{item_id}"),
             InlineKeyboardButton("❌ ביטול", callback_data=f"saved:{item_id}")],
        ])
        await query.edit_message_text("⚠️ למחוק לצמיתות?", reply_markup=keyboard)
    elif action == "delete_confirm":
        db.delete_item(item_id)
        await query.edit_message_text("🗑 נמחק.", reply_markup=main_keyboard())
    elif action == "snooze1h":
        db.snooze_item(item_id, hours=1)
        await query.edit_message_text("⏰ נדחה בשעה אחת.", reply_markup=main_keyboard())
    elif action == "tomorrow":
        db.postpone_to_tomorrow(item_id)
        await query.edit_message_text("📅 נדחה למחר.", reply_markup=main_keyboard())
    elif action == "clear_confirm":
        count = db.count_items_by_type(chat_id, None if param == "all" else param)
        type_label = {"task": "משימות", "reminder": "תזכורות", "note": "הערות", "all": "כל הפריטים"}.get(param, param)
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("✔️ כן, המשך", callback_data=f"clear_final:{param}")],
            [InlineKeyboardButton("❌ ביטול", callback_data="clear_cancel")],
        ])
        await query.edit_message_text(
            f"❓ *אימות ראשון*\nרוצה למחוק את {type_label}?\n_פעולה זו לא ניתנת לביטול._",
            parse_mode="Markdown", reply_markup=keyboard
        )
    elif action == "clear_final":
        count = db.count_items_by_type(chat_id, param)
        type_label = {
            "task": "משימות",
            "reminder": "תזכורות",
            "note": "הערות",
            "all": "פריטים"
        }.get(param, param)
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔴 כן, מחק הכל", callback_data=f"clear_execute:{param}")],
            [InlineKeyboardButton("❌ ביטול", callback_data="clear_cancel")],
        ])
        await query.edit_message_text(
            f"⚠️ *אזהרה אחרונה!*\nאתה עומד למחוק {count} {type_label} לצמיתות.\n*לא ניתן לשחזר.*\n\nהאם אתה בטוח לגמרי?",
            parse_mode="Markdown", reply_markup=keyboard
        )
    elif action == "clear_execute":
        deleted = db.delete_items_by_type(chat_id, None if param == "all" else param)
        type_label = {
            "task": "משימות",
            "reminder": "תזכורות",
            "note": "הערות",
            "all": "פריטים"
        }.get(param, param)
        await query.edit_message_text(f"✅ נמחקו {deleted} {type_label}.", reply_markup=main_keyboard())
    elif action == "saved":
        await query.answer("כבר נשמר ✓", show_alert=False)

async def clear_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Full bot reset — straight to delete all with 2 confirmations."""
    chat_id = update.effective_chat.id
    total = db.count_items_by_type(chat_id, "all")
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("⚠️ כן, המשך לאיפוס", callback_data="clear_confirm:all")],
        [InlineKeyboardButton("❌ ביטול", callback_data="clear_cancel")],
    ])
    await update.effective_message.reply_text(
        f"🗂 *איפוס הבוט*\n\nיש לך {total} פריטים שמורים.\nהאם למחוק את *הכל*?",
        parse_mode="Markdown",
        reply_markup=keyboard
    )
