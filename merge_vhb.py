# -*- coding: utf-8 -*-
"""Führt die VHB-2024-Gesamtliste mit den bestehenden Journal-Stammdaten zusammen.

Schritt 1 (dieses Skript): Dedupe + Abgleich + Chunk-Dateien für die
Verlags-Recherche. Schritt 2 (apply_enrichment.py): Verlage/Homepages einspielen
und journals.json final schreiben.
"""
import html
import json
import re
import unicodedata
from pathlib import Path

ROOT = Path(__file__).parent
RANK = {"A+": 0, "A": 1, "B": 2, "B?": 3}

ALIASES = {
    # Gesamtliste -> Name in journals.json
    "journal of strategic information systems": "the journal of strategic information systems",
    "electronic markets em": "electronic markets",
}


def norm(name):
    n = html.unescape(name or "").lower().strip()
    n = n.split("/")[0]  # "MIS quarterly / MISRC" -> "MIS quarterly"
    n = unicodedata.normalize("NFKD", n)
    n = re.sub(r"\(.*?\)", " ", n)  # Klammerzusätze weg
    n = re.sub(r"[^a-z0-9 ]", " ", n)
    n = re.sub(r"\s+", " ", n).strip()
    return ALIASES.get(n, n)


def load(p):
    with open(ROOT / p, encoding="utf-8") as f:
        return json.load(f)


# 1) Gesamtliste einlesen, säubern, dedupen (Union der Fachbereiche, bestes Rating)
full = {}
for e in load("vhb_full_raw.json"):
    name = html.unescape(e["name"]).strip()
    if "eingestellt" in name.lower() or name.endswith(" DUP"):
        continue
    key = norm(name)
    if not key:
        continue
    areas = sorted(set(e.get("areas") or []))
    if key in full:
        f = full[key]
        f["areas"] = sorted(set(f["areas"]) | set(areas))
        if RANK.get(e["vhb_2024"], 9) < RANK.get(f["vhb_2024"], 9):
            f["vhb_2024"] = e["vhb_2024"]
        # kürzeren/saubereren Namen bevorzugen
        if len(name) < len(f["name"]):
            f["name"] = name
    else:
        full[key] = {"name": name, "vhb_2024": e["vhb_2024"], "areas": areas}

# 2) Bestehende Journals abgleichen: areas/rating aus Gesamtliste übernehmen
existing = load("journals.json")
matched_keys = set()
for j in existing:
    key = norm(j["name"])
    hit = full.get(key)
    if hit:
        j["areas"] = hit["areas"]
        j["vhb_2024"] = hit["vhb_2024"]
        matched_keys.add(key)
    else:
        j.setdefault("areas", ["WI"])

# 3) Neue Journals (noch ohne Verlag/Homepage)
new = []
for key, e in sorted(full.items()):
    if key in matched_keys:
        continue
    new.append({
        "name": e["name"], "abbrev": None, "vhb_2024": e["vhb_2024"],
        "basket11": False, "publisher": None, "homepage": None,
        "areas": e["areas"],
    })

merged = existing + new
with open(ROOT / "journals_merged.json", "w", encoding="utf-8") as f:
    json.dump(merged, f, ensure_ascii=False, indent=1)

# 4) Chunk-Dateien für die Verlags-Recherche
names = [j["name"] for j in new]
n_chunks = 4
for i in range(n_chunks):
    chunk = names[i::n_chunks]
    with open(ROOT / f"enrich_chunk_{i + 1}.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(chunk))

print(f"Gesamtliste (dedupliziert): {len(full)}")
print(f"Bestehende gematcht: {len(matched_keys)} von {len(existing)}")
print(f"Neue Journals: {len(new)}  -> {n_chunks} Chunk-Dateien")
print(f"Gesamt nach Merge: {len(merged)}")
unmatched = [j['name'] for j in existing if norm(j['name']) not in full]
print("Bestehende OHNE Treffer in Gesamtliste:", unmatched)
