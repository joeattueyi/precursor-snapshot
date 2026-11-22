"""Builds the dashboard's second set of data files.
Run from data/: python3 ../scripts/build_dash_data2.py ../docs/data current_web.tsv
Inputs: formd_cache/*.zip (SEC Form D data sets), roster.csv, formd_rounds.csv, alumni_status.csv,
current_web.tsv (website check of current companies, 22 Nov 2026).
Outputs: funds.json, current_signals.json, alumni_status.json (adds buyer_type)."""
import csv, glob, io, json, os, sys, zipfile
from collections import defaultdict

out, web_path = sys.argv[1], sys.argv[2]
os.makedirs(out, exist_ok=True)
CODE = open(__file__, encoding="utf-8").read()
rd = lambda p: list(csv.DictReader(open(p, newline="", encoding="utf-8")))


def save(name, rows, inputs, extra=None):
    meta = [{"label": "build_dash_data2.py", "value": CODE, "type": "code", "lang": "python"},
            {"label": "Input", "value": ", ".join(inputs)}] + (extra or [])
    json.dump({"rows": rows, "meta": meta}, open(os.path.join(out, name), "w", encoding="utf-8"), ensure_ascii=False)
    print(name, len(rows))


def num(s):
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


# 1. Precursor's own fund vehicles in the SEC Form D data sets
filings = []
for p in sorted(glob.glob("formd_cache/*_d.zip")):
    z = zipfile.ZipFile(p)
    names = {n.split("/")[-1].upper(): n for n in z.namelist()}
    t = lambda key: csv.DictReader(io.TextIOWrapper(z.open(names[key]), encoding="utf-8", errors="replace"), delimiter="\t")
    if "ISSUERS.TSV" not in names:
        continue
    iss = {r["ACCESSIONNUMBER"]: r for r in t("ISSUERS.TSV") if "PRECURSOR VENTURES" in (r.get("ENTITYNAME") or "").upper()}
    if not iss:
        continue
    sub = {r["ACCESSIONNUMBER"]: r for r in t("FORMDSUBMISSION.TSV") if r["ACCESSIONNUMBER"] in iss}
    for r in t("OFFERING.TSV"):
        a = r["ACCESSIONNUMBER"]
        if a in iss:
            filings.append({"entity": iss[a]["ENTITYNAME"].strip(), "cik": iss[a]["CIK"].lstrip("0"),
                            "filed": sub.get(a, {}).get("FILING_DATE", ""), "first_sale": r.get("SALE_DATE") or "",
                            "offered": num(r.get("TOTALOFFERINGAMOUNT")), "sold": num(r.get("TOTALAMOUNTSOLD")),
                            "investors": num(r.get("TOTALNUMBERALREADYINVESTED")), "quarter": os.path.basename(p)[:6]})
by = defaultdict(list)
for f in filings:
    by[f["cik"]].append(f)
