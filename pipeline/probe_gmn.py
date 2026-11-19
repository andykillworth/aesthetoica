import re, sys
sys.path.insert(0, "pipeline")
import fetch
from datetime import date
idx = fetch.S.get(fetch.GMN_DAILY, timeout=60).text
print("index url", fetch.GMN_DAILY, "len", len(idx))
names = sorted(set(re.findall(r'href="([^"]+)"', idx)))
print("entries", len(names)); print("last 15:", names[-15:])
for n in [x for x in names if "20261118" in x or "20261119" in x or "20261117" in x][:4]:
    txt = fetch.S.get(fetch.GMN_DAILY + n, timeout=120).text.splitlines()
    print("FILE", n, "lines", len(txt))
    for l in txt[:6]: print("  ", l[:400])
    rows = [l for l in txt if l and not l.startswith("#")]
    print("  rows", len(rows)); print("  first row:", rows[0][:400] if rows else None)
