#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""review_gates.py [书架目录] — 对目录下所有 md 做全量客观校验
缺陷级(必须修): $$ 奇数、页锚点残留、图片缺失、乱码
结构级(需审校): H1 数量异常、无标题结构、目录点线、行内$不配平、孤立数字行
输出 review.tsv + 终端摘要"""
import os, re, sys, json
from urllib.parse import unquote

ROOT = sys.argv[1] if len(sys.argv) > 1 else "."
OUT = sys.argv[2] if len(sys.argv) > 2 else "review.tsv"

def check(md_path):
    t = open(md_path, encoding="utf-8").read()
    masked = re.sub(r"```.*?```", "", t, flags=re.S)
    masked = re.sub(r"`[^`\n]*`", "", masked)
    issues = []
    if masked.count("$$") % 2: issues.append(("缺陷", "$$奇数"))
    if re.search(r"<!-- 第\d+页 -->", t): issues.append(("缺陷", "页锚点残留"))
    base = os.path.dirname(md_path)
    missing = 0
    for m in re.finditer(r'!\[[^\]]*\]\(([^)\s]+)|<img[^>]*src="([^"]+)"', masked):
        ref = unquote(m.group(1) or m.group(2))
        if not ref.startswith(("http://", "https://")) and not os.path.exists(os.path.normpath(os.path.join(base, ref))):
            missing += 1
    if missing: issues.append(("缺陷", f"图片缺失x{missing}"))
    for tag in ("div", "table", "tr", "td"):
        o = len(re.findall(rf"<{tag}[\s>]", t, flags=re.I))
        c = len(re.findall(rf"</{tag}>", t, flags=re.I))
        if o != c: issues.append(("结构", f"<{tag}>标签不配对{o}vs{c}"))
    if "\ufffd" in t: issues.append(("缺陷", "乱码�"))
    h1 = len(re.findall(r"^# ", t, flags=re.M))
    hn = len(re.findall(r"^#{1,6} ", t, flags=re.M))
    if h1 == 0: issues.append(("结构", "无H1"))
    if h1 > 1: issues.append(("结构", f"H1x{h1}"))
    if hn == 0: issues.append(("结构", "无标题结构"))
    if re.search(r"第[章节]\s*[，。、：:]|^第[章节]$", t, flags=re.M): issues.append(("结构", "疑似断章断节"))
    if re.search(r"^\s*[-*]?\s*.{0,60}(\.{4,}|…{3,}|·{4,})\s*\d+\s*$", t, flags=re.M): issues.append(("结构", "目录点线残留"))
    bad_dollar = sum(1 for l in masked.split("\n") if not l.strip().startswith("<") and l.count("$") % 2 and "$$" not in l)
    if bad_dollar: issues.append(("结构", f"行内$不配平x{bad_dollar}"))
    orphan = len(re.findall(r"^\d{1,4}$", t, flags=re.M))
    if orphan > 20: issues.append(("结构", f"孤立数字行x{orphan}"))
    return issues

rows = []
for dirpath, _, files in os.walk(ROOT):
    if "/.st" in dirpath or "/.git" in dirpath: continue
    for fn in files:
        if not fn.endswith(".md") or fn.startswith("._"): continue
        p = os.path.join(dirpath, fn)
        rows.append((p, check(p)))

with open(OUT, "w") as f:
    for p, issues in sorted(rows, key=lambda x: (0 if any(l == "缺陷" for l, _ in x[1]) else 1, -len(x[1]))):
        lvl = "DEFECT" if any(l == "缺陷" for l, _ in issues) else ("STRUCT" if issues else "PASS")
        f.write("\t".join([p, lvl, ";".join(d for _, d in issues)]) + "\n")

nd = sum(1 for _, i in rows if any(l == "缺陷" for l, _ in i))
ns = sum(1 for _, i in rows if i and not any(l == "缺陷" for l, _ in i))
print(f"共 {len(rows)} 本: 缺陷 {nd}, 结构待审 {ns}, 干净 {len(rows)-nd-ns} -> {OUT}")
from collections import Counter
c = Counter()
for _, issues in rows:
    for l, d in issues: c[f"{l}:{d.split('x')[0]}"] += 1
for k, v in c.most_common(10): print(f"  {k}: {v}")
