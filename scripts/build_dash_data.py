"""Builds the dashboard's data files from the project CSVs.
Run from data/: python3 ../scripts/build_dash_data.py ../docs/data formd_rounds_rule_v2_test.csv
formd_rounds_rule_v2_test.csv is formd_rounds.orig.csv labelled by rule v2 (label_rounds.py), used to score v2 on the checked rounds.
Inputs: formd_rounds.csv, formd_candidates.csv, wayback_first_listed.csv,
wayback_first_listed_snapshots.csv."""
import csv, json, os, re, sys
from collections import defaultdict

out, v2path = sys.argv[1], sys.argv[2]
os.makedirs(out, exist_ok=True)
CODE = open(__file__, encoding="utf-8").read()
rd = lambda p: list(csv.DictReader(open(p, newline="", encoding="utf-8")))


def save(name, rows, inputs):
    meta = [{"label": "build_dash_data.py", "value": CODE, "type": "code", "lang": "python"},
            {"label": "Input", "value": ", ".join(inputs)}]
    json.dump({"rows": rows, "meta": meta}, open(os.path.join(out, name), "w", encoding="utf-8"), ensure_ascii=False)
    print(name, len(rows))


def num(s):
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


def group(stage):
    s = stage.lower()
    if s.startswith("extension"):
        return "Extension or bridge"
    if s.startswith("pre-seed/seed"):
        return "Note or SAFE"
    for key, g in (("pre-seed", "Pre-seed"), ("seed", "Seed"), ("series a", "Series A"),
                   ("series b", "Series B"), ("series c", "Series C+")):
        if s.startswith(key):
            return g
    return "Other"


# 1. Rounds: one row per company and sale date
filings = rd("formd_rounds.csv")
by = defaultdict(list)
for f in filings:
    by[(f["company"], f["sale_date"] or f["filing_date"])].append(f)
rounds = []
for (co, date), fs in sorted(by.items()):
    notices = [f for f in fs if f["is_new_notice"] == "yes"] or fs
    f0 = notices[0]
    checked = next((f for f in fs if "checked against press" in f["checked_by"]), None)
    f = checked or f0
    rounds.append({
        "company": co, "round_id": f"{co} {date}", "sale_date": date, "year": int(date[:4]),
        "amount_usd_m": round(max(num(x["amount_sold"]) or 0 for x in notices) / 1e6, 2),
        "stage": f["stage"], "stage_group": group(f["stage"]),
        "lead_investor": f["lead_investor"] or None,
        "label_source": "Checked against press" if checked else "AI rule, unchecked",
        "filings": len(fs), "filing_url": f0["filing_url"]})
save("rounds.json", rounds, ["formd_rounds.csv"])

# 2. Label checks: the 14 press-checked rounds
v2 = {(r["company"], r["sale_date"]): r["stage"] for r in rd(v2path)}
checks = []
for (co, date), fs in sorted(by.items()):
    c = next((f for f in fs if "checked against press" in f["checked_by"]), None)
    if not c:
        continue
    cb = c["checked_by"]
    sv = re.search(r"stage (correct|wrong[^,]*)", cb).group(1)
    lv = re.search(r"lead ([^.]*)\.", cb).group(1)
    ai_stage = re.search(r"stage='([^']*)'", cb).group(1)
    ai_lead = re.search(r"lead='([^']*)'", cb).group(1)
    checks.append({"company": co, "round_id": f"{co} {date}", "sale_date": date,
                   "ai_stage": ai_stage, "true_stage": c["stage"], "stage_verdict": sv,
                   "stage_ok": sv == "correct", "ai_stage_v2": v2[(co, date)],
                   "stage_v2_ok": group(v2[(co, date)]) == group(c["stage"]),
                   "ai_lead": ai_lead or None, "true_lead": c["lead_investor"],
                   "lead_verdict": lv.split(" (")[0], "source_url": c["stage_source"]})
save("label_checks.json", checks, ["formd_rounds.csv", "v2test.csv (rule v2 run on formd_rounds.orig.csv)"])

# 3. Form D match decisions, one row per company
cands = rd("formd_candidates.csv")
dec = {}
for r in cands:
    c = r["company"]
    d = dec.setdefault(c, {"company": c, "list": r["list"], "candidates": 0, "decision": "No SEC candidate"})
    if r["cik"]:
        d["candidates"] += 1
    if r["approved"] == "y":
        d["decision"] = "Approved by AI"
    elif r["cik"] and r["approved"] == "" and d["decision"] != "Approved by AI":
        d["decision"] = "Needs a person"
    elif r["cik"] and r["approved"] == "n" and d["decision"] == "No SEC candidate":
        d["decision"] = "All candidates rejected"
save("formd_match.json", list(dec.values()), ["formd_candidates.csv"])

# 4. Vintages: first month each company is seen on an archived copy of the site
vin = []
for r in rd("wayback_first_listed.csv"):
    vin.append({"company": r["company"], "list": r["list"], "first_seen": r["first_seen"] or None,
                "first_year": int(r["first_seen"][:4]) if r["first_seen"] else None,
                "first_seen_url": r["first_seen_url"] or None})
save("vintages.json", vin, ["wayback_first_listed.csv"])

snaps = []
for r in rd("wayback_first_listed_snapshots.csv"):
    snaps.append({"timestamp": r["timestamp"], "month": f"{r['timestamp'][:4]}-{r['timestamp'][4:6]}",
                  "year": int(r["timestamp"][:4]), "url": r["url"], "names_matched": int(r["names_matched"])})
save("snapshots.json", snaps, ["wayback_first_listed_snapshots.csv"])
