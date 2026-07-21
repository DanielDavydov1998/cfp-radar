# -*- coding: utf-8 -*-
"""Spielt die Verlags-/Homepage-Recherche (enrich_*.json) in journals_merged.json
ein und schreibt das finale journals.json."""
import html
import json
import re
import unicodedata
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).parent


def norm(name):
    n = html.unescape(name or "").lower().strip()
    n = n.split("/")[0]
    n = unicodedata.normalize("NFKD", n)
    n = re.sub(r"\(.*?\)", " ", n)
    n = re.sub(r"[^a-z0-9 ]", " ", n)
    return re.sub(r"\s+", " ", n).strip()


with open(ROOT / "journals_merged.json", encoding="utf-8") as f:
    journals = json.load(f)

enrich = {}
for i in range(1, 5):
    p = ROOT / f"enrich_{i}.json"
    if not p.exists():
        print(f"WARNUNG: {p.name} fehlt")
        continue
    for e in json.loads(p.read_text(encoding="utf-8")):
        enrich[norm(e["name"])] = e

filled = missing = 0
for j in journals:
    if j.get("publisher"):
        continue  # Bestandsjournal, bereits gepflegt
    e = enrich.get(norm(j["name"]))
    if e:
        pub = (e.get("publisher") or "").strip() or None
        home = (e.get("homepage") or "").strip() or None
        if home and not home.startswith("http"):
            home = None
        j["publisher"] = pub
        j["homepage"] = home
        filled += 1
    else:
        missing += 1

with open(ROOT / "journals.json", "w", encoding="utf-8") as f:
    json.dump(journals, f, ensure_ascii=False, indent=1)

print(f"Journals gesamt: {len(journals)} | angereichert: {filled} | ohne Treffer: {missing}")
print("Verlagsverteilung:", dict(Counter((j.get('publisher') or '?') for j in journals).most_common(20)))
