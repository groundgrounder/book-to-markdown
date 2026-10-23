#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""cip_clean.py <book.md> (v2) — 精确删除版权页/CIP 块
反向逻辑: 命中噪音标题后, 吞掉一切"非散文/非标题/非图片/非目录条目"的行(<=100行)。
- 散文: 含，。； 且较长 → 停
- 目录条目: 第X章/X.Y节/点线页码 → 停(防止吃掉紧接的目录/正文)
- 图片行 → 停
输出删除行数 + 边界后第一行存留内容"""
import json, re, sys

HEAD = re.compile(r"^#{1,6}\s*.*(图书在版编目|CIP数据|C\.I\.P|版权页|版权信息|出版信息|版权声明)")
TOC_ENTRY = re.compile(r"^(第[一二三四五六七八九十百千0-9]+[章节]|\d+\.\d+|.{2,40}(…|\.{3,})\s*\d{1,4}\s*$)")

def main():
    p = sys.argv[1]
    lines = open(p, encoding="utf-8").read().split("\n")
    out, i, deleted, survivors = [], 0, 0, []
    while i < len(lines):
        if HEAD.match(lines[i]):
            j = i + 1
            eaten = 0
            while j < len(lines) and eaten < 100:
                s = lines[j].strip()
                if re.match(r"^#{1,6}\s", lines[j]): break          # 新标题
                if not s: eaten += 1; j += 1; continue
                if s.startswith("<") and "img" in s: break           # 图片
                if TOC_ENTRY.match(s): break                         # 目录/正文条目
                if len(s) > 90: break                                # 长散文行
                if len(s) > 45 and s.endswith(("。", "；")): break     # 完整句子=前言类
                eaten += 1; j += 1
            deleted += eaten
            nxt = next((lines[k].strip() for k in range(j, min(j + 8, len(lines))) if lines[k].strip()), "")
            survivors.append((lines[i].strip()[:30], eaten, nxt[:50]))
            i = j
        else:
            out.append(lines[i]); i += 1
    if deleted:
        t = re.sub(r"\n{3,}", "\n\n", "\n".join(out))
        open(p, "w", encoding="utf-8").write(t.strip() + "\n")
    print(json.dumps({"deleted": deleted, "survivors": survivors}, ensure_ascii=False))

if __name__ == "__main__":
    main()
