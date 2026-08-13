"""
Entry point for מזכיר מינימליסטי bot.
"""
import logging
from telegram import BotCommand
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)
import db
import handlers
import scheduler as sched
from config import TELEGRAM_BOT_TOKEN

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

BOT_COMMANDS = [
    BotCommand("start", "התחלה והצגת עצמי"),
    BotCommand("help", "עזרה ורשימת פקודות"),
    BotCommand("list", "משימות פתוחות"),
    BotCommand("today", "משימות להיום"),
    BotCommand("people", "אנשים עם נושאים ממתינים"),
    BotCommand("notes", "הערות שמורות"),
    BotCommand("reminders", "תזכורות פעילות"),
    BotCommand("focus", "מיקוד היום — מה הכי חשוב"),
    BotCommand("focusblock", "בלוק עבודה ממוקדת 25 דקות"),
    BotCommand("tip", "טיפ מינימליזם"),
    BotCommand("history", "מה שבוצע לאחרונה"),
    BotCommand("export", "ייצוא כל הנתונים ל-CSV"),
    BotCommand("menu", "תפריט כפתורים"),
]

async def post_init(app: Application):
    db.init_db()
    logger.info("Database initialized.")

    await app.bot.set_my_commands(BOT_COMMANDS)
    logger.info("Bot commands registered.")

    scheduler = sched.setup_scheduler(app)
    scheduler.start()
    logger.info("Scheduler started.")
    app.bot_data["scheduler"] = scheduler

async def post_shutdown(app: Application):
    scheduler = app.bot_data.get("scheduler")
    if scheduler:
        scheduler.shutdown()

def main():
    app = (
        Application.builder()
        .token(TELEGRAM_BOT_TOKEN)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )

    # Core commands
    app.add_handler(CommandHandler("start", handlers.start))
    app.add_handler(CommandHandler("help", handlers.help_cmd))
    app.add_handler(CommandHandler("list", handlers.list_cmd))
    app.add_handler(CommandHandler("today", handlers.today_cmd))
    app.add_handler(CommandHandler("export", handlers.export_cmd))
    app.add_handler(CommandHandler("clear", handlers.clear_cmd))
    app.add_handler(CommandHandler("menu", handlers.menu_cmd))
    app.add_handler(CommandHandler("people", handlers.people_cmd))

    # New commands
    app.add_handler(CommandHandler("notes", handlers.notes_cmd))
    app.add_handler(CommandHandler("reminders", handlers.reminders_cmd))
    app.add_handler(CommandHandler("focus", handlers.focus_cmd))
    app.add_handler(CommandHandler("focusblock", handlers.focusblock_cmd))
    app.add_handler(CommandHandler("tip", handlers.tip_cmd))
    app.add_handler(CommandHandler("history", handlers.history_cmd))

    # Messages
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handlers.handle_text))
    app.add_handler(MessageHandler(filters.VOICE, handlers.handle_voice))
    app.add_handler(MessageHandler(filters.PHOTO, handlers.handle_photo))

    # Inline button callbacks
    app.add_handler(CallbackQueryHandler(handlers.handle_callback))

    logger.info("Bot starting with polling…")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
