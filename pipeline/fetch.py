"""Pull the day's invisible events into data/days/YYYY-MM-DD.json.

Run every 15 minutes for today:      python pipeline/fetch.py
Finalise a finished day (nightly):    python pipeline/fetch.py --date 2026-11-16 --final

Every source is optional: if one fails the others still write, and the
site falls back to simulation for anything missing.
"""
import argparse
import os
import csv
import io
import math
import re
import statistics
import sys
from datetime import date, datetime, timedelta, timezone

import requests

from common import (DAYS, LYME, UA, WIKI_RX, day_bounds, iso, load_day, london_today,
                    merge_events, merge_series, ms, save_day)

S = requests.Session()
S.headers["User-Agent"] = UA
T = 30


def warn(src, e):
    print(f"[{src}] skipped: {e}", file=sys.stderr)


# ---------------------------------------------------------------- magnetometer
# The UK observatories (Hartland, Eskdalemuir, Lerwick) reach INTERMAGNET about ten days late, so the live
# field comes from the nearest observatory that publishes within minutes. Over a few hundred kilometres the
# disturbances that matter here (storms, substorms, the daily swing) are much the same.
HAPI = "https://imag-data.bgs.ac.uk/GIN_V1/hapi"
MAG_STATIONS = [("clf", "Chambon-la-Forêt"), ("val", "Valentia"), ("dou", "Dourbes"), ("had", "Hartland")]


def magnetometer(start, end, prefer=None):
    """One-minute data from the nearest live INTERMAGNET observatory.
    Returns 10-minute H deviations (nT), a rough Kp-like activity estimate, and the station's name."""
    order = sorted(MAG_STATIONS, key=lambda s: 0 if s[1] == prefer else 1)
    cat = S.get(f"{HAPI}/catalog", timeout=T).json()["catalog"]
    js, why, name = None, [], None
    for code, nm in order:
        ids = [c["id"] for c in cat if c["id"].lower().startswith(code + "/best-avail/pt1m")]
        ids.sort(key=lambda i: 0 if "xyz" in i.lower() else 1)
        for ds in ids[:2]:
            try:
                inf = S.get(f"{HAPI}/info", params={"dataset": ds}, timeout=T).json()
                held = datetime.fromisoformat(inf["stopDate"].replace("Z", "+00:00"))
                stop = min(end, held)
                if stop <= start or end - held > timedelta(hours=3):
                    why.append(f"{ds}: holds data only to {inf['stopDate']}"); break
                r = S.get(f"{HAPI}/data", params={"dataset": ds, "start": iso(start), "stop": iso(stop), "format": "json", "include": "header"}, timeout=60)
                if r.ok and r.json().get("data"):
                    js, name = r.json(), nm
                    print(f"[magnetometer] {nm} ({ds}), data to {inf['stopDate']}")
                    break
                why.append(f"{ds}: {r.status_code}")
            except Exception as e:
                why.append(f"{ds}: {e}")
        if js:
            break
    if js is None:
        raise RuntimeError("; ".join(why) or "no observatory answered")
    names = [p["name"].lower() for p in js.get("parameters", [])]
    rows = js["data"]
    hs = []
    for row in rows:
        t = datetime.fromisoformat(row[0].replace("Z", "+00:00"))
        vals = row[1:]
        flat = []
        for v in vals:
            flat.extend(v if isinstance(v, list) else [v])
        flat = [x for x in flat if isinstance(x, (int, float)) and abs(x) < 99990]
        if not flat:
            continue
        if "/xyz" in ds.lower() and len(flat) >= 2:
            h = math.hypot(flat[0], flat[1])
        else:
            h = flat[0]
        hs.append((t, h))
    if not hs:
        raise RuntimeError("no rows")
    base = statistics.median(h for _, h in hs)
    out, kp = [], []
    bucket = {}
    for t, h in hs:
        k = t.replace(minute=t.minute - t.minute % 10, second=0, microsecond=0)
        bucket.setdefault(k, []).append(h)
    for k in sorted(bucket):
        out.append([ms(k), round(statistics.mean(bucket[k]) - base, 1)])
    # activity: H range over each 3-hour window, mapped loosely onto a Kp-like 0..9 scale
    three = {}
    for t, h in hs:
        k = t.replace(hour=t.hour - t.hour % 3, minute=0, second=0, microsecond=0)
        three.setdefault(k, []).append(h)
    for k in sorted(three):
        rng = max(three[k]) - min(three[k])
        est = min(9, max(0, round(math.log(max(rng, 1) / 5, 1.6), 1)))
        kp.append([ms(k), est])
    return out, kp, name


