#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""orphan_check.py <pp_structurev3 结果目录> [--tsv out.tsv]
pp_structurev3 单引擎自检：整页 OCR（overall_ocr_res）认出来、却没进任何版面块的行 = 静默丢失。

机制：pp_structurev3 先做版面检测，再只把落在版面块里的文字写进 md。版面模型漏框
（灰底案例框、照片旁的行、页底末行、整栏对话实录）时，那些行 OCR 明明认出来了，md 里却没有，
现有的守恒检查（fidelity_diff 对比的是 OCR 原始输出）看不见。
行中心落在页眉/页脚/页码/图片块里的不算（本来就该丢）。

只适用于 pp_structurev3 结果（PaddleOCR-VL 没有整页 OCR，用 crosscheck.py）。
目录可以是 pdf_ocr.sh 的 <书名>/ 或 <书名>/pages/，也可以是平铺的 *_res.json 目录。
"""
import difflib, glob, json, os, re, sys, unicodedata

DROPPED = {"header", "header_image", "footer", "footer_image", "number", "image", "chart", "seal"}

def norm(s):
    s = unicodedata.normalize("NFKC", re.sub(r"<[^>]+>", "", s)).lower()
    return "".join(ch for ch in s if unicodedata.category(ch)[0] in "LN")

def orphans(res):
    blocks = res["parsing_res_list"]
    md = norm("".join(b.get("block_content") or "" for b in blocks if b.get("block_label") not in DROPPED))
    skip = [b["block_bbox"] for b in blocks if b.get("block_label") in DROPPED]
    o = res.get("overall_ocr_res") or {}
    out = []
    for t, box in zip(o.get("rec_texts", []), o.get("rec_boxes", [])):
        nt = norm(t)
        if len(nt) < 4 or nt in md:
            continue
        # 块内重识别与整页 OCR 偶有一两字出入，七成连续命中就算在
        if difflib.SequenceMatcher(None, nt, md, autojunk=False).find_longest_match(0, len(nt), 0, len(md)).size >= 0.7 * len(nt):
            continue
        cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
        if any(b[0] <= cx <= b[2] and b[1] <= cy <= b[3] for b in skip):
            continue
        out.append((t, [int(x) for x in box]))
    return out

def main():
    root = sys.argv[1]
    tsv = sys.argv[sys.argv.index("--tsv") + 1] if "--tsv" in sys.argv else None
    files = sorted(glob.glob(os.path.join(root, "**", "*_res.json"), recursive=True))
    if not files:
        sys.exit(f"no *_res.json under {root}")
    rows, chars = [], 0
    for f in files:
        res = json.load(open(f, encoding="utf-8"))
        if "overall_ocr_res" not in res:
            sys.exit(f"{f}: 没有 overall_ocr_res（PaddleOCR-VL 结果？用 crosscheck.py）")
        page = os.path.basename(f)[:-len("_res.json")]
        for t, box in orphans(res):
            rows.append((page, t, box)); chars += len(norm(t))
    pages = sorted({p for p, _, _ in rows})
    print(f"{len(files)} 页：孤儿行 {len(rows)} 行 / {chars} 字，分布在 {len(pages)} 页")
    for p in pages[:30]:
        ls = [t for q, t, _ in rows if q == p]
        print(f"  {p}: {len(ls)} 行  {' | '.join(x[:20] for x in ls[:3])}")
    if tsv:
        with open(tsv, "w", encoding="utf-8") as fo:
            fo.write("page\tbbox\ttext\n")
            for p, t, b in rows:
                fo.write(f"{p}\t{','.join(map(str, b))}\t{t}\n")
        print(f"-> {tsv}")
    sys.exit(1 if rows else 0)

if __name__ == "__main__":
    main()
