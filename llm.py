"""
LLM interface — all Groq API calls live here.
"""
import json
import base64
import httpx
from datetime import date, datetime, timedelta
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

{{date_context}}
"""

SUGGEST_TIMES_SYSTEM = """You are a scheduling assistant for a Hebrew personal task manager.
The user added a task or reminder. Suggest exactly 3 natural times when they should be reminded.
Consider the task content to pick appropriate timing (urgent = sooner, long-term = later).

Return ONLY valid JSON — an array of exactly 3 objects:
[
  {{"label": "<short Hebrew label, max 3 words>", "date": "<YYYY-MM-DD>", "time": "<HH:MM>"}},
  {{"label": "<short Hebrew label, max 3 words>", "date": "<YYYY-MM-DD>", "time": "<HH:MM>"}},
  {{"label": "<short Hebrew label, max 3 words>", "date": "<YYYY-MM-DD>", "time": "<HH:MM>"}}
]

Spread suggestions: one soon, one medium, one later.
Good labels: "בעוד שעה", "הערב 20:00", "מחר בוקר", "סוף שבוע", "שבוע הבא".
Use the current date/time context: {date_context}
"""

CHAT_SYSTEM = """You are a friendly, concise Hebrew personal assistant bot named מזכיר.
Respond in Hebrew. Be brief and helpful. Use Israeli conversational tone.
Do not offer to save things — this is a pure chat response."""


async def classify(text: str) -> dict:
    date_ctx = enrich_prompt_with_date_context()
    system = CLASSIFY_SYSTEM.replace("{date_context}", date_ctx)
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


async def suggest_times(content: str) -> list:
    """Ask LLM for 3 smart date+time suggestions for a task/reminder."""
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
                "temperature": 0.3,
                "max_tokens": 250,
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
            if isinstance(suggestions, list) and len(suggestions) >= 3:
                return suggestions[:3]
        except json.JSONDecodeError:
            pass
    # Fallback
    return _fallback_suggestions()


def _fallback_suggestions() -> list:
    now = datetime.now()
    today = now.date().isoformat()
    tomorrow = (now.date() + timedelta(days=1)).isoformat()
    in_one_hour = (now + timedelta(hours=1)).strftime("%H:%M")
    return [
        {"label": f"בעוד שעה ({in_one_hour})", "date": today, "time": in_one_hour},
        {"label": "הערב 20:00", "date": today, "time": "20:00"},
        {"label": "מחר 09:00", "date": tomorrow, "time": "09:00"},
    ]


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
