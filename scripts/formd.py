#!/usr/bin/env python3
"""Match a company roster against the SEC's Form D data sets and pull funding rounds.

Standard library only. Three steps:

  python3 formd.py inspect  --email you@example.com
  python3 formd.py match    --email you@example.com --roster roster.csv
      -> formd_candidates.csv   (review it: put y in the 'approved' column)
  python3 formd.py rounds   --candidates formd_candidates.csv
      -> formd_rounds.csv       (one row per Form D filing of each approved issuer)

The SEC asks automated clients to identify themselves, hence --email.
Data: https://www.sec.gov/dera/data/form-d  (quarterly ZIPs of tab-separated tables)
"""
import argparse, csv, datetime as dt, difflib, io, os, re, sys, time, urllib.error, urllib.request, zipfile
from collections import defaultdict

BASE = "https://www.sec.gov/files/structureddata/data/form-d-data-sets/{q}_d.zip"
csv.field_size_limit(10**9)

SUFFIXES = {"inc", "incorporated", "llc", "corp", "corporation", "co", "company", "ltd", "limited",
            "lp", "pbc", "plc", "holdings", "the"}
# Names that are ordinary words or very short: matches need a human look.
AMBIGUOUS_MAX_LEN = 5


def norm(name):
    s = re.sub(r"[^a-z0-9 ]+", " ", (name or "").lower().replace("&", " and "))
    toks = [t for t in s.split() if t not in SUFFIXES]
    return " ".join(toks)


def quarters(start, end):
    y, q = int(start[:4]), int(start[-1])
    ey, eq = int(end[:4]), int(end[-1])
    while (y, q) <= (ey, eq):
        yield f"{y}q{q}"
        q += 1
        if q == 5:
            y, q = y + 1, 1


def default_end():
    t = dt.date.today()
    return f"{t.year}q{(t.month - 1) // 3 + 1}"


