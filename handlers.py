"""All Telegram bot handlers."""
import io, csv, logging
from datetime import date
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
import llm, db

logger = logging.getLogger(__name__)

def main_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📋 משימות", callback_data="cmd:list"), InlineKeyboardButton("📅 היום", callback_data="cmd:today")],
        [InlineKeyboardButton("📤 ייצוא", callback_data="cmd:export"), InlineKeyboardButton("❓ עזרה", callback_data="cmd:help")],
    ])

def save_confirm_keyboard(item_id, type_):
    type_label = {"task": "✅ משימה", "note": "📝 הערה", "reminder": "⏰ תזכורת"}.get(type_, type_)
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"נשמר כ{type_label} ✓", callback_data=f"saved:{item_id}")],
        [InlineKeyboardButton("🗑 מחק", callback_data=f"delete:{item_id}"), InlineKeyboardButton("📋 כל המשימות", callback_data="cmd:list")],
    ])

def reminder_keyboard(item_id):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ סיימתי", callback_data=f"done:{item_id}")],
        [InlineKeyboardButton("⏰ דחה שעה", callback_data=f"snooze1h:{item_id}"), InlineKeyboardButton("📅 למחר", callback_data=f"tomorrow:{item_id}")],
    ])

def task_list_keyboard(items):
    buttons = [[InlineKeyboardButton(f"✅ {row[3][:30]}{'…' if len(row[3]) > 30 else ''}", callback_data=f"done:{row[0]}")] for row in items]
    buttons.append([InlineKeyboardButton("🔙 חזור", callback_data="cmd:main")])
    return InlineKeyboardMarkup(buttons)

async def start(update, context):
    await update.message.reply_text("שלום! אני המזכיר שלך 🤖\n\nשלח לי קול, טקסט או תמונה — אשמור הכל מייד.", reply_markup=main_keyboard())

async def help_cmd(update, context):
    await update.message.reply_text("מה אני יכול לעשות:\n\n🎤 *קול* — אוגר ומסווג אוטומטית\n💬 *טקסט* — אותו דבר\n🖼 *תמונה* — תיאור ושמירה\n\nפקודות:\n/list — כל המשימות\n/today — משימות להיום\n/export — ייצוא ל-CSV", parse_mode="Markdown", reply_markup=main_keyboard())

async def list_cmd(update, context):
    chat_id = update.effective_chat.id
    items = db.get_items(chat_id, type_="task", done=0)
    if not items:
        await update.effective_message.reply_text("אין משימות פתוחות 🎉", reply_markup=main_keyboard()); return
    text = "📋 *משימות פתוחות:*\n\n" + "".join(f"• {row[3]}{' — ' + row[4] if row[4] else ''}\n" for row in items)
    await update.effective_message.reply_text(text, parse_mode="Markdown", reply_markup=task_list_keyboard(items))

async def today_cmd(update, context):
    chat_id = update.effective_chat.id
    items = db.get_today_items(chat_id)
    if not items:
        await update.effective_message.reply_text("אין פריטים להיום ✨", reply_markup=main_keyboard()); return
    text = f"📅 *היום — {date.today().strftime('%d/%m/%Y')}:*\n\n"
    for row in items:
        emoji = {"task": "☐", "note": "📝", "reminder": "⏰"}.get(row[2], "•")
        text += f"{emoji} {row[3]}{' ' + row[5] if row[5] else ''}\n"
    await update.effective_message.reply_text(text, parse_mode="Markdown", reply_markup=task_list_keyboard(items))

async def export_cmd(update, context):
    chat_id = update.effective_chat.id
    rows = db.export_all(chat_id)
    if not rows:
        await update.effective_message.reply_text("אין נתונים לייצוא עדיין.", reply_markup=main_keyboard()); return
    buf = io.StringIO()
    buf.write("\ufeff")
    writer = csv.writer(buf)
    writer.writerow(["ID", "סוג", "תוכן", "תאריך", "שעה", "חוזר", "בוצע", "נוצר"])
    for row in rows:
        writer.writerow([row[0], row[1], row[2], row[3] or "", row[4] or "", row[5] or "", "כן" if row[6] else "לא", row[7]])
    buf.seek(0)
    await update.effective_message.reply_document(document=io.BytesIO(buf.getvalue().encode("utf-8-sig")), filename=f"מזכיר_{date.today().isoformat()}.csv", caption="הנה כל הנתונים שלך 📊")

