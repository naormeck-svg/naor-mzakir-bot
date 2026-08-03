"""
LLM interface — all Groq API calls live here.
"""
import json
import base64
import httpx
from datetime import datetime, date, timedelta
from zoneinfo import ZoneInfo

_TZ = ZoneInfo("Asia/Jerusalem")
def _now(): return datetime.now(_TZ)
def _today(): return datetime.now(_TZ).date()
from config import GROQ_API_KEY, GROQ_MODEL, GROQ_VISION_MODEL, WHISPER_MODEL
from hebrew_dates import enrich_prompt_with_date_context

GROQ_BASE = "https://api.groq.com/openai/v1"
HEADERS = {
    "Authorization": f"Bearer {GROQ_API_KEY}",
    "Content-Type": "application/json",
}

CLASSIFY_SYSTEM = """You are a classifier for a Hebrew personal assistant Telegram bot.
Classify the user's message and return ONLY valid JSON, nothing else.

Output format:
{{
  "type": "task" | "note" | "reminder" | "chat",
  "content": "<cleaned text in Hebrew>",
  "date": "<ISO date YYYY-MM-DD or null>",
  "time": "<HH:MM or null>",
  "recurring": "daily" | "weekly:sun" | "weekly:mon" | "weekly:tue" | "weekly:wed" | "weekly:thu" | "weekly:fri" | "monthly" | null
}}

Rules:
- "task": something to do with a deadline. Extract date/time if mentioned.
- "reminder": something to remember at a specific time/date. Always has date or time.
- "note": a thought, idea, or piece of information to save. No action required.
- "chat": casual conversation, question, or greeting — do NOT save, just respond.
- Handle Hebrew-English code-switching naturally.
- Resolve relative dates using the date context below.
- If recurring is detected, set the recurring field.
- content should be clean, concise Hebrew (or mixed) text.
- Infinitive phrases (לקרוא, לשלוח, לעשות, לבדוק, etc.) = task.
- Past references ("שבוע שעבר", "אתמול", "לפני X ימים") = note, not recurring.
- "ביום שני" when today is Monday means next Monday (שני הבא), not today.
- recurring ONLY if explicit words: "כל יום", "כל שבוע", "every week", "weekly", "כל חודש".

{date_context}
"""

CHAT_SYSTEM = """You are a friendly, concise Hebrew personal assistant bot named מזכיר.
Respond in Hebrew. Be brief and helpful. Use Israeli conversational tone.
Do not offer to save things — this is a pure chat response."""

CONTEXT_CHAT_SYSTEM = """אתה מזכיר עברי חכם ותמציתי.
יש לך גישה לנתוני המשתמש:
{user_data}

ענה על שאלת המשתמש בהתבסס על הנתונים האלו.
תהיה קצר וישיר. אל תמציא מידע שלא קיים בנתונים."""

SUGGEST_TIMES_SYSTEM = """You are a scheduling assistant for a Hebrew Telegram bot.
The user just added an item and needs to pick a time for it.

{date_context}

CRITICAL RULES:
1. ALL suggested dates and times MUST be strictly in the future (after right now).
2. Never suggest a time that has already passed today.
3. If the current time is after 20:00, do NOT suggest "הערב 20:00" — suggest tomorrow or later instead.
4. Spread suggestions: one soon (within a few hours), one medium (tomorrow or next few days), one later (next week or further).
5. Make labels contextually relevant to the item content.

Return ONLY valid JSON — an array of exactly 3 objects:
[
  {"label": "<short Hebrew label, max 4 words>", "date": "<YYYY-MM-DD>", "time": "<HH:MM>"},
  {"label": "<short Hebrew label, max 4 words>", "date": "<YYYY-MM-DD>", "time": "<HH:MM>"},
  {"label": "<short Hebrew label, max 4 words>", "date": "<YYYY-MM-DD>", "time": "<HH:MM>"}
]
"""


async def classify(text: str) -> dict:
    date_ctx = enrich_prompt_with_date_context()
    system = CLASSIFY_SYSTEM.format(date_context=date_ctx)
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            f"{GROQ_BASE}/chat/completions",
            headers=HEADERS,
            json={
                "model": GROQ_MODEL,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": text},
                ],
                "temperature": 0.1,
                "max_tokens": 200,
            }
        )
        resp.raise_for_status()
        raw = resp.json()["choices"][0]["message"]["content"].strip()
        if "```" in raw:
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {"type": "note", "content": text, "date": None, "time": None, "recurring": None}


