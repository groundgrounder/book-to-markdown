#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""toc_fix.py <book.md> (v2) — 目录整理(幂等)
三种情形:
A. 已有 ## 目录 + 列表块 → 解析条目, 重新拼接/规范化, 重排缩进
B. 找到印刷目录(含杂缀的"目录"行, 前25%) → 吞条目→拼接→嵌套列表
C. 全书无印刷目录 → 从正文标题树合成 ## 目录 并插在书名后
拼接规则: 纯页码行并入上条; "第四十四章"独立行与下一非模式行合并;
条目内"第X章标题"补空格; 尾部点线/省略号清除; 页码保留
输出 JSON
"""
import json, re, sys

P_PART = re.compile(r"^第[一二三四五六七八九十百千0-9]+[卷编部篇]")
P_CHAP = re.compile(r"^第[一二三四五六七八九十百千0-9]+章")
P_SEC  = re.compile(r"^第[一二三四五六七八九十百千0-9]+节")
P_ENUM = re.compile(r"^[一二三四五六七八九十]+、")
P_SUB  = re.compile(r"^[（(][一二三四五六七八九十0-9]+[)）]")
P_NUMONLY = re.compile(r"^第[一二三四五六七八九十百千0-9]+[章节卷编部篇]\s*$")
P_PAGE = re.compile(r"^[（(]?\d{1,4}[)）]?$")
FRONT  = ("导言","导论","绪论","前言","序言","总序","译序","中译本","出版说明","参考文献","附录","索引","后记","跋","致谢","修订版","再版说明","内容提要","内容简介","Preface","Introduction","Contents","Bibliography","Index","Appendix","Prologue","Epilogue","Foreword")
STOP = re.compile(r"[。！？；]$")

def level_of(s):
    if P_PART.match(s): return 0
    if any(s.startswith(w) for w in FRONT): return 0
    if P_CHAP.match(s): return 1
    if P_SEC.match(s): return 2
    if P_ENUM.match(s): return 2
    if P_SUB.match(s): return 3
    return None

def norm(s):
    return re.sub(r"[\s·、:：.…\-—_()（）\[\]]", "", s)

def clean_entry(s):
    s = re.sub(r"[\s.…·\-—]*\d{0,4}\s*$", "", s).strip()   # 尾部点线+页码
    s = re.sub(r"[.…·]{1,}\s*$", "", s).strip()
    s = re.sub(r"^\d{1,3}(?=第[一二三四五六七八九十百千0-9]+[章节卷编部篇])", "", s)  # 头部页码
    s = re.sub(r"^(第[一二三四五六七八九十百千0-9]+[章节卷编部篇])(?=\S)", r"\1 ", s)
    s = re.sub(r"^([一二三四五六七八九十]+、)(?=\S)", r"\1 ", s)
    return s

def join_entries(raw):
    """拼接多行条目"""
    out = []
    for s in raw:
        s = s.strip()
        if not s: continue
        s2 = re.sub(r"^[.…·\s]+", "", s)   # 去头部点线
        if P_PAGE.match(s2) and out:
            continue  # 页码行丢弃(保留条目文字为主)
        if P_NUMONLY.match(s):
            out.append(s); continue          # 暂存, 等待标题行合并
        if out and P_NUMONLY.match(out[-1]) and level_of(s) is None:
            out[-1] = out[-1] + " " + s; continue
        out.append(s)
    return [clean_entry(e) for e in out if clean_entry(e)]

def emit(entries):
    lines, prev = ["## 目录", ""], 0
    for e in entries:
        lv = level_of(e)
        if lv is None: lv = prev
        prev = lv
        lines.append("  " * lv + "- " + e)
    return lines

def main():
    path = sys.argv[1]
    t = open(path, encoding="utf-8").read()
    lines = t.split("\n")
    n = len(lines)

    # A. 已有 ## 目录 列表块
    for i, l in enumerate(lines):
        if re.fullmatch(r"##\s*目录", l.strip()):
            j = i + 1
            raw = []
            while j < n and (re.match(r"^\s*-\s+", lines[j]) or not lines[j].strip()):
                m = re.match(r"^\s*(?:-\s+)*(.*)$", lines[j])
                if m and m.group(1).strip(): raw.append(m.group(1))
                j += 1
            entries = join_entries(raw)
            if not entries:
                pass  # 空块: 不落盘, 落入 B 模式按纯文本条目重吞(从该标题行起)
            else:
                if len(entries) > 250:   # 巨目录(多为合成)只保留到章级, 封顶 200
                    entries = [e for e in entries if (level_of(e) or 0) <= 1][:200]
                body_heads = [norm(re.sub(r"^#{1,6}\s*", "", x)) for x in lines if re.match(r"^#{1,6}\s", x) and not x.startswith("## 目录")]
                matched = sum(1 for e in entries if norm(e) in body_heads)
                new = lines[:i] + emit(entries) + [""] + lines[j:]
                open(path, "w", encoding="utf-8").write("\n".join(new))
                print(json.dumps({"mode": "re-emit", "entries": len(entries),
                                  "rate": round(matched / max(len(entries), 1), 2)}, ensure_ascii=False))
                return

    # B. 印刷目录(前 25% 内含"目录"二字且行长短的)
    limit = int(n * 0.25)
    start = None
    for i, l in enumerate(lines[:limit]):
        s = l.strip()
        if len(s) <= 25 and "目录" in s and not s.startswith("#"):
            start = i
            break
        if re.fullmatch(r"#{1,6}\s*目\s*录\s*", s):
            start = i
            break
    if start is not None:
        entries_raw, end, blanks = [], start + 1, 0
        while end < n:
            s = lines[end].strip()
            if not s:
                blanks += 1
                if blanks > 6: break
                end += 1; continue
            if s.startswith("#"): break
            entries_raw.append(s); blanks = 0
            #  lookahead: 下一条不像条目就停
            core = clean_entry(s)
            if level_of(core) is None and (len(core) > 30 or STOP.search(core) or "，" in core):
                entries_raw.pop(); break
            end += 1
        entries = join_entries(entries_raw)
        if len(entries) >= 3:
            body_heads = [norm(re.sub(r"^#{1,6}\s*", "", x)) for x in lines if re.match(r"^#{1,6}\s", x)]
            matched = sum(1 for e in entries if norm(e) in body_heads)
            new = lines[:start] + emit(entries) + [""] + lines[end:]
            open(path, "w", encoding="utf-8").write("\n".join(new))
            print(json.dumps({"mode": "rebuilt", "entries": len(entries),
                              "rate": round(matched / len(entries), 2)}, ensure_ascii=False))
            return
        print(json.dumps({"mode": "found-too-few", "entries": len(entries)})); return

    # C. 从标题树合成(只取到章级, 封顶 200 条)
    heads = []
    for l in lines:
        m = re.match(r"^(#{1,6})\s+(.*)$", l)
        if not m: continue
        lv, txt = len(m.group(1)), m.group(2).strip()
        if lv == 1: continue                      # 跳过书名
        depth = min(lv - 1, 3)
        if depth <= 1:
            heads.append((depth, txt))
    if len(heads) < 3:
        print(json.dumps({"mode": "no-toc-no-heads"})); return
    heads = heads[:200]
    # 插入位置: 书名(H1)之后
    ins = next((i for i, l in enumerate(lines) if l.startswith("# ")), 0) + 1
    toc = ["## 目录", ""] + ["  " * lv + "- " + txt for lv, txt in heads] + [""]
    new = lines[:ins] + [""] + toc + lines[ins:]
    open(path, "w", encoding="utf-8").write("\n".join(new))
    print(json.dumps({"mode": "synthesized", "entries": len(heads)}, ensure_ascii=False))

if __name__ == "__main__":
    main()
