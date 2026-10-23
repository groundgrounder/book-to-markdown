#!/usr/bin/env python3
"""审图裁决有没有真的落到成品 md 里。

审图结论先写回主引擎逐页结果（apply_review），再由 patch_cleaned 改进旧 md。后一步有一串守卫
（两侧各 ≥10 字一致、表格、标题、脚注号……），守卫挡掉的改字只进 skipped.tsv、或者干脆静默跳过
（同一句里两处错字相距 <10 字：两处都不改）。这里逐条核对：裁决后的读法 + 两侧各 4 字在成品里出现了没有；
没出现、而另一种读法出现了 → 没落实。

用法: decision_check.py <成品.md> <sites.tsv> [--fix]
  --fix：只改"另一种读法在成品里恰好出现一次"的（位置唯一），改完重写成品 md；其余列出来人工处理
输出: 每条没落实的一行：n page class 成品现读 → 裁决读法 上下文
"""
import csv, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from patch_cleaned import norm_map, OLD_TAG  # noqa: E402
from crosscheck import norm  # noqa: E402

SKIP_CLASS = {"pagenum", "repeat"}           # 页码、页面重复：本来就不进正文


def main():
    md_path, sites = sys.argv[1], sys.argv[2]
    fix = "--fix" in sys.argv
    md = open(md_path, encoding="utf-8").read()
    fn, fpos = norm_map(md, OLD_TAG)
    todo, bad = [], 0
    for r in csv.DictReader(open(sites, encoding="utf-8"), delimiter="\t"):
        d, ctx = (r["decision"] or "").strip(), r["context"]
        if not d or r["class"] in SKIP_CLASS or "【" not in ctx: continue
        L, rest = ctx.split("【", 1); M, R = rest.split("】", 1)
        if d == "primary": want, other = M, r["insert"]
        elif d == "secondary": want, other = r["insert"], M
        elif d.startswith("="): want, other = d[1:], M
        else: continue
        L4, R4 = norm(L)[-4:], norm(R)[:4]
        w, o = norm(want), norm(other)
        if w == o or len(L4) < 4 or len(R4) < 4: continue
        if (L4 + w + R4) in fn: continue
        hit = [m.start() for m in re.finditer(re.escape(L4 + o + R4), fn)]
        if not hit: continue                 # 两种读法都不在：这段被旧 md 结构改过（标题/表格），看不出来
        bad += 1
        print(f"{r['n']}\t{r['page']}\t{r['class']}\t{other or '∅'} → {want or '∅'}\t{L[-10:]}【{M}】{R[:10]}\t{'唯一' if len(hit) == 1 else f'{len(hit)}处'}")
        if len(hit) == 1 and o and w and len(o) == len(w):
            a = hit[0] + len(L4)
            todo.append((fpos[a], fpos[a + len(o) - 1] + 1, want))
    print(f"# 没落实 {bad} 条；可自动改（位置唯一、等长替换）{len(todo)} 条", file=sys.stderr)
    if fix and todo:
        for a, b, rep in sorted(todo, reverse=True):
            seg = md[a:b]
            # 原文段里夹着非字母数字（标点/空格）时按字位置替换，保留标点
            chars = [i for i in range(a, b) if norm(md[i])]
            if len(chars) != len(norm(rep)): continue
            s = list(md)
            for i, c in zip(chars, [c for c in rep if norm(c)]): s[i] = c
            md = "".join(s)
        open(md_path, "w", encoding="utf-8").write(md)


if __name__ == "__main__":
    main()
