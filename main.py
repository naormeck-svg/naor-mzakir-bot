"""
Entry point for מזכיר מינימליסטי bot.
"""
import logging
import asyncio
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


async def post_init(app: Application):
    db.init_db()
    logger.info("Database initialized.")
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
    app.add_handler(CommandHandler("start", handlers.start))
    app.add_handler(CommandHandler("help", handlers.help_cmd))
    app.add_handler(CommandHandler("list", handlers.list_cmd))
    app.add_handler(CommandHandler("today", handlers.today_cmd))
    app.add_handler(CommandHandler("export", handlers.export_cmd))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handlers.handle_text))
    app.add_handler(MessageHandler(filters.VOICE, handlers.handle_voice))
    app.add_handler(MessageHandler(filters.PHOTO, handlers.handle_photo))
    app.add_handler(CallbackQueryHandler(handlers.handle_callback))
    logger.info("Bot starting with polling...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
