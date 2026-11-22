"""AI first-pass labels for formd_rounds.csv: stage (rule-based) and lead investor (board-seat inference)."""
import csv, sys
from collections import defaultdict

path = sys.argv[1]
rows = list(csv.DictReader(open(path, newline="", encoding="utf-8")))

# Director -> firm, only where the affiliation is well known. A new board seat is
# evidence of the lead (or a major investor), not proof.
FIRM = {
    "Drew Oetting": "8VC", "David Yuan": "Tidemark", "Henri Pierre-Jacques": "Harlem Capital",
    "Scott Dorsey": "High Alpha", "Charles Hudson": "Precursor Ventures", "Rob Go": "NextView Ventures",
    "David Frankel": "Founder Collective", "Sean Ammirati": "Birchmere Labs", "Michael Dauber": "Amplify Partners",
    "Satya Patel": "Homebrew", "Nick Shalek": "Ribbit Capital", "Ann Miura-Ko": "Floodgate",
    "Maha Ibrahim": "Canaan Partners", "Ellen Chisa": "boldstart ventures", "Rick Yang": "NEA",
    "Jeffrey Crowe": "Norwest Venture Partners", "Sameer Gandhi": "Accel", "Deepen Parikh": "Bedrock",
    "Napoleon Ta": "Founders Fund", "Eric Stromberg": "Bedrock", "Jim Andelman": "Rincon Venture Partners",
    "Amias Gerety": "QED Investors", "Larry Marcus": "Walden Venture Capital", "Ashley Fontana": "Zetta Venture Partners",
    "Stuart Peterson": "Artis Ventures", "Stewart Peterson": "Artis Ventures", "Tianxiang Zhuo": "Accel",
}
ALIASES = {"ann muira-ko": "Ann Miura-Ko"}


def people(r):
    out = set()
    for p in r["related"].split("; "):
        name = p.split(" (")[0].strip()
        key = name.lower()
        name = ALIASES.get(key) or next((k for k in FIRM if k.lower() == key), name)
        if "Director" in p and "Executive Officer" not in p:
            out.add(name)
    return out


def num(s):
    try:
        return float(s)
    except ValueError:
        return 0.0


def stage_for(amount, secs):
    equity = "Equity" in secs
    if not equity and amount < 3e6:
        return "Pre-seed/Seed (note or SAFE)"
    if amount < 1.5e6:
        return "Pre-seed"
    if amount < 10e6:
        return "Seed"
    if amount < 20e6:
        return "Series A"
    if amount < 70e6:
        return "Series B"
    return "Series C+"


ORDER = ["Pre-seed/Seed (note or SAFE)", "Pre-seed", "Seed", "Series A", "Series B", "Series C+"]

by_co = defaultdict(list)
for r in rows:
    by_co[r["company"]].append(r)

for co, rs in by_co.items():
    # one round per sale date; size it by the largest amount any filing for that date reports
    rounds = defaultdict(list)
    for r in rs:
        rounds[r["sale_date"] or r["filing_date"]].append(r)
    seen_dirs, top, first = set(), -1, True
    for date in sorted(rounds):
        fs = rounds[date]
        new_notices = [f for f in fs if f["is_new_notice"] == "yes"] or fs
        amount = max(num(f["amount_sold"]) for f in new_notices)  # amendments accumulate later sales
        secs = "; ".join(f["securities"] for f in fs)
        st = stage_for(amount, secs)
        if ORDER.index(st) < top and "Equity" in secs:
            st = f"Extension or bridge (after {ORDER[top]})"
        else:
            top = max(top, ORDER.index(st))
        dirs = set().union(*(people(f) for f in fs))
        new = dirs - seen_dirs if not first else dirs
        firms = sorted({FIRM[d] for d in new if d in FIRM})
        lead = "; ".join(firms)
        lead_note = ""
        if firms:
            who = ", ".join(sorted(d for d in new if d in FIRM))
            lead_note = (f"lead inferred from board seat ({who}); "
                         + ("seat seen at company's first filing, may predate this round" if first else "new director this round"))
        for f in fs:
            if "checked against press" in f["checked_by"]:
                continue  # keep press-verified labels
            f["stage"] = st
            f["lead_investor"] = lead
            f["stage_source"] = ("rule v2 (seed <$10M, A <$20M, B <$70M, by first notice amount) + security type + order; Form D does not state stage"
                                 + (f". {lead_note}" if lead_note else ""))
            if f["is_new_notice"] == "no":
                f["stage_source"] += ". Amendment: same round as the notice with this sale date"
            f["checked_by"] = "AI first pass" + (" (stage + lead)" if lead else " (stage only)")
        seen_dirs |= dirs
        first = False

with open(path, "w", newline="", encoding="utf-8") as fh:
    w = csv.DictWriter(fh, fieldnames=rows[0].keys())
    w.writeheader()
    w.writerows(rows)
