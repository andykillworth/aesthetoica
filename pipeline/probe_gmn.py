import re, sys
sys.path.insert(0, "pipeline")
import fetch
idx = fetch.S.get(fetch.GMN_DAILY, timeout=60).text
n = [x for x in set(re.findall(r'href="([^"]+)"', idx)) if "20261117" in x][0]
L = fetch.S.get(fetch.GMN_DAILY + n, timeout=120).text.splitlines()
h = [l for l in L[:8] if l.startswith("#") and ";" in l]
a = [c.strip() for c in h[0].lstrip("#").split(";")]; b = [c.strip() for c in h[1].lstrip("#").split(";")]
for i, (x, y) in enumerate(zip(a, b)): print("COL", i, repr(x), repr(y))
