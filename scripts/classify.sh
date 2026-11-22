#!/bin/bash
# usage: classify.sh sites.tsv out.tsv   -> company, url, http_code, final_url, title
: > "$2"
while IFS=$'\t' read c u; do
  [ -z "$u" ] && { printf "%s\t\t000\t\t\n" "$c" >> "$2"; continue; }
  r=$(curl -sSL -m 20 -A "Mozilla/5.0 (portfolio-research)" -o body.tmp -w "%{http_code}\t%{url_effective}" "$u" 2>/dev/null)
  [ -z "$r" ] && r=$'000\t'
  t=$(python3 -I -c "
import re,html,os
s=open('body.tmp',encoding='utf-8',errors='replace').read() if os.path.exists('body.tmp') else ''
m=re.search(r'(?is)<title[^>]*>(.*?)</title>',s)
t=re.sub(r'\s+',' ',html.unescape(m.group(1))).strip()[:90] if m else ''
if not t and '/lander' in s: t='(parked: /lander)'
print(t.replace('\t',' '))" 2>/dev/null)
  printf "%s\t%s\t%s\t%s\n" "$c" "$u" "$r" "$t" >> "$2"; rm -f body.tmp
done < "$1"