async def handle_text(update, context):
    text = update.message.text.strip()
    chat_id = update.effective_chat.id
    if text in ("/list", "רשימה"): return await list_cmd(update, context)
    if text in ("/today", "היום"): return await today_cmd(update, context)
    if text in ("/export", "ייצוא"): return await export_cmd(update, context)
    await _process_content(update, chat_id, text)

async def handle_voice(update, context):
    chat_id = update.effective_chat.id
    file = await context.bot.get_file(update.message.voice.file_id)
    audio_bytes = bytes(await file.download_as_bytearray())
    await update.message.reply_text("🎤 מתמלל…")
    try:
        text = await llm.transcribe(audio_bytes, "audio.ogg")
    except Exception as e:
        logger.error(f"Transcription error: {e}")
        await update.message.reply_text("לא הצלחתי לתמלל. נסה שוב.", reply_markup=main_keyboard()); return
    await _process_content(update, chat_id, text, voice_text=text)

async def handle_photo(update, context):
    chat_id = update.effective_chat.id
    file = await context.bot.get_file(update.message.photo[-1].file_id)
    image_bytes = bytes(await file.download_as_bytearray())
    await update.message.reply_text("🖼 מנתח תמונה…")
    try:
        description = await llm.describe_image(image_bytes)
    except Exception as e:
        logger.error(f"Vision error: {e}")
        await update.message.reply_text("לא הצלחתי לנתח את התמונה.", reply_markup=main_keyboard()); return
    item_id = db.save_item(chat_id, "note", f"[תמונה] {description}")
    await update.message.reply_text(f"📝 שמרתי:\n_{description}_", parse_mode="Markdown", reply_markup=save_confirm_keyboard(item_id, "note"))

async def _process_content(update, chat_id, text, voice_text=None):
    try:
        result = await llm.classify(text)
    except Exception as e:
        logger.error(f"Classification error: {e}")
        await update.message.reply_text("אופס, שגיאה. נסה שוב.", reply_markup=main_keyboard()); return
    msg_type = result.get("type", "note")
    content = result.get("content", text)
    due_date, due_time, recurring = result.get("date"), result.get("time"), result.get("recurring")
    if msg_type == "chat":
        try: reply = await llm.chat(text)
        except: reply = "לא הצלחתי לענות, נסה שוב."
        await update.message.reply_text(reply, reply_markup=main_keyboard()); return
    item_id = db.save_item(chat_id, msg_type, content, due_date, due_time, recurring)
    emoji = {"task": "✅", "note": "📝", "reminder": "⏰"}.get(msg_type, "💾")
    label = {"task": "משימה", "note": "הערה", "reminder": "תזכורת"}.get(msg_type, "פריט")
    details = ""
    if voice_text and voice_text != content: details += f"\n🎤 _{voice_text}_"
    if due_date: details += f"\n📅 {due_date}"
    if due_time: details += f" ⏰ {due_time}"
    if recurring:
        rl = {"daily": "כל יום", "weekly:sun": "כל ראשון", "weekly:mon": "כל שני", "weekly:fri": "כל שישי", "monthly": "כל חודש"}
        details += f"\n🔄 {rl.get(recurring, recurring)}"
    await update.message.reply_text(f"{emoji} נשמר כ*{label}*: {content}{details}", parse_mode="Markdown", reply_markup=save_confirm_keyboard(item_id, msg_type))

async def handle_callback(update, context):
    query = update.callback_query
    await query.answer()
    data = query.data
    if data == "cmd:list": return await list_cmd(update, context)
    if data == "cmd:today": return await today_cmd(update, context)
    if data == "cmd:export": return await export_cmd(update, context)
    if data == "cmd:help": return await help_cmd(update, context)
    if data == "cmd:main":
        await query.edit_message_text("תפריט ראשי:", reply_markup=main_keyboard()); return
    parts = data.split(":", 1)
    if len(parts) != 2: return
    action, item_id_str = parts
    try: item_id = int(item_id_str)
    except: return
    if action == "done":
        db.mark_done(item_id); await query.edit_message_text("✅ סומן כבוצע!", reply_markup=main_keyboard())
    elif action == "delete":
        db.mark_done(item_id); await query.edit_message_text("🗑 נמחק.", reply_markup=main_keyboard())
    elif action == "snooze1h":
        db.snooze_item(item_id, hours=1); await query.edit_message_text("⏰ נדחה בשעה אחת.", reply_markup=main_keyboard())
    elif action == "tomorrow":
        db.postpone_to_tomorrow(item_id); await query.edit_message_text("📅 נדחה למחר.", reply_markup=main_keyboard())
    elif action == "saved":
        await query.answer("כבר נשמר ✓", show_alert=False)