def fetch(q, cache, email, offline):
    path = os.path.join(cache, f"{q}_d.zip")
    if os.path.exists(path) or offline:
        return path if os.path.exists(path) else None
    req = urllib.request.Request(BASE.format(q=q), headers={"User-Agent": f"portfolio-research {email}"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r, open(path + ".part", "wb") as f:
            f.write(r.read())
        os.replace(path + ".part", path)
        time.sleep(0.3)  # stay far below the SEC's 10 requests/second limit
        return path
    except urllib.error.HTTPError as e:
        print(f"  {q}: HTTP {e.code}, skipped (not published yet, or the file name differs)", file=sys.stderr)
        return None


def table(zf, name):
    """Yield dict rows of one table, whatever folder it sits in inside the ZIP."""
    member = next((m for m in zf.namelist() if os.path.basename(m).lower() == name.lower() + ".tsv"), None)
    if member is None:
        return
    with zf.open(member) as f:
        text = io.TextIOWrapper(f, encoding="utf-8", errors="replace", newline="")
        for row in csv.DictReader(text, delimiter="\t", quoting=csv.QUOTE_NONE):
            yield row


def key(s):
    return re.sub(r"[^a-z0-9]", "", s.lower())


def get(row, *names):
    """Read a column by any of several spellings, ignoring case and underscores."""
    idx = row.get("__idx")
    if idx is None:
        idx = row["__idx"] = {key(k): k for k in row if k}
    for n in names:
        k = idx.get(key(n))
        if k is not None:
            return (row.get(k) or "").strip()
    return ""


def parse_date(s):
    s = (s or "").strip()
    for fmt in ("%Y-%m-%d", "%d-%b-%Y", "%m/%d/%Y", "%Y%m%d", "%d-%b-%y"):
        try:
            return dt.datetime.strptime(s[:11].strip(), fmt).date().isoformat()
        except ValueError:
            pass
    return s


def filing_url(cik, acc):
    return f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc.replace('-', '')}/" if cik.isdigit() else ""


def load(args, want_ciks=None):
    """Read every cached quarter. Returns filings keyed by accession number."""
    os.makedirs(args.cache, exist_ok=True)
    filings = {}
    for q in quarters(args.start, args.end):
        path = fetch(q, args.cache, args.email, args.offline)
        if not path:
            continue
        with zipfile.ZipFile(path) as zf:
            issuers = {}
            for r in table(zf, "ISSUERS"):
                if get(r, "IS_PRIMARYISSUER_FLAG", "ISPRIMARYISSUER") in ("NO", "N", "0", "false"):
                    continue
                cik = get(r, "CIK")
                if want_ciks is not None and cik.lstrip("0") not in want_ciks:
                    continue
                issuers[get(r, "ACCESSIONNUMBER")] = {
                    "cik": cik.lstrip("0"), "entity": get(r, "ENTITYNAME"), "city": get(r, "CITY"),
                    "state": get(r, "STATEORCOUNTRY"), "inc_state": get(r, "JURISDICTIONOFINC"),
                    "inc_year": get(r, "YEAROFINC_VALUE_ENTERED", "YEAROFINC_VALUE", "YEAROFINC")}
            subs = {get(r, "ACCESSIONNUMBER"): r for r in table(zf, "FORMDSUBMISSION") if get(r, "ACCESSIONNUMBER") in issuers}
            offs = {get(r, "ACCESSIONNUMBER"): r for r in table(zf, "OFFERING") if get(r, "ACCESSIONNUMBER") in issuers}
            people = defaultdict(list)
            if want_ciks is not None:
                for r in table(zf, "RELATEDPERSONS"):
                    a = get(r, "ACCESSIONNUMBER")
                    if a in issuers:
                        rel = " ".join(v for k, v in r.items() if k and k != "__idx" and key(k).startswith("relationship") and v)
                        people[a].append(f"{get(r, 'FIRSTNAME')} {get(r, 'LASTNAME')} ({rel.strip() or 'role not stated'})")
            for a, i in issuers.items():
                s, o = subs.get(a, {}), offs.get(a, {})
                kinds = [lab for lab, col in (("Equity", "ISEQUITYTYPE"), ("Debt", "ISDEBTTYPE"),
                                              ("Option/warrant/right", "ISOPTIONTOACQUIRETYPE"),
                                              ("Security to be acquired", "ISSECURITYTOBEACQUIREDTYPE"))
                         if o and get(o, col).lower() in ("true", "y", "yes", "1", "x")]
                filings[a] = dict(i, accession=a, quarter=q,
                                  form=get(s, "SUBMISSIONTYPE") if s else "",
                                  filing_date=parse_date(get(s, "FILING_DATE", "FILINGDATE")) if s else "",
                                  sale_date=parse_date(get(o, "SALE_DATE", "DATEOFFIRSTSALE")) if o else "",
                                  industry=get(o, "INDUSTRYGROUPTYPE") if o else "",
                                  amount_sold=get(o, "TOTALAMOUNTSOLD") if o else "",
                                  offering_amount=get(o, "TOTALOFFERINGAMOUNT") if o else "",
                                  investors=get(o, "TOTALNUMBERALREADYINVESTED") if o else "",
                                  securities="; ".join(kinds), related="; ".join(people.get(a, [])))
        print(f"  {q}: {len(filings):,} filings kept so far", file=sys.stderr)
    return filings


def score(company_n, issuer_n):
    if not company_n or not issuer_n:
        return 0
    if company_n == issuer_n:
        return 100
    ct, it = company_n.split(), issuer_n.split()
    if it[:len(ct)] == ct:  # 'finix' vs 'finix payments'
        return 90 if len(it) - len(ct) <= 2 else 80
    if "".join(ct) == "".join(it):  # 'juniper square' vs 'junipersquare'
        return 95
    return round(100 * difflib.SequenceMatcher(None, company_n, issuer_n).ratio()) if abs(len(company_n) - len(issuer_n)) <= 4 else 0


def cmd_inspect(args):
    q = args.end if not args.offline else next((f[:6] for f in sorted(os.listdir(args.cache)) if f.endswith("_d.zip")), args.end)
    os.makedirs(args.cache, exist_ok=True)
    path = fetch(q, args.cache, args.email, args.offline) or fetch(next(iter(quarters(args.start, args.start))), args.cache, args.email, args.offline)
    if not path:
        sys.exit("No data set could be downloaded. Check the list at https://www.sec.gov/dera/data/form-d")
    with zipfile.ZipFile(path) as zf:
        for m in zf.namelist():
            if m.lower().endswith(".tsv"):
                with zf.open(m) as f:
                    print(f"{m}\n  " + ", ".join(f.readline().decode("utf-8", "replace").strip().split("\t")) + "\n")


def cmd_match(args):
    roster = list(csv.DictReader(open(args.roster, newline="", encoding="utf-8")))
    filings = load(args)
    by_cik = defaultdict(list)
    for f in filings.values():
        by_cik[f["cik"]].append(f)
    index = defaultdict(set)  # first token -> ciks
    names = {}
    for cik, fs in by_cik.items():
        for n in {norm(f["entity"]) for f in fs}:
            if n:
                index[n.split()[0]].add(cik)
                index["".join(n.split())[:4]].add(cik)
                names.setdefault(cik, set()).add(n)
    out = []
    for row in roster:
        c = row["company"]
        cn = norm(c)
        pool = index.get(cn.split()[0], set()) | index.get("".join(cn.split())[:4], set()) if cn else set()
        cands = []
        for cik in pool:
            best = max(score(cn, n) for n in names[cik])
            if best >= args.min_score:
                fs = sorted(by_cik[cik], key=lambda f: f["filing_date"])
                pooled = any("pooled" in f["industry"].lower() for f in fs)
                cands.append((best - (15 if pooled else 0), cik, fs, pooled))
        cands.sort(key=lambda x: (-x[0], x[2][0]["filing_date"]))
        ambiguous = len(cn.replace(" ", "")) <= AMBIGUOUS_MAX_LEN
        if not cands:
            out.append({"company": c, "list": row.get("list", ""), "score": "", "approved": "", "note": "no candidate found"})
        for s, cik, fs, pooled in cands[:args.max_candidates]:
            f = fs[-1]
            out.append({"company": c, "list": row.get("list", ""), "score": s, "approved": "",
                        "entity": f["entity"], "cik": cik, "city": f["city"], "state": f["state"],
                        "inc_state": f["inc_state"], "inc_year": f["inc_year"], "industry": f["industry"],
                        "filings": len(fs), "first_filing": fs[0]["filing_date"], "last_filing": f["filing_date"],
                        "edgar": f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik}&type=D",
                        "note": "; ".join(x for x in ("short or common name: check carefully" if ambiguous else "",
                                                       "pooled investment fund: probably not the company" if pooled else "") if x)})
    cols = ["company", "list", "score", "approved", "entity", "cik", "city", "state", "inc_state", "inc_year",
            "industry", "filings", "first_filing", "last_filing", "edgar", "note"]
    with open(args.out, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        w.writerows(out)
    found = len({r["company"] for r in out if r.get("cik")})
    print(f"{found} of {len(roster)} companies have at least one candidate -> {args.out}\n"
          f"Review it and put y in 'approved' for each correct row, then run: formd.py rounds", file=sys.stderr)


def cmd_rounds(args):
    ok = [r for r in csv.DictReader(open(args.candidates, newline="", encoding="utf-8")) if r.get("approved", "").strip().lower() in ("y", "yes", "1", "true")]
    if not ok:
        sys.exit("No rows marked y in the 'approved' column.")
    company = {r["cik"]: r["company"] for r in ok}
    args.offline = True  # everything needed is already cached by 'match'
    filings = load(args, want_ciks=set(company))
    rows = sorted(filings.values(), key=lambda f: (company[f["cik"]].lower(), f["sale_date"] or f["filing_date"]))
    cols = ["company", "entity", "cik", "form", "is_new_notice", "filing_date", "sale_date", "amount_sold", "offering_amount",
            "investors", "securities", "related", "filing_url", "stage", "lead_investor", "stage_source", "checked_by"]
    with open(args.out, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for f in rows:
            w.writerow(dict(f, company=company[f["cik"]], is_new_notice="yes" if f["form"].strip().upper() == "D" else "no",
                            filing_url=filing_url(f["cik"], f["accession"]), stage="", lead_investor="", stage_source="", checked_by=""))
    print(f"{len(rows)} filings for {len(company)} approved issuers -> {args.out}", file=sys.stderr)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("command", choices=["inspect", "match", "rounds"])
    p.add_argument("--email", default="", help="contact address sent in the User-Agent, as the SEC requires")
    p.add_argument("--roster", default="roster.csv")
    p.add_argument("--candidates", default="formd_candidates.csv")
    p.add_argument("--out", default=None)
    p.add_argument("--cache", default="formd_cache")
    p.add_argument("--start", default="2015q1", help="first quarter, e.g. 2015q1 (Precursor was founded in 2015)")
    p.add_argument("--end", default=default_end())
    p.add_argument("--min-score", type=int, default=80)
    p.add_argument("--max-candidates", type=int, default=8)
    p.add_argument("--offline", action="store_true", help="use only ZIPs already in --cache")
    args = p.parse_args()
    if not args.offline and args.command != "rounds" and "@" not in args.email:
        sys.exit("Pass --email you@example.com (the SEC blocks clients that do not identify themselves).")
    args.out = args.out or {"match": "formd_candidates.csv", "rounds": "formd_rounds.csv"}.get(args.command)
    {"inspect": cmd_inspect, "match": cmd_match, "rounds": cmd_rounds}[args.command](args)


if __name__ == "__main__":
    main()
