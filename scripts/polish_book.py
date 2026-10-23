#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""polish_book.py <book.md> — OCR/转换成品 md 的结构化精修(幂等)
1. 标题层级重排: # 仅书名; 卷/编/部→H2 章→H3 节→H4 N、→H5 (N)→H6; 无卷则整体上移
2. 标题清理: 去页码前缀("27 五、"→"五、"); 第X章后补空格; 连续重复书名行只留首个
3. 孤立页码行: 删除被空行夹住的 ^\\d{1,4}$ 行
4. 目录点线: "标题……27"→"标题 27"
5. 公式幻觉截断: $$内同字符>=8连重复/� 处截断并闭合
输出 JSON: 每项改动计数 + 修后门禁
"""
import json, os, re, sys

FRONT = ("导言", "导论", "绪论", "前言", "序言", "总序", "译序", "中译本", "出版说明", "目录",
         "参考文献", "附录", "索引", "后记", "跋", "致谢", "修订版说明", "再版说明",
         "Preface", "Introduction", "Contents", "Bibliography", "Index", "Appendix", "Prologue", "Epilogue")
P_PART = re.compile(r"^第[一二三四五六七八九十百千0-9]+[卷编部篇]")
P_CHAP = re.compile(r"^第[一二三四五六七八九十百千0-9]+章")
P_SEC  = re.compile(r"^第[一二三四五六七八九十百千0-9]+节")
P_ENUM = re.compile(r"^[一二三四五六七八九十]+、")
P_SUB  = re.compile(r"^[（(][一二三四五六七八九十0-9]+[)）]")
RUN    = re.compile(r"(.)\1{7,}")

def is_front(s):
    return any(s.startswith(w) for w in FRONT)

def clean_math_line(l, stats):
    if "\ufffd" not in l and not RUN.search(l):
        return l
    cut = len(l)
    m = RUN.search(l)
    if m: cut = min(cut, m.start())
    u = l.find("\ufffd")
    if u != -1: cut = min(cut, u)
    if cut == len(l): return l
    head = l[:cut]
    # 去掉截断点残留的未完成命令/环境
    head = re.sub(r"\\[a-zA-Z]+\{?$", "", head)
    head = re.sub(r"\\(quad|qquad|,|;|!)\s*$", "", head).rstrip("\\{}, \t")
    # 闭合 $
    if head.count("$$") % 2: head += "$$"
    elif head.count("$") % 2: head += "$"
    stats["math_trunc"] += 1
    return head

def main():
    path = sys.argv[1]
    t = open(path, encoding="utf-8").read()
    stats = dict(h_relevel=0, h_pagenum=0, h_space=0, dup_title=0, orphan=0, dotleader=0, math_trunc=0)
    lines = t.split("\n")

    # 0) 公式幻觉截断(逐行)
    lines = [clean_math_line(l, stats) if "$" in l else l for l in lines]

    # 1) 收集标题, 判断层级基准
    heads = [(i, re.match(r"^(#{1,6})\s*(.*)$", l)) for i, l in enumerate(lines)]
    has_part = any(m and P_PART.match(m.group(2).strip()) for _, m in heads if m)
    has_sec  = any(m and P_SEC.match(m.group(2).strip()) for _, m in heads if m)
    lv_part, lv_chap = 2, (3 if has_part else 2)
    lv_sec = lv_chap + 1
    lv_enum = lv_sec + (1 if has_sec else 0)
    lv_sub = lv_enum + 1

    # 2) 去重复书名行(保留第一个 H1)
    first_h1 = next((i for i, l in enumerate(lines) if l.startswith("# ")), None)
    title = lines[first_h1][2:].strip() if first_h1 is not None else None

    out = []
    prev_blank = True
    for i, l in enumerate(lines):
        m = re.match(r"^(#{1,6})\s*(.*)$", l)
        if m:
            hashes, txt = m.group(1), m.group(2).strip()
            # 重复书名行
            if i != first_h1 and title and txt == title and len(hashes) == 1:
                stats["dup_title"] += 1
                continue
            # 页码前缀 "27 五、" / "27 第五章"
            new = re.sub(r"^\d{1,3}\s+(?=[一二三四五六七八九十第（(])", "", txt)
            if new != txt: stats["h_pagenum"] += 1; txt = new
            # 第X章/节后无空格
            new = re.sub(r"^(第[一二三四五六七八九十百千0-9]+[章节卷编部篇])(?=\S)", r"\1 ", txt)
            if new != txt: stats["h_space"] += 1; txt = new
            # “一、”后无空格
            new = re.sub(r"^([一二三四五六七八九十]+、)(?=\S)", r"\1 ", txt)
            if new != txt: stats["h_space"] += 1; txt = new
            # 层级重排
            if i == first_h1:
                target = 1
            elif P_PART.match(txt) or is_front(txt): target = 2
            elif P_CHAP.match(txt): target = lv_chap
            elif P_SEC.match(txt): target = lv_sec
            elif P_ENUM.match(txt): target = lv_enum
            elif P_SUB.match(txt): target = lv_sub
            elif len(hashes) == 1: target = 2
            else: target = len(hashes)
            if target != len(hashes):
                stats["h_relevel"] += 1
            out.append("#" * target + " " + txt)
            prev_blank = False
            continue
        # 孤立页码行(前后皆空行)
        if re.fullmatch(r"\d{1,4}", l.strip()) and l.strip():
            nxt = lines[i + 1] if i + 1 < len(lines) else ""
            if prev_blank and (not nxt.strip()):
                stats["orphan"] += 1
                prev_blank = True
                continue
        # 目录点线
        if RUN.search("") is None and re.search(r"(\.{3,}|…{2,}|·{3,})\s*\d{1,4}\s*$", l) and len(l) < 120:
            l2 = re.sub(r"\s*(\.{3,}|…{2,}|·{3,})\s*(\d{1,4})\s*$", r" \2", l)
            if l2 != l: stats["dotleader"] += 1; l = l2
        out.append(l)
        prev_blank = (l.strip() == "")

    text = "\n".join(out)
    # 卷名合并: "## 第一卷" 紧跟一个非模式同级标题 → 合并为一行
    if stats.get("_mergeable") or True:
        pat = re.compile(r"^(## 第[一二三四五六七八九十百千0-9]+[卷编部篇])\s*\n\n(## (?!第[一二三四五六七八九十百千0-9]+[卷编部篇章节])(?![一二三四五六七八九十]+、)(?![（(])(.+))$", re.M)
        text, nmerge = pat.subn(lambda m: m.group(1) + " " + m.group(3), text)
        stats["part_merge"] = nmerge
    text = re.sub(r"\n{3,}", "\n\n", text).strip() + "\n"
    open(path, "w", encoding="utf-8").write(text)

    # 门禁
    base = os.path.dirname(path)
    from urllib.parse import unquote
    missing = 0
    for m in re.finditer(r'!\[[^\]]*\]\(([^)\s]+)|<img[^>]*src="([^"]+)"', text):
        ref = unquote(m.group(1) or m.group(2))
        if not ref.startswith(("http://", "https://")) and not os.path.exists(os.path.normpath(os.path.join(base, ref))):
            missing += 1
    h1 = len(re.findall(r"^# ", text, flags=re.M))
    gates = {"dollar_even": text.count("$$") % 2 == 0, "anchors": len(re.findall(r"<!-- 第\d+页 -->", text)),
             "img_missing": missing, "h1": h1, "fffd": text.count("\ufffd")}
    print(json.dumps({"stats": stats, "gates": gates}, ensure_ascii=False))

if __name__ == "__main__":
    main()