funds = []
for cik, fs in by.items():
    e = fs[-1]["entity"]
    kind = ("Follow-on vehicle (Outgrowth series)" if "Outgrowth" in e else "Opportunity fund" if "Opportunity" in e
            else "Parallel fund" if "IV-A" in e else "Main fund")
    sold = max((f["sold"] or 0) for f in fs)
    offered = max((f["offered"] or 0) for f in fs if f["offered"] is not None) if any(f["offered"] for f in fs) else None
    first = min((f["first_sale"] for f in fs if f["first_sale"]), default="") or min(f["quarter"] for f in fs)
    note = ""
    counted = sold
    if kind == "Parallel fund":
        note = "Reports the same total as Fund IV, so it looks like a combined figure; counted once, under Fund IV."
        counted = None
    if e.startswith("Precursor Ventures V"):
        note = "Latest filing Aug 2024; the raise may have continued after the last data set."
    funds.append({"vehicle": e, "cik": cik, "kind": kind, "first_sale": first[:10], "year": int(first[:4]),
                  "sold_usd_m": round(sold / 1e6, 2), "counted_usd_m": round(counted / 1e6, 2) if counted is not None else None,
                  "target_usd_m": round(offered / 1e6, 2) if offered else None,
                  "investors": int(max((f["investors"] or 0) for f in fs)), "filings": len(fs),
                  "edgar": f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik}&type=D", "note": note or None})
# Later closes reported in press, newer than the last Form D. The SEC figure is kept in sold_usd_m.
PRESS = {"Precursor Ventures V": {"amount_usd_m": 66.0, "date": "2025-04", "source": "https://vcwire.tech/2025/04/14/precursor-ventures-closes-fifth-fund-at-66m/",
                                  "note": "Final close reported April 2025; last Form D (Aug 2024) showed $62.58M of a $120M target."}}
for f in funds:
    f["amount_usd_m"], f["amount_source"], f["amount_date"], f["amount_url"] = f["sold_usd_m"], "SEC Form D", None, f["edgar"]
    for key, pr in PRESS.items():
        if f["vehicle"].startswith(key + ",") or f["vehicle"].startswith(key + " "):
            f["amount_usd_m"], f["amount_source"], f["amount_date"], f["amount_url"] = pr["amount_usd_m"], "Press", pr["date"], pr["source"]
            f["counted_usd_m"] = pr["amount_usd_m"]
            f["note"] = pr["note"]
funds.sort(key=lambda r: (r["first_sale"], r["vehicle"]))
save("funds.json", funds, ["formd_cache (SEC Form D data sets 2015q1 to 2026q1)", "Press: VCWire, 14 Apr 2025 (Fund V close)"])

# 2. Signals for current companies: website state and time since last filed round
web = {}
for line in open(web_path, encoding="utf-8"):
    c, u, code, final, title, state = (line.rstrip("\n").split("\t") + [""] * 6)[:6]
    web[c] = {"url": u, "state": state, "final": final}
last = {}
for r in rd("formd_rounds.csv"):
    d = r["sale_date"] or r["filing_date"][:10]
    if r["is_new_notice"] == "yes":
        last[r["company"]] = max(last.get(r["company"], ""), d)
AS_OF = "2026-11-22"
sig = []
for r in rd("roster.csv"):
    if r["list"] == "Alumni only":
        continue
    c = r["company"]
    w = web.get(c, {"state": "Not checked", "url": "", "final": ""})
    flags = []
    if w["state"] in ("Unreachable", "Parked or for sale", "Page missing"):
        flags.append(f"Website {w['state'].lower()}")
    lr = last.get(c)
    # A gap in filings is not used as a flag: Juniper Square's last matched filing is 2019,
    # yet press reports a 2025 Series D, so later rounds can be unfiled or filed under another entity.
    sig.append({"company": c, "list": r["list"], "sector": r["sector"], "website_state": w["state"],
                "website": w["url"] or None, "last_filed_round": lr, "flags": "; ".join(flags) or None, "flag_count": len(flags)})
save("current_signals.json", sig, ["roster.csv", "formd_rounds.csv", "current_web.tsv"],
     [{"label": "As of", "value": AS_OF}])

# 3. Alumni outcomes with buyer type (from the press sources already in alumni_status.csv)
BUYER = {"Bash": "Acqui-hire", "Pulse": "Acqui-hire", "Kinside": "Merger", "OpenSauced": "Non-profit"}
# Chorus Sleep, Clutch, illume, Lilo and Vinebase were confirmed by press on 22 Nov 2026 (operating-company buyers).
al = []
for r in rd("alumni_status.csv"):
    st = r["status"]
    grp = ("Acquired" if st == "Acquired" else "Operating" if st.startswith("Operating") or st == "Likely operating"
           else "Shut down" if st == "Likely shut down" else "Unclear")
    al.append({"company": r["company"], "sector": r["sector"] or None, "status": st, "outcome": grp,
               "acquirer": r["acquirer"] or None, "buyer_type": (BUYER.get(r["company"], "Strategic buyer") if grp == "Acquired" else None),
               "year": int(r["year"]) if r["year"].strip() else None, "confidence": r["confidence"],
               "evidence": r["note"] or None, "source_url": r["source"] or None})
save("alumni_status.json", al, ["alumni_status.csv"])
