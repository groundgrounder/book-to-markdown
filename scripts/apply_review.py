#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""apply_review.py <sites.tsv> <主引擎目录> [--dry-run]
把 crosscheck.py 审图后的裁决写回主引擎的逐页 md（merge_pages.py 之前做）。

decision 列：
  primary / 空     保留主引擎原文（空 = 未裁决，会列出来提醒）
  secondary        用 insert 列替换 raw_start:raw_end（漏段 = 在 raw_start 处插入；extra/repeat = 删除）
  =文字            用"="后面的文字替换
每页第一次改动前备份为 <页>.md.orig；之后每次都从 .orig 重放全部裁决，可反复改 tsv 重跑。
md 的 sha1 与 crosscheck 时不符（md 被别的步骤改过）→ 拒绝改这一页，需重跑 crosscheck。
"""
import csv, glob, hashlib, os, sys
from collections import defaultdict


def main():
    tsv, root = sys.argv[1], sys.argv[2]
    dry = "--dry-run" in sys.argv
    mds = {os.path.basename(f)[:-3]: f for f in glob.glob(os.path.join(root, "**", "*.md"), recursive=True)}
    rows = list(csv.DictReader(open(tsv, encoding="utf-8"), delimiter="\t"))
    edits, undecided, manual = defaultdict(list), [], []
    for r in rows:
        d = (r["decision"] or "").strip()
        if not d:
            undecided.append(r["n"]); continue
        if d in ("primary", "skip"):
            continue
        if r["raw_start"] == "":
            manual.append(r["n"]); continue          # 漏段没找到插入位置 / 文字层独有：手工补
        new = r["insert"] if d == "secondary" else d[1:] if d.startswith("=") else None
        if new is None:
            sys.exit(f"#{r['n']}: 看不懂的 decision {d!r}（primary / secondary / =文字）")
        edits[r["page"]].append((int(r["raw_start"]), int(r["raw_end"]), new, r["md_sha1"], r["n"]))

    changed = 0
    for page, es in sorted(edits.items()):
        md = mds.get(page)
        if not md:
            print(f"✗ {page}: 找不到 md"); continue
        orig = md + ".orig"
        src = open(orig if os.path.exists(orig) else md, encoding="utf-8").read()
        if hashlib.sha1(src.encode()).hexdigest()[:12] != es[0][3]:
            print(f"✗ {page}: md 与 crosscheck 时不一致，跳过（重跑 crosscheck.py）"); continue
        # 从后往前改，前面的偏移不受影响；重叠的裁决只认第一条
        es.sort(key=lambda e: (e[0], e[1]))
        last_start, text = len(src) + 1, src
        for a, b, new, _, n in reversed(es):
            if b > last_start:
                print(f"  ⚠️ {page} #{n} 与后一条裁决区间重叠，跳过"); continue
            text = text[:a] + new + text[b:]; last_start = a
        if dry:
            print(f"{page}: {len(es)} 处（dry-run）"); continue
        if not os.path.exists(orig):
            os.rename(md, orig)
        open(md, "w", encoding="utf-8").write(text)
        changed += len(es)
    print(f"写回 {changed} 处裁决，涉及 {len(edits)} 页" + ("（dry-run 未写）" if dry else ""))
    if undecided: print(f"未裁决 {len(undecided)} 处: #{' #'.join(undecided[:20])}")
    if manual: print(f"需手工处理 {len(manual)} 处（无插入位置/文字层独有）: #{' #'.join(manual[:20])}")


if __name__ == "__main__":
    main()
