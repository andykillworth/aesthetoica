"""Build the static pages: one page per pulled sheet, the archive, sitemap and the tray's index.json.

    python pipeline/build.py

Reads day files from DATA_DIR/days, writes into site/.
"""
import html
import json
import statistics
from datetime import date, datetime

from common import DAYS, LONDON, SITE, sheet_no

BASE_URL = "https://aesthetoica.com"
FONTS = '<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin><link href="https://fonts.googleapis.com/css2?family=IM+Fell+Double+Pica&family=IM+Fell+English:ital@0;1&family=IM+Fell+English+SC&family=Mrs+Saint+Delafield&display=swap" rel="stylesheet">'
CSS = """*{box-sizing:border-box;margin:0;padding:0}body{background:#1f1b18;color:#d8cdb8;font-family:'IM Fell English',Georgia,serif;min-height:100vh}
a{color:inherit;text-underline-offset:3px}.top{display:flex;justify-content:space-between;align-items:flex-end;padding:22px 5vw 18px}
.wm{font-family:'IM Fell Double Pica',serif;font-size:44px;color:#efe4cf;text-decoration:none}.nav{font-size:16px;color:#bfb29b}.nav a{margin-left:16px}
.leaf{max-width:1100px;margin:0 auto 60px;padding:0 5vw}.sheet{position:relative;box-shadow:0 6px 14px rgba(0,0,0,.55)}.sheet img{display:block;width:100%;height:auto}
.plate{position:absolute;right:24px;bottom:22px;width:230px;padding:12px 16px 11px;background:#efe6d2;color:#3a2b1f;transform:rotate(-1.2deg);box-shadow:0 1px 2px rgba(60,40,20,.35)}
.plate .t{font-family:'IM Fell English SC',serif;font-size:15px}.plate .n{font-size:26px;line-height:1.05}.plate .d{font-style:italic;font-size:15px;color:#5a4330}
.note{background:#f1e9d6;color:#2f241b;margin-top:28px;padding:30px 40px 34px}.ledger{font-family:'Mrs Saint Delafield',cursive;font-size:34px;line-height:1.15;color:#2c3550}
.note h2{font-family:'IM Fell English SC',serif;font-weight:400;font-size:17px;color:#5a4634;margin:22px 0 8px}.note ul{list-style:none}.note li{font-size:17px;line-height:1.5}.note li b{font-weight:400;color:#6b2a1f}
.pn{display:flex;justify-content:space-between;margin-top:20px;font-size:16px;color:#bfb29b}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(250px,1fr));gap:28px 26px;padding:10px 5vw 60px}.card{text-decoration:none;color:inherit}
.card img{width:100%;aspect-ratio:3/2;object-fit:cover;display:block;box-shadow:0 4px 10px rgba(0,0,0,.5)}.card .no{margin-top:10px;font-size:18px;color:#efe4cf}.card .dd{font-style:italic;font-size:14.5px;color:#a99c86}
.card .ln{font-family:'Mrs Saint Delafield',cursive;font-size:24px;line-height:1.05;color:#c9d2ea;margin-top:4px}
h1.ar{font-family:'IM Fell Double Pica',serif;font-weight:400;font-size:40px;padding:0 5vw;color:#efe4cf}.sub{font-style:italic;color:#a99c86;padding:4px 5vw 18px}"""


def esc(s):
    return html.escape(str(s), quote=True)


def nice(d: date):
    return d.strftime("%-d %B %Y")


def events_list(day):
    li = []
    if day.get("neutron"):
        m = statistics.mean(v for _, v in day["neutron"])
        base = day.get("neutron_mean") or m
        pct = (m / base - 1) * 100
        li.append(f"<b>Ochre</b> cosmic-ray neutrons at Kiel, {pct:+.1f}% against the usual.")
    if day.get("kp"):
        li.append(f"<b>Verdigris</b> the magnetic field at Hartland reached about Kp {max(v for _, v in day['kp']):.0f}.")
    if day.get("wiki"):
        titles = ", ".join("‘" + esc(w["title"]) + "’" for w in day["wiki"][:3])
        li.append(f"<b>Indigo</b> {len(day['wiki'])} edits to obscure Wikipedia articles, among them {titles}.")
    mets = day.get("meteors") or []
    if mets:
        sh = sorted({m.get("shower") for m in mets if m.get("shower") and m["shower"] != "Sporadic"})
        bright = sum(1 for m in mets if m.get("mag") is not None and m["mag"] < -2)
        li.append(f"<b>Carmine</b> {len(mets)} meteors within 400 km of Lyme Regis, {bright} of them bright{(', ' + ', '.join(sh) + ' among them') if sh else ''}.")
    for g in day.get("gw") or []:
        t = datetime.fromtimestamp(g["t"] / 1000, LONDON).strftime("%H:%M")
        kind = {"BBH": "two black holes", "BNS": "two neutron stars", "NSBH": "a neutron star and a black hole"}.get(g.get("type"), "an unconfirmed source")
        li.append(f"<b>The comb</b> {esc(g['id'])} at {t}, probably {kind}.")
    if day.get("hz"):
        hz = [v for _, v in day["hz"]]
        li.append(f"<b>The rocking</b> the National Grid ran between {min(hz):.3f} and {max(hz):.3f} Hz.")
    return "\n".join(f"<li>{x}</li>" for x in li) or "<li>No records came in for this day; the sheet was made from the simulation.</li>"