# ---------------------------------------------------------------- NMDB (Kiel)
NEST = "https://www.nmdb.eu/nest/draw_graph.php"


def nmdb(start, end, station="KIEL2"):
    """Hourly corrected counts from NMDB's NEST interface (ASCII output)."""
    p = {"formchk": 1, "stations[]": station, "tabchoice": "revori", "dtype": "corr_for_efficiency",
         "tresolution": 60, "yunits": 0, "date_choice": "bydate", "output": "ascii",
         "start_day": start.day, "start_month": start.month, "start_year": start.year, "start_hour": start.hour, "start_min": 0,
         "end_day": end.day, "end_month": end.month, "end_year": end.year, "end_hour": end.hour, "end_min": 59}
    txt = S.get(NEST, params=p, timeout=60).text
    out = []
    for m in re.finditer(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s*;\s*([\d.]+)", txt):
        t = datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        out.append([ms(t), float(m.group(2))])
    if not out:
        raise RuntimeError("no rows parsed (check NEST parameters)")
    return out


def neutron_baseline(today):
    """Mean of the previous 27 days' neutron means (one solar rotation)."""
    vals = []
    for i in range(1, 28):
        p = DAYS / f"{(today - timedelta(days=i)).isoformat()}.json"
        if p.exists():
            import json
            d = json.loads(p.read_text())
            if d.get("neutron"):
                vals.append(statistics.mean(v for _, v in d["neutron"]))
    return statistics.mean(vals) if vals else None


# ---------------------------------------------------------------- Elexon
def elexon(start, end):
    r = S.get("https://data.elexon.co.uk/bmrs/api/v1/system/frequency",
              params={"from": iso(start), "to": iso(end), "format": "json"}, timeout=60)
    r.raise_for_status()
    rows = r.json().get("data", [])
    bucket = {}
    for row in rows:
        t = datetime.fromisoformat(row["measurementTime"].replace("Z", "+00:00"))
        k = t.replace(second=0, microsecond=0)
        bucket.setdefault(k, []).append(float(row["frequency"]))
    return [[ms(k), round(statistics.mean(v), 3)] for k, v in sorted(bucket.items())]


# ---------------------------------------------------------------- GraceDB
GPS_EPOCH = datetime(1980, 1, 6, tzinfo=timezone.utc)
LEAP = 18


def gracedb(start, end):
    q = f"is_public: True created: {start.strftime('%Y-%m-%d %H:%M:%S')} .. {end.strftime('%Y-%m-%d %H:%M:%S')}"
    r = S.get("https://gracedb.ligo.org/api/superevents/", params={"query": q, "format": "json"}, timeout=60)
    r.raise_for_status()
    out = []
    for e in r.json().get("superevents", []):
        if "RETRACTED" in (e.get("labels") or []):
            continue
        t = GPS_EPOCH + timedelta(seconds=float(e["t_0"]) - LEAP)
        ev = {"t": ms(t), "id": e["superevent_id"], "far": e.get("far")}
        try:
            pa = S.get(f"https://gracedb.ligo.org/api/superevents/{e['superevent_id']}/files/p_astro.json", timeout=T)
            if pa.ok:
                probs = pa.json()
                ev["type"] = max(probs, key=probs.get)
        except Exception:
            pass
        out.append(ev)
    return out


# ---------------------------------------------------------------- Wikipedia
def wikipedia(since, until, max_pages=30):
    out, cont = [], {}
    for _ in range(max_pages):
        p = {"action": "query", "list": "recentchanges", "rcnamespace": 0, "rctype": "edit", "rcshow": "!bot",
             "rcprop": "title|timestamp|sizes", "rclimit": 500, "rcstart": iso(until), "rcend": iso(since),
             "format": "json", **cont}
        js = S.get("https://en.wikipedia.org/w/api.php", params=p, timeout=T).json()
        for rc in js.get("query", {}).get("recentchanges", []):
            if WIKI_RX.search(rc["title"]):
                t = datetime.fromisoformat(rc["timestamp"].replace("Z", "+00:00"))
                out.append({"t": ms(t), "title": rc["title"], "bytes": rc.get("newlen", 0) - rc.get("oldlen", 0)})
        if "continue" not in js:
            break
        cont = js["continue"]
    return out


# ---------------------------------------------------------------- Global Meteor Network
GMN_DAILY = "https://globalmeteornetwork.org/data/traj_summary_data/daily/"


def haversine(a, b):
    la1, lo1, la2, lo2 = map(math.radians, (*a, *b))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(h))


