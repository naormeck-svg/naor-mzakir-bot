import os
from dotenv import load_dotenv
load_dotenv()
TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
GROQ_API_KEY = os.environ["GROQ_API_KEY"]
TURSO_DATABASE_URL = os.environ["TURSO_DATABASE_URL"]
TURSO_AUTH_TOKEN = os.environ["TURSO_AUTH_TOKEN"]
GROQ_MODEL = "openai/gpt-oss-120b"
GROQ_VISION_MODEL = "openai/gpt-oss-120b"
WHISPER_MODEL = "whisper-large-v3"
TIMEZONE = "Asia/Jerusalem"
MORNING_HOUR = 8
MORNING_MINUTE = 0