def page(d, day, prev_d, next_d):
    n = sheet_no(d)
    title = f"Sheet No. {n:,} · {nice(d)} · æsthetoica"
    led = day.get("ledger") or ""
    desc = (led + " " if led else "") + f"The marbled sheet for {nice(d)}, made from cosmic rays, the magnetic field, meteors and other things that passed Lyme Regis unseen."
    img = f"/sheets/{n}/sheet.jpg"
    ld = {"@context": "https://schema.org", "@type": "VisualArtwork", "name": f"Sheet No. {n:,}", "dateCreated": d.isoformat(),
          "image": BASE_URL + img, "artMedium": "Simulated marbling driven by live data", "artform": "Generative print",
          "locationCreated": {"@type": "Place", "name": "Lyme Regis, Dorset"}, "isPartOf": {"@type": "Collection", "name": "æsthetoica sheets", "url": BASE_URL + "/sheets/"}}
    pn = (f'<a href="/sheets/{sheet_no(prev_d)}/">Sheet No. {sheet_no(prev_d):,}</a>' if prev_d else "<span></span>") + \
         (f'<a href="/sheets/{sheet_no(next_d)}/">Sheet No. {sheet_no(next_d):,}</a>' if next_d else "<span></span>")
    return f"""<!DOCTYPE html><html lang="en-GB"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(title)}</title><meta name="description" content="{esc(desc)}"><link rel="canonical" href="{BASE_URL}/sheets/{n}/">
<meta property="og:title" content="{esc(title)}"><meta property="og:description" content="{esc(desc)}"><meta property="og:image" content="{BASE_URL}/sheets/{n}/og.jpg"><meta name="twitter:card" content="summary_large_image">
{FONTS}<style>{CSS}</style><script type="application/ld+json">{json.dumps(ld, ensure_ascii=False)}</script></head><body>
<div class="top"><a class="wm" href="/">æsthetoica</a><div class="nav"><a href="/#day-{d.isoformat()}">Open this sheet in the tray</a><a href="/sheets/">All sheets</a><a href="/#on-the-word">On the word</a></div></div>
<div class="leaf"><div class="sheet"><img src="{img}" alt="Marbled sheet No. {n:,}, {nice(d)}" width="1800" height="1200">
<div class="plate"><div class="t">æsthetoica</div><div class="n">Sheet No. {n:,}</div><div class="d">{nice(d)}</div><div class="d">Lyme Regis</div><div class="d">Pulled at midnight</div></div></div>
<div class="note">{f'<div class="ledger">{esc(led)}</div>' if led else ''}<h2>What fell into the tray</h2><ul>{events_list(day)}</ul></div>
<div class="pn">{pn}</div></div></body></html>"""


def main():
    days = sorted(p.stem for p in DAYS.glob("*.json"))
    done = []
    for s in days:
        d = date.fromisoformat(s)
        day = json.loads((DAYS / f"{s}.json").read_text())
        if (SITE / "sheets" / str(sheet_no(d)) / "sheet.jpg").exists():
            done.append((d, day))
    sheets = []
    for i, (d, day) in enumerate(done):
        prev_d = done[i - 1][0] if i > 0 else None
        next_d = done[i + 1][0] if i + 1 < len(done) else None
        out = SITE / "sheets" / str(sheet_no(d))
        out.mkdir(parents=True, exist_ok=True)
        (out / "index.html").write_text(page(d, day, prev_d, next_d))
        sheets.append({"date": d.isoformat(), "sheet": sheet_no(d), "ledger": day.get("ledger", ""), "img": f"/sheets/{sheet_no(d)}/sheet.jpg", "url": f"/sheets/{sheet_no(d)}/"})
    sheets.reverse()
    (SITE / "data").mkdir(exist_ok=True)
    (SITE / "data" / "index.json").write_text(json.dumps({"sheets": sheets}, ensure_ascii=False))
    cards = "\n".join(f'<a class="card" href="{s["url"]}"><img src="{s["img"]}" alt="Sheet No. {s["sheet"]:,}" loading="lazy"><div class="no">Sheet No. {s["sheet"]:,}</div>'
                      f'<div class="dd">{nice(date.fromisoformat(s["date"]))}</div><div class="ln">{esc(s["ledger"])}</div></a>' for s in sheets)
    (SITE / "sheets").mkdir(exist_ok=True)
    (SITE / "sheets" / "index.html").write_text(f"""<!DOCTYPE html><html lang="en-GB"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Sheets · æsthetoica</title><meta name="description" content="Every marbled sheet pulled from the tray, one a day, numbered on from Thomasin Gale's first in 1823."><link rel="canonical" href="{BASE_URL}/sheets/">
{FONTS}<style>{CSS}</style></head><body><div class="top"><a class="wm" href="/">æsthetoica</a><div class="nav"><a href="/">Today’s tray</a><a href="/#on-the-word">On the word</a></div></div>
<h1 class="ar">Sheets</h1><div class="sub">Pulled at midnight, one a day. Numbered on from Thomasin Gale’s first, 3 December 1823.</div><div class="grid">{cards}</div></body></html>""")
    urls = [f"{BASE_URL}/", f"{BASE_URL}/sheets/"] + [BASE_URL + s["url"] for s in sheets]
    (SITE / "sitemap.xml").write_text('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' + "\n".join(f"<url><loc>{u}</loc></url>" for u in urls) + "\n</urlset>\n")
    (SITE / "robots.txt").write_text(f"User-agent: *\nAllow: /\nSitemap: {BASE_URL}/sitemap.xml\n")
    print(f"built {len(sheets)} sheet pages")


if __name__ == "__main__":
    main()
