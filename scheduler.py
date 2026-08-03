"""Scheduled jobs: morning digest + reminder check."""
import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from telegram.ext import Application
import db
import llm
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
            lines = ["☀️ *בוקר טוב! הנה הסיכום שלך:*\n"]
            if tasks > 0:
                lines.append(f"📋 {tasks} משימות להיום")
            if reminders > 0:
                lines.append(f"⏰ {reminders} תזכורות להיום")
            if overdue > 0:
                lines.append(f"⚠️ {overdue} פריטים שעברו מועד")
            await bot.send_message(
                chat_id=chat_id,
                text="\n".join(lines),
                parse_mode="Markdown",
                reply_markup=handlers.main_keyboard(),
            )
        except Exception as e:
            logger.error(f"Morning digest error for {chat_id}: {e}")


async def check_reminders(app):
    """Fire due reminders and show reschedule options."""
    due = db.get_due_reminders()
    for row in due:
        item_id = row[0]
        chat_id = row[1]
        content = row[3]
        try:
            db.mark_reminded(item_id)
            # Get smart reschedule suggestions
            try:
                suggestions = await llm.suggest_times(content)
            except Exception:
                suggestions = llm._fallback_suggestions()

            keyboard = handlers.reschedule_keyboard(item_id, suggestions)
            await app.bot.send_message(
                chat_id=chat_id,
                text=f"⏰ *תזכורת:* {content}\n\nמה תרצה לעשות?",
                parse_mode="Markdown",
                reply_markup=keyboard,
            )
            # Handle recurring
            if row[6]:  # recurring column
                db.handle_recurring(item_id)
        except Exception as e:
            logger.error(f"Reminder send error for item {item_id}: {e}")


def setup_scheduler(app: Application) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone=TIMEZONE)

    scheduler.add_job(
        send_morning_digest,
        CronTrigger(hour=MORNING_HOUR, minute=MORNING_MINUTE, timezone=TIMEZONE),
        args=[app.bot],
        id="morning_digest",
        replace_existing=True,
    )

    scheduler.add_job(
        check_reminders,
        CronTrigger(minute="*", timezone=TIMEZONE),
        args=[app],
        id="reminder_check",
        replace_existing=True,
    )

    return scheduler
