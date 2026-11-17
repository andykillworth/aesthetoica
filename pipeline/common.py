"""Shared helpers for the æsthetoica pipeline."""
import json
import os
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "site"
# Day files live on the `data` branch in production (checked out into DATA_DIR by the workflows).
DATA_DIR = Path(os.environ.get("DATA_DIR", SITE / "data"))
DAYS = DATA_DIR / "days"
LONDON = ZoneInfo("Europe/London")
FIRST_SHEET = date(1823, 12, 3)  # Thomasin Gale's first sheet
LYME = (50.725, -2.937)
UA = "aesthetoica/1.0 (https://aesthetoica.com; art project)"

WIKI_RX = re.compile(r"moth|beetle|lichen|moss|fung|fern|lighthouse|shipwreck|chapel|abbey|barrow|tumulus|folklore|ghost|fossil|ammonite|comet|meteor|tide|cliff|hillfort|bog|marsh|owl|toad|newt|eel|snail|extinct|ruin|hamlet|mill|canal|bell|orrery|sundial|beacon", re.I)


def sheet_no(d: date) -> int:
    return (d - FIRST_SHEET).days + 1


def london_today() -> date:
    return datetime.now(LONDON).date()


def day_bounds(d: date):
    """UTC datetimes for London midnight to the next London midnight."""
    start = datetime(d.year, d.month, d.day, tzinfo=LONDON).astimezone(timezone.utc)
    nxt = d + timedelta(days=1)
    end = datetime(nxt.year, nxt.month, nxt.day, tzinfo=LONDON).astimezone(timezone.utc)
    return start, end


def ms(dt: datetime) -> int:
    return int(dt.timestamp() * 1000)


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def day_path(d: date) -> Path:
    return DAYS / f"{d.isoformat()}.json"


def load_day(d: date) -> dict:
    p = day_path(d)
    if p.exists():
        return json.loads(p.read_text())
    return {"date": d.isoformat(), "sheet": sheet_no(d)}


def save_day(d: date, day: dict) -> None:
    DAYS.mkdir(parents=True, exist_ok=True)
    day_path(d).write_text(json.dumps(day, ensure_ascii=False, separators=(",", ":")))


def merge_series(old, new):
    """Merge [[t, v], ...] series, newest value wins, sorted by time."""
    m = {int(t): v for t, v in (old or [])}
    m.update({int(t): v for t, v in (new or [])})
    return [[t, m[t]] for t in sorted(m)]


def merge_events(old, new, key="t"):
    seen = {(e[key], e.get("title") or e.get("id") or "") for e in (old or [])}
    out = list(old or [])
    for e in new or []:
        k = (e[key], e.get("title") or e.get("id") or "")
        if k not in seen:
            out.append(e)
            seen.add(k)
    return sorted(out, key=lambda e: e[key])