def gmn(d, start, end, radius_km=400):
    """Meteors from GMN daily trajectory summaries that ended within radius_km of Lyme Regis.
    GMN files run noon to noon (UTC) and are named for the afternoon they start, so a London day needs the
    files for the day before and the day itself. They appear about 30 hours after the night ends.
    Returns (meteors, complete): complete is False until both files are published."""
    idx = S.get(GMN_DAILY, timeout=T).text
    names = set(re.findall(r'href="(traj_summary_\d{8}_[^"]+\.txt)"', idx))
    days = [(d - timedelta(days=1)).strftime("%Y%m%d"), d.strftime("%Y%m%d")]
    want = [n for n in names if n[13:21] in days]
    complete = all(any(n[13:21] == k for n in want) for k in days)
    out = []
    for n in want:
        txt = S.get(GMN_DAILY + n, timeout=120).text
        lines = txt.splitlines()
        # the column names are split over two header lines: names, then units
        hl = [l for l in lines[:12] if l.startswith("#") and ";" in l]
        rows = [l for l in lines if l and not l.startswith("#")]
        if len(hl) < 2 or not rows:
            continue
        a, b = ([c.strip() for c in l.lstrip("#").split(";")] for l in hl[:2])
        cols = [f"{x} {y}".strip().lower() for x, y in zip(a, b)]

        def col(*keys):
            for i, c in enumerate(cols):
                if all(k in c for k in keys):
                    return i
            return None
        iT, iLat, iLon, iH1, iH2, iMag, iSh, iV = (col("beginning", "utc"), col("latend"), col("lonend"), col("htbeg"),
                                                   col("htend"), col("peak", "absmag") or col("peak", "mag"), col("iau", "code"), col("vgeo"))
        for l in rows:
            f = [x.strip() for x in l.split(";")]
            try:
                t = datetime.strptime(f[iT][:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
                if not (start <= t < end):
                    continue
                lat, lon = float(f[iLat]), float(f[iLon])
                if haversine(LYME, (lat, lon)) > radius_km:
                    continue
                sh = f[iSh] if iSh is not None else ""
                out.append({"t": ms(t), "lat": lat, "lon": lon, "h1": float(f[iH1]), "h2": float(f[iH2]),
                            "mag": float(f[iMag]) if iMag is not None else None,
                            "v": float(f[iV]) if iV is not None else None,
                            "shower": SHOWER_NAMES.get(sh, "Sporadic" if sh in ("", "...", "-1") else "Minor shower"), "code": sh})
            except (ValueError, IndexError, TypeError):
                continue
    return out, complete


SHOWER_NAMES = {"QUA": "Quadrantid", "LYR": "Lyrid", "ETA": "Eta Aquariid", "PER": "Perseid", "DRA": "Draconid",
                "ORI": "Orionid", "LEO": "Leonid", "GEM": "Geminid", "URS": "Ursid", "STA": "Southern Taurid", "NTA": "Northern Taurid"}


# ---------------------------------------------------------------- main
def backfill(n):
    """Meteors arrive ~30 hours late: fill them in for recent sheets, so those sheets can be pulled again."""
    changed = []
    for k in range(1, n + 1):
        d = london_today() - timedelta(days=k)
        day = load_day(d)
        if not day.get("final") or day.get("meteors_final"):
            continue
        start, end = day_bounds(d)
        try:
            mets, complete = gmn(d, start, end)
        except Exception as e:
            warn("gmn", e); continue
        if not complete:
            print(f"[gmn] {d}: still waiting for GMN"); continue
        day["meteors"], day["meteors_final"] = merge_events([], mets), True
        save_day(d, day)
        changed.append(d.isoformat())
        print(f"[gmn] {d}: {len(mets)} meteors added")
    if os.environ.get("RERENDER_FILE"):
        with open(os.environ["RERENDER_FILE"], "w") as f:
            f.write(" ".join(changed))



def run(d: date, final: bool):
    start, end = day_bounds(d)
    now = datetime.now(timezone.utc)
    upto = min(end, now)
    day = load_day(d)
    jobs = [
        ("magnetometer", lambda: magnetometer(start, upto, day.get("mag_station"))),
        ("nmdb", lambda: nmdb(start, upto)),
        ("elexon", lambda: elexon(start, upto)),
        ("gracedb", lambda: gracedb(start, upto)),
        ("wikipedia", lambda: wikipedia(max(start, upto - timedelta(hours=1)), upto)),
    ]
    if final:
        jobs.append(("gmn", lambda: gmn(d, start, end)))
    for name, job in jobs:
        try:
            res = job()
            if name == "magnetometer":
                if day.get("mag_station") and day["mag_station"] != res[2]:
                    day["magH"], day["kp"] = [], []  # don't stitch two observatories into one trace
                day["magH"], day["kp"] = merge_series(day.get("magH"), res[0]), merge_series(day.get("kp"), res[1])
                day["mag_station"] = res[2]
            elif name == "nmdb":
                day["neutron"] = merge_series(day.get("neutron"), res)
                base = neutron_baseline(d)
                if base:
                    day["neutron_mean"] = round(base, 3)
            elif name == "elexon":
                day["hz"] = merge_series(day.get("hz"), res)
            elif name == "gracedb":
                day["gw"] = merge_events(day.get("gw"), res)
            elif name == "wikipedia":
                day["wiki"] = merge_events(day.get("wiki"), res)
            elif name == "gmn":
                day["meteors"], day["meteors_final"] = merge_events([], res[0]), res[1]
                if not res[1]:
                    print("[gmn] the night's meteors aren't published yet; they'll be added in a later pull")
            print(f"[{name}] ok")
        except Exception as e:  # keep going: missing sources fall back to simulation on the site
            warn(name, e)
    day["updated"] = ms(now)
    if final:
        day["final"] = True
    save_day(d, day)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", help="YYYY-MM-DD (London). Default: today")
    ap.add_argument("--final", action="store_true", help="finished day: also pull meteors from the Global Meteor Network")
    ap.add_argument("--backfill", type=int, metavar="N", help="add meteors to the last N finished days that are still waiting for them; list the days changed in $RERENDER_FILE")
    a = ap.parse_args()
    if a.backfill:
        backfill(a.backfill)
    else:
        run(date.fromisoformat(a.date) if a.date else london_today(), a.final)
