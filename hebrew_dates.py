"""Resolve Hebrew calendar phrases to ISO date strings."""
from datetime import datetime, date, timedelta
from zoneinfo import ZoneInfo
import re

_TZ = ZoneInfo("Asia/Jerusalem")
def _today(): return datetime.now(_TZ).date()

try:
    import hdate
    HDATE_AVAILABLE = True
except ImportError:
    HDATE_AVAILABLE = False

DOW_MAP = {"ראשון": 6, "שני": 0, "שלישי": 1, "רביעי": 2, "חמישי": 3, "שישי": 4, "שבת": 5,
           "sunday": 6, "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3, "friday": 4, "saturday": 5}

HOLIDAY_APPROX = {"ראש השנה": (9, 25), "יום כיפור": (10, 4), "סוכות": (10, 9),
                   "שמחת תורה": (10, 16), "חנוכה": (12, 25), "פורים": (3, 13), "פסח": (4, 12), "שבועות": (6, 1)}

def _next_weekday(target_dow):
    today = _today()
    days_ahead = (target_dow - today.weekday()) % 7
    return today + timedelta(days=days_ahead or 7)

def _next_friday(): return _next_weekday(4)
def _next_saturday(): return _next_weekday(5)
def _next_sunday(): return _next_weekday(6)

def resolve_relative_date(text):
    text_lower = text.lower()
    if "היום" in text_lower or "today" in text_lower: return _today().isoformat()
    if "מחר" in text_lower or "tomorrow" in text_lower: return (_today() + timedelta(days=1)).isoformat()
    if "מחרתיים" in text_lower: return (_today() + timedelta(days=2)).isoformat()
    if "אחרי שבת" in text_lower: return (_next_saturday() + timedelta(days=1)).isoformat()
    if "לפני שבת" in text_lower: return _next_friday().isoformat()
    if "בשבת" in text_lower or "שבת הקרובה" in text_lower: return _next_saturday().isoformat()
    if "סוף השבוע" in text_lower or "סוף שבוע" in text_lower: return _next_friday().isoformat()
    for heb, dow in DOW_MAP.items():
        if heb in text_lower: return _next_weekday(dow).isoformat()
    m = re.search(r"בעוד\s+(\d+)\s+ימים", text_lower)
    if m: return (_today() + timedelta(days=int(m.group(1)))).isoformat()
    if "בעוד שבוע" in text_lower: return (_today() + timedelta(weeks=1)).isoformat()
    if "בעוד חודש" in text_lower: return (_today() + timedelta(days=30)).isoformat()
    return _resolve_holiday_approx(text_lower)

def _resolve_holiday_approx(text):
    today = _today()
    for holiday, (month, day) in HOLIDAY_APPROX.items():
        if holiday in text:
            candidate = date(today.year, month, day)
            if candidate < today: candidate = date(today.year + 1, month, day)
            return candidate.isoformat()
    return None

def enrich_prompt_with_date_context():
    today = _today()
    weekday_names = ["שני", "שלישי", "רביעי", "חמישי", "שישי", "שבת", "ראשון"]
    weekday_heb = weekday_names[today.weekday()]
    return (
        f"Today is {today.isoformat()} (יום {weekday_heb}). "
        f"Next Friday is {_next_friday().isoformat()}. "
        f"Next Saturday (שבת) is {_next_saturday().isoformat()}. "
        f"Next Sunday (אחרי שבת) is {_next_sunday().isoformat()}."
    )
