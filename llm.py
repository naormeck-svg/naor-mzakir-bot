"""LLM interface — all Groq API calls."""
import json, base64, httpx
from config import GROQ_API_KEY, GROQ_MODEL, GROQ_VISION_MODEL, WHISPER_MODEL
from hebrew_dates import enrich_prompt_with_date_context

GROQ_BASE = "https://api.groq.com/openai/v1"
HEADERS = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}

CLASSIFY_SYSTEM = """You are a classifier for a Hebrew personal assistant Telegram bot.
Classify the user message and return ONLY valid JSON:
{{"type": "task"|"note"|"reminder"|"chat", "content": "<Hebrew text>", "date": "<YYYY-MM-DD or null>", "time": "<HH:MM or null>", "recurring": "daily"|"weekly:sun"|"weekly:mon"|"weekly:fri"|"monthly"|null}}
Rules:
- task: something to do. note: info to save. reminder: timed alert. chat: casual conversation.
- Handle Hebrew-English code-switching naturally.
- Resolve relative dates using context below.
{date_context}"""

CHAT_SYSTEM = "You are a friendly Hebrew personal assistant bot named מזכיר. Respond in Hebrew. Be brief and helpful."

async def classify(text):
    date_ctx = enrich_prompt_with_date_context()
    system = CLASSIFY_SYSTEM.format(date_context=date_ctx)
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(f"{GROQ_BASE}/chat/completions", headers=HEADERS,
            json={"model": GROQ_MODEL, "messages": [{"role": "system", "content": system}, {"role": "user", "content": text}], "temperature": 0.1, "max_tokens": 200})
        resp.raise_for_status()
        raw = resp.json()["choices"][0]["message"]["content"].strip()
        if "```" in raw:
            raw = raw.split("```")[1]
            if raw.startswith("json"): raw = raw[4:]
        try: return json.loads(raw)
        except: return {"type": "note", "content": text, "date": None, "time": None, "recurring": None}

async def chat(text, history=None):
    messages = [{"role": "system", "content": CHAT_SYSTEM}]
    if history: messages.extend(history[-6:])
    messages.append({"role": "user", "content": text})
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(f"{GROQ_BASE}/chat/completions", headers=HEADERS,
            json={"model": GROQ_MODEL, "messages": messages, "temperature": 0.7, "max_tokens": 300})
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip()

async def transcribe(audio_bytes, filename="audio.ogg"):
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(f"{GROQ_BASE}/audio/transcriptions",
            headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
            files={"file": (filename, audio_bytes, "audio/ogg")},
            data={"model": WHISPER_MODEL, "language": "he", "response_format": "text"})
        resp.raise_for_status()
        return resp.text.strip()

async def describe_image(image_bytes):
    b64 = base64.b64encode(image_bytes).decode()
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.post(f"{GROQ_BASE}/chat/completions", headers=HEADERS,
            json={"model": GROQ_VISION_MODEL, "messages": [{"role": "user", "content": [
                {"type": "text", "text": "תאר את התמונה הזאת בקצרה בעברית. אם יש טקסט — צטט אותו."},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}}]}], "max_tokens": 200})
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip()
