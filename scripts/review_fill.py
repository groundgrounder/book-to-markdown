#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""review_fill.py <sites.tsv> <answers.txt> [--sample 0.1]
把视觉子代理的看图初审（每行 "#编号 A|B|N|? 原文"）填进 sites.tsv 的 decision 列，并列出需要主模型复核的条目。

校准（2026-10-21，deepseek-v4.1-flash 对 34 处已定答案盲审）：答了 30 处、对 27 处（90%），
4 处它说看不到而人能看清；3 处错全是斜体 "vol. 1" 读成 "I"——字形两可时语言先验占上风，
恰好和 VL 错在一起。所以复核这几类：
  ?            看不清
  N            两个都不对（它给的读法不直接采用）
  数字字母形近   候选里有 1/I/l/0/O 这类且涉及数字（英文单词里的字母互换如 Gold[e]nberg/Gold[c]nberg
               是整词判断，校准中全对，不复核）
  抽样          其余 A/B 随机抽 --sample 比例，抽检出错就扩大复核
A → primary，B → secondary。已经有 decision 的行（预填/人工）不覆盖。
输出：更新后的 sites.tsv + 同目录 recheck.txt（待复核编号，按审图板分组）。
"""
import csv, os, random, re, sys
from collections import defaultdict

AMBIG = re.compile(r"[01IlioOS5B8]")   # 数字与字母形近：斜体 1 读成 I 就是这一类


def main():
    tsv, ans = sys.argv[1], sys.argv[2]
    rate = float(sys.argv[sys.argv.index("--sample") + 1]) if "--sample" in sys.argv else 0.1
    answers = {}
    for line in open(ans, encoding="utf-8"):
        m = re.match(r"\s*#(\d+)\s+([ABN?？])\s*(.*)", line)
        if m: answers[m.group(1)] = (m.group(2).replace("？", "?"), m.group(3).strip())
    rows = list(csv.DictReader(open(tsv, encoding="utf-8"), delimiter="\t"))
    rng = random.Random(0)
    recheck, filled = defaultdict(list), 0
    for r in rows:
        if r["decision"] or r["sheet"] == "": continue
        a = answers.get(r["n"])
        why = None
        if a is None: why = "未答"
        elif a[0] == "?": why = "看不清"
        elif a[0] == "N": why = f"都不对:{a[1]}"
        elif AMBIG.search(r["primary"] + r["secondary"]) and re.search(r"\d", r["primary"] + r["secondary"] + a[1]):
            why = "数字字母形近"
        elif rng.random() < rate: why = "抽样"
        if a and a[0] in "AB":
            r["decision"] = "primary" if a[0] == "A" else "secondary"; filled += 1
        if why:
            recheck[r["sheet"]].append(f"#{r['n']}({why}; 初审{a[0] if a else '-'})")
    with open(tsv, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=rows[0].keys(), delimiter="\t"); w.writeheader(); w.writerows(rows)
    out = os.path.join(os.path.dirname(tsv), "recheck.txt")
    with open(out, "w", encoding="utf-8") as f:
        for sh in sorted(recheck, key=int):
            f.write(f"sheet_{int(sh):03d}: {' '.join(recheck[sh])}\n")
    n = sum(map(len, recheck.values()))
    print(f"填入 {filled} 处初审；待复核 {n} 处（{len(recheck)} 张审图板）→ {out}")


if __name__ == "__main__":
    main()
