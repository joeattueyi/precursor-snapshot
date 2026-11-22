#!/usr/bin/env python3
"""Find when each company first appeared on Precursor's site, using the Wayback Machine.

  python3 wayback_first_listed.py --roster roster.csv
      -> wayback_first_listed.csv

Standard library only. For each archived snapshot (one per month at most) it checks
which roster names occur in the page text. The first year a name appears is a proxy
for the investment year; it is an upper bound, since the site may lag the deal.

Limits: a snapshot whose company list was drawn by JavaScript contains no names, so
the script reports how many names each snapshot matched; ignore years with ~0.
"""
import argparse, csv, html, json, re, sys, time, urllib.parse, urllib.request

CDX = "https://web.archive.org/cdx/search/cdx"
PAGES = ["precursorvc.com/portfolio", "precursorvc.com/portfolio/", "precursorvc.com/companies",
         "precursorvc.com/companies/", "precursorvc.com/", "precursorvc.com/llms.txt"]
UA = {"User-Agent": "portfolio-research (personal, low volume)"}


def get(url, tries=4):
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=90) as r:
                return r.read().decode("utf-8", "replace")
        except Exception as e:  # the archive rate-limits and times out often: back off and retry
            if i == tries - 1:
                print(f"  failed: {url} ({e})", file=sys.stderr)
                return ""
            time.sleep(5 * (i + 1))


def snapshots(page, start):
    q = urllib.parse.urlencode({"url": page, "output": "json", "from": start, "filter": "statuscode:200",
                                "collapse": "timestamp:6", "fl": "timestamp,original"})
    body = get(f"{CDX}?{q}")
    rows = json.loads(body) if body.strip().startswith("[") else []
    return [(ts, orig) for ts, orig in rows[1:]]


def text_of(page_html):
    s = re.sub(r"(?is)<(script|style)\b.*?</\1>", " ", page_html)
    return html.unescape(re.sub(r"(?s)<[^>]+>", " ", s))


def matcher(name):
    """Short or ordinary-word names match case-sensitively to cut false hits."""
    flags = 0 if len(name) <= 5 else re.I
    return re.compile(r"(?<![A-Za-z0-9])" + re.escape(name) + r"(?![A-Za-z0-9])", flags)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--roster", default="roster.csv")
    p.add_argument("--out", default="wayback_first_listed.csv")
    p.add_argument("--start", default="2015")
    p.add_argument("--pause", type=float, default=2.0, help="seconds between requests")
    args = p.parse_args()

    roster = list(csv.DictReader(open(args.roster, newline="", encoding="utf-8")))
    pats = {r["company"]: matcher(r["company"]) for r in roster}
    seen = {c: [] for c in pats}  # company -> [(timestamp, url)]
    log = []
    snaps = sorted({s for page in PAGES for s in snapshots(page, args.start)})
    print(f"{len(snaps)} snapshots to read", file=sys.stderr)
    for ts, orig in snaps:
        body = get(f"https://web.archive.org/web/{ts}id_/{orig}")
        time.sleep(args.pause)
        txt = text_of(body)
        hits = [c for c, pat in pats.items() if pat.search(txt)]
        url = f"https://web.archive.org/web/{ts}/{orig}"
        for c in hits:
            seen[c].append((ts, url))
        log.append((ts, orig, len(hits)))
        print(f"  {ts[:4]}-{ts[4:6]} {orig}: {len(hits)} names", file=sys.stderr)

    with open(args.out, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["company", "list", "first_seen", "first_seen_url", "last_seen", "snapshots_with_name", "note"])
        for r in roster:
            s = sorted(seen[r["company"]])
            note = "short or common name: confirm by opening the snapshot" if len(r["company"]) <= 5 else ""
            if s:
                w.writerow([r["company"], r.get("list", ""), f"{s[0][0][:4]}-{s[0][0][4:6]}", s[0][1], f"{s[-1][0][:4]}-{s[-1][0][4:6]}", len(s), note])
            else:
                w.writerow([r["company"], r.get("list", ""), "", "", "", 0, "never found in a snapshot"])
    with open(args.out.replace(".csv", "_snapshots.csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["timestamp", "url", "names_matched"])
        w.writerows(log)
    print(f"-> {args.out}", file=sys.stderr)


if __name__ == "__main__":
    main()
