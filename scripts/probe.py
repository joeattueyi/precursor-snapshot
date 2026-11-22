"""Checks each company website: final address after redirects, HTTP status and page title.
Usage: python3 probe.py sites.tsv out.tsv   (sites.tsv: company<TAB>url per line)
Follow up unclear results with classify.sh, which retries with curl.
"""
import sys, urllib.request, urllib.parse, ssl, re, html, concurrent.futures as cf
UA={"User-Agent":"Mozilla/5.0 (portfolio-research)"}
ctx=ssl.create_default_context()
def probe(line):
    c,u=line.rstrip("\n").split("\t")
    if not u: return c,u,"","no url",""
    try:
        with urllib.request.urlopen(urllib.request.Request(u,headers=UA),timeout=20,context=ctx) as r:
            body=r.read(200000).decode("utf-8","replace")
            final=r.geturl()
            t=re.search(r"(?is)<title[^>]*>(.*?)</title>",body)
            title=re.sub(r"\s+"," ",html.unescape(t.group(1))).strip()[:90] if t else ""
            return c,u,final,str(r.status),title
    except urllib.error.HTTPError as e:
        return c,u,"",f"HTTP {e.code}",""
    except Exception as e:
        return c,u,"",type(e).__name__+": "+str(e)[:60],""
lines=[l for l in open(sys.argv[1]) if l.strip()]
with cf.ThreadPoolExecutor(16) as ex, open(sys.argv[2],"w") as out:
    for res in ex.map(probe,lines):
        out.write("\t".join(res)+"\n")
