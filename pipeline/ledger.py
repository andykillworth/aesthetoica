"""Write the keeper's ledger line for a finished day, in Thomasin Gale's manner.

    python pipeline/ledger.py --date 2026-11-16

Needs ANTHROPIC_API_KEY. ANTHROPIC_MODEL overrides the model.
The line is written from the day's facts only, never invented.
"""
import argparse
import json
import os
import statistics
import sys
from datetime import date, datetime

import requests

from common import LONDON, load_day, save_day, sheet_no

MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-5-5")

SYSTEM = """You keep the ledger of a marbling tray, writing as Thomasin Gale, a bookbinder in Lyme Regis in the 1820s and 1830s.
Each night you write one entry about the day's sheet. You do not know modern science: you only know what the colours in the tray did.
The colours mean: ochre speckle (fine, heavy or thin), green (the current that turns the tray; slow, steady or strong),
blue drops (unaccountable, one at a time), red lines (quick strokes across the tray), gold at the shore edge,
and being "combed" (a ring pushed outward when no one was there). The tray also rocks.

Rules:
- One or two short sentences, at most 22 words in total.
- Plain, practical, a working woman's notebook. Dry, not poetic. No metaphors about the soul, stars or mysteries.
- Never use dashes. No exclamation marks. No modern words.
- Only describe what the facts support. If something did not happen, you may note its absence plainly.

Examples of her entries:
Ochre fine, like rain through a roof.
Green turning the whole tray, strong.
Blue in drops, unaccountable.
Red lines all night, very quick, too many to count.
Combed. No one here.
"""


def facts(day):
    f = {}
    if day.get("neutron"):
        m = statistics.mean(v for _, v in day["neutron"])
        base = day.get("neutron_mean") or m
        f["ochre_vs_usual_percent"] = round((m / base - 1) * 100, 1)
    if day.get("kp"):
        f["green_strength_0_to_9"] = max(v for _, v in day["kp"])
    if day.get("hz"):
        hz = [v for _, v in day["hz"]]
        f["rocking"] = {"lowest_hz": min(hz), "highest_hz": max(hz)}
    mets = day.get("meteors") or []
    bright = [m for m in mets if m.get("mag") is not None and m["mag"] < -2]
    hours = sorted({datetime.fromtimestamp(m["t"] / 1000, LONDON).hour for m in bright})
    f["red_lines"] = {"count": len(bright), "hours": hours, "faint_specks": len(mets) - len(bright),
                      "showers": sorted({m.get("shower") for m in mets if m.get("shower") and m["shower"] != "Sporadic"})}
    f["blue_drops"] = len(day.get("wiki") or [])
    f["combed"] = len(day.get("gw") or [])
    return f


def write(d: date, force=False):
    day = load_day(d)
    if day.get("ledger") and not force:
        print("already written:", day["ledger"])
        return
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        sys.exit("ANTHROPIC_API_KEY is not set")
    msg = f"Sheet No. {sheet_no(d)}, {d.strftime('%-d %B %Y')}. Facts about the tray today:\n{json.dumps(facts(day), indent=1)}\n\nWrite tonight's entry."
    r = requests.post("https://api.anthropic.com/v1/messages", timeout=60,
                      headers={"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
                      json={"model": MODEL, "max_tokens": 120, "system": SYSTEM, "messages": [{"role": "user", "content": msg}]})
    r.raise_for_status()
    line = "".join(b.get("text", "") for b in r.json()["content"]).strip().strip('"')
    line = line.replace("—", ",").replace("–", ",")
    day["ledger"] = line
    save_day(d, day)
    print(line)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True)
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    write(date.fromisoformat(a.date), a.force)
