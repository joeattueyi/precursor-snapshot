# Precursor Ventures: fund diligence snapshot

How much can public data tell you about a venture fund? This builds a diligence snapshot of Precursor Ventures from public records only.

**Live dashboard:** [joeattueyi.github.io/precursor-snapshot](https://joeattueyi.github.io/precursor-snapshot/)

Independent analysis; not affiliated with Precursor Ventures. Data as of November 2026.

## What it shows

- **Fund:** $215M raised across Funds I to V, Fund V's $66M close (April 2025), investors per fund, and 14 "Outgrowth" follow-on vehicles.
- **Portfolio:** 297 named companies, new companies a year, how often first rounds fit the stated thesis, and sector mix.
- **Performance signals:** progression to Series A and beyond, later rounds, $1B+ valuations, 26 acquisitions (22 to operating companies), likely inactive companies, and websites offline.
- **Limitations appendix:** a 12-question coverage scorecard, what still needs a data room (DPI, TVPI, IRR, ownership, reserves), and the measured error rate of the AI-assisted steps.

## Sources

| Source | Used for |
|---|---|
| SEC Form D quarterly data sets, 2015 to 2026 | Fund sizes, company funding rounds |
| precursorvc.com (19 Nov 2026) | Roster, sectors, stated thesis |
| Wayback Machine copies of the site | First year each company was listed |
| Company websites (22 Nov 2026) | Operating, acquired (redirects) or inactive |
| Press coverage | Acquisitions, large rounds, Fund V close |

## How it was built

1. `scripts/formd.py` downloads the Form D data sets and proposes SEC issuers for each roster company. An AI first pass approved 59 clear matches (name, location, founding year) and left 97 for a person.
2. `scripts/label_rounds.py` labels each filed round's stage by size and order, and infers a lead investor from new board seats.
3. `scripts/wayback_first_listed.py` finds the first archived copy of the site that names each company.
4. `scripts/probe.py` and `scripts/classify.sh` check every company website; each acquisition found was then confirmed with press.
5. `scripts/build_dash_data.py` and `scripts/build_dash_data2.py` turn the CSVs in `data/` into the JSON files in `docs/data/` that the page reads.

## Where AI helped, and where it didn't

AI made the volume possible: matching about 300 names across 45 quarters of SEC data, checking every website, and drafting labels with sources. It was weakest at judgment calls. Checked against press on 14 rounds:

| Task | Right |
|---|---|
| Funding-stage label, first rule | 50% |
| Funding-stage label, revised rule (tuned on the same rounds, so optimistic) | 79% |
| Lead investor inferred from board seats | 64% of those named |

An automated "no filing in three years" warning was dropped after it flagged Juniper Square, which raised a Series D in 2025 that was not in the matched filings. Rule used: AI drafts, a person verifies, and the error rate is published.

## What I would change

- Start from the reader's question. An early version led with caveats; the useful version leads with facts and puts limits in an appendix.
- Test the stage rule on rounds it was not tuned on.
- Have a person clear the 97 company matches still awaiting review.
- Reconcile Fund IV: its Form D shows $73.2M, while one press account implies about $82.5M.

## Reproduce

Python 3.9+, standard library only.

```
cd data
python3 ../scripts/formd.py match --email you@example.com      # downloads ~150 MB into data/formd_cache
python3 ../scripts/formd.py rounds
python3 ../scripts/build_dash_data.py ../docs/data formd_rounds_rule_v2_test.csv
python3 ../scripts/build_dash_data2.py ../docs/data current_web.tsv
cd ../docs && python3 -m http.server 8000                          # open http://localhost:8000
```

The SEC asks automated clients to identify themselves, hence `--email`.

## Layout

```
data/      source CSVs (roster, SEC matches and rounds, archive dates, website checks, outcomes)
scripts/   pipeline
docs/      the dashboard (GitHub Pages serves this folder)
```

## License

Code is MIT licensed. Data is compiled from the public sources above; each outcome row links to its source.