async def chat(text: str, history: list = None) -> str:
    messages = [{"role": "system", "content": CHAT_SYSTEM}]
    if history:
        messages.extend(history[-6:])
    messages.append({"role": "user", "content": text})
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            f"{GROQ_BASE}/chat/completions",
            headers=HEADERS,
            json={
                "model": GROQ_MODEL,
                "messages": messages,
                "temperature": 0.7,
                "max_tokens": 300,
            }
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip()


async def chat_with_context(text: str, user_data_summary: str) -> str:
    system = CONTEXT_CHAT_SYSTEM.format(user_data=user_data_summary)
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            f"{GROQ_BASE}/chat/completions",
            headers=HEADERS,
            json={
                "model": GROQ_MODEL,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": text},
                ],
                "temperature": 0.5,
                "max_tokens": 300,
            }
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip()

async def transcribe(audio_bytes: bytes, filename: str = "audio.ogg") -> str:
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{GROQ_BASE}/audio/transcriptions",
            headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
            files={"file": (filename, audio_bytes, "audio/ogg")},
            data={"model": WHISPER_MODEL, "language": "he", "response_format": "text"},
        )
        resp.raise_for_status()
        return resp.text.strip()


async def describe_image(image_bytes: bytes) -> str:
    b64 = base64.b64encode(image_bytes).decode()
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.post(
            f"{GROQ_BASE}/chat/completions",
            headers=HEADERS,
            json={
                "model": GROQ_VISION_MODEL,
                "messages": [{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "תאר את התמונה הזאת בקצרה בעברית. אם יש טקסט — צטט אותו."},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                    ]
                }],
                "max_tokens": 200,
            }
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip()


async def suggest_times(content: str) -> list:
    """Generate 3 smart future time suggestions for a task/reminder."""
    date_ctx = enrich_prompt_with_date_context()
    system = SUGGEST_TIMES_SYSTEM.format(date_context=date_ctx)
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            f"{GROQ_BASE}/chat/completions",
            headers=HEADERS,
            json={
                "model": GROQ_MODEL,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": content},
                ],
                "temperature": 0.4,
                "max_tokens": 200,
            }
        )
        resp.raise_for_status()
        raw = resp.json()["choices"][0]["message"]["content"].strip()
        if "```" in raw:
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        try:
            suggestions = json.loads(raw)
            if isinstance(suggestions, list) and suggestions:
                # Filter out any past times
                now = datetime.now()
                valid = []
                for s in suggestions:
                    try:
                        dt_str = f"{s['date']} {s.get('time', '00:00')}"
                        dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M")
                        if dt > now:
                            valid.append(s)
                    except Exception:
                        valid.append(s)
                if valid:
                    return valid
        except Exception:
            pass
    return _fallback_suggestions()


def _fallback_suggestions() -> list:
    """Future-safe fallback suggestions."""
    now = datetime.now()
    today = now.date().isoformat()
    tomorrow = (now.date() + timedelta(days=1)).isoformat()
    next_week = (now.date() + timedelta(days=7)).isoformat()

    # "Soon" = next round hour, minimum 1 hour from now
    soon_dt = (now + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
    if soon_dt.date() == now.date() and soon_dt.hour < 22:
        soon = {"label": f"בעוד שעה ({soon_dt.strftime('%H:%M')})", "date": today, "time": soon_dt.strftime("%H:%M")}
    else:
        soon = {"label": "מחר בבוקר 09:00", "date": tomorrow, "time": "09:00"}

    # "Evening" = today 20:00, only if still future
    evening_dt = now.replace(hour=20, minute=0, second=0, microsecond=0)
    if evening_dt > now:
        medium = {"label": "הערב 20:00", "date": today, "time": "20:00"}
    else:
        medium = {"label": "מחר 09:00", "date": tomorrow, "time": "09:00"}

    later = {"label": "שבוע הבא 09:00", "date": next_week, "time": "09:00"}
    return [soon, medium, later]
