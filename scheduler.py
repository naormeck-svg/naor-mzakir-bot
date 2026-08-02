"""Scheduled jobs: morning digest + reminder check."""
import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from telegram import Bot
from telegram.ext import Application
import db
from config import TIMEZONE, MORNING_HOUR, MORNING_MINUTE
import handlers

logger = logging.getLogger(__name__)

async def send_morning_digest(bot):
    chat_ids = db.get_all_chat_ids()
    for chat_id in chat_ids:
        try:
            tasks, reminders, overdue = db.get_summary_for_digest(chat_id)
            if tasks == 0 and reminders == 0 and overdue == 0:
                continue
            lines = ["☀️ *בוקר טוב! הנה מה שיש להיום:*\n"]
            if tasks > 0: lines.append(f"📋 {tasks} משימות להיום")
            if reminders > 0: lines.append(f"⏰ {reminders} תזכורות להיום")
            if overdue > 0: lines.append(f"⚠️ {overdue} פריטים שלא בוצעו מימים קודמים")
            lines.append("\nשלח /today לפירוט.")
            await bot.send_message(chat_id=chat_id, text="\n".join(lines), parse_mode="Markdown", reply_markup=handlers.main_keyboard())
        except Exception as e:
            logger.error(f"Morning digest error for {chat_id}: {e}")

async def check_reminders(bot):
    due = db.get_due_reminders()
    for row in due:
        item_id, chat_id, _, content, _, _, recurring = row[0], row[1], row[2], row[3], row[4], row[5], row[6]
        try:
            await bot.send_message(chat_id=chat_id, text=f"⏰ *תזכורת:* {content}", parse_mode="Markdown", reply_markup=handlers.reminder_keyboard(item_id))
            db.mark_reminded(item_id)
            if recurring: db.handle_recurring(item_id)
        except Exception as e:
            logger.error(f"Reminder error for item {item_id}: {e}")

def setup_scheduler(app):
    scheduler = AsyncIOScheduler(timezone=TIMEZONE)
    bot = app.bot
    scheduler.add_job(send_morning_digest, CronTrigger(hour=MORNING_HOUR, minute=MORNING_MINUTE, timezone=TIMEZONE), args=[bot], id="morning_digest", replace_existing=True)
    scheduler.add_job(check_reminders, "interval", minutes=1, args=[bot], id="reminder_check", replace_existing=True)
    return scheduler
