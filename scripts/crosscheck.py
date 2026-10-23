#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""crosscheck.py <主引擎目录> <副引擎目录> <审图输出目录> [--pdf book.pdf] [--render 渲染图目录] [--old 旧md]
双引擎逐页对拍：两个架构不同的引擎（PaddleOCR-VL 为主、pp_structurev3 为副）在同一位置犯同一个错的概率很低，
所以只需要看它们不一致的地方。输出 sites.tsv（每个分歧点一行）+ sheets/*.png（分歧行的原图切片，编号对应 tsv）。

分歧类型（class）：
  drop     副引擎有、主引擎整段没有（主漏段？还是副把图中文字/页眉认进来了？）
  drop-t   只有 PDF 自带文字层有（--pdf；文字层常是劣质 OCR，多为乱码，低优先）
  extra    只有主引擎有（幻觉/重复？也可能是副引擎漏的）
  char     短分歧：错字/少字/多字 → 看图裁决
  dash     一方是"一"、另一方为空：破折号/连字符被认成"一"（多为 PP 的错）
  digit    1/l、0/o 互混
  num      只有副引擎有的纯数字：多为页边的原版书页码（译著）被 PP 混进正文，也可能是主引擎漏了年份
  repeat   主引擎同一片段连续重复 ≥3 次：VLM 失控生成
  pagenum  副引擎把本页页码混进正文（PP 常见）
pagenum/dash/digit 预填 decision=primary、不出图（试点中全是主引擎对）。
每页还报告"未对齐率"：两引擎阅读顺序差太多时，短分歧会藏进大段错位里，这些页要整页看。

--old（重排已清洗过的旧书，配合 patch_cleaned.py）：副引擎/文字层独有、旧 md 里已经有的段落自动判 primary
——旧 md 是骨架，它们不会丢；剩下的多是图中文字，少数是两边都漏的正文，要看。

裁决：在 sites.tsv 的 decision 列填 primary（保留主引擎）/ secondary（换成副引擎的 insert 列）/
=自定义文字，然后 apply_review.py 把裁决写回主引擎的逐页 md。raw_start/raw_end 是主引擎 md 的字符偏移。

两个目录要是同一套渲染图的结果（pdf_ocr.sh 默认如此：<outdir>/<书名>/pages + render）。
"""
import csv, difflib, glob, hashlib, json, os, re, subprocess, sys, unicodedata

IGNORE = {"header", "header_image", "footer", "footer_image", "number"}
# 试点中这几类全部是主引擎（VL）对，预填 primary、不出图；审校时扫一眼 tsv 即可
# drop-t：只有 PDF 自带文字层有的段落。两本书 170 处全是劣质 OCR 层的乱码或图中文字、0 处真正文 → 预填，tsv 里仍列出
# "一X"常用词的第二字：一个 一种 一些 一切 一样 一般 一定 一直 一致 一起 一同 一贯 一旦 一向 一度 一方 一面 一边 一部
# 一次 一点 一时 一生 一体 一对 一一 一妻 一夫 一位 一名 一项 一条 一份 一类 一套 一系 一系列 一段 一步 一半 一端 一层……
YI_NEXT = set("个种些切样般定直致起同贯旦向度方面边部次点时生体对一妻夫位名项条份类套系段步半端层门家件句"
              "席员群批组场番回阵类言心身无概律味再连经味举纸本字句篇首张")
PREFILL = {"pagenum": "primary", "dash": "primary", "digit": "primary", "num": "primary", "drop-t": "primary"}
COLS = ["n", "page", "class", "primary", "secondary", "sheet", "context", "decision",
        "raw_start", "raw_end", "insert", "md_sha1"]
# 独占一行的 1–3 位数字 = 页边的原版书页码（VL 标为 aside_text 保留下来），正文里的数字从不单独成行
TAG = re.compile(r"<[^>]+>|!\[[^\]]*\]\([^)]*\)|\\[a-zA-Z]+|&#?\w+;|^[ \t]*\d{1,3}[ \t]*$", re.M)


def norm_map(s):
    """归一化（只留字母数字、NFKC、小写）并记住每个字在原文的位置，用来回填原文上下文。"""
    skip = [False] * len(s)
    for m in TAG.finditer(s):
        for i in range(m.start(), m.end()): skip[i] = True
    out, pos = [], []
    for i, ch in enumerate(s):
        if skip[i]: continue
        for c in unicodedata.normalize("NFKC", ch).lower():
            if unicodedata.category(c)[0] in "LN":
                out.append(c); pos.append(i)
    return "".join(out), pos


def norm(s):
    return norm_map(s)[0]


def load_pages(root):
    """页名 -> res.json 路径。支持 pdf_ocr.sh 布局与平铺目录。"""
    return {os.path.basename(f)[:-len("_res.json")]: f
            for f in glob.glob(os.path.join(root, "**", "*_res.json"), recursive=True)}


def blocks(res):
    return [(b.get("block_label"), b.get("block_bbox"), b.get("block_content") or "") for b in res["parsing_res_list"]]


def body(res):
    return "\n".join(c for lab, _, c in blocks(res) if lab not in IGNORE)


def grams(s, k):
    return {s[i:i + k] for i in range(len(s) - k + 1)}


def uncovered(a, b, k=6, min_run=8):
    """a 中连续 >=min_run 字在 b 任何位置都找不到（与顺序无关）。"""
    g = grams(b, k)
    cov = [False] * len(a)
    for i in range(len(a) - k + 1):
        if a[i:i + k] in g:
            for j in range(i, i + k): cov[j] = True
    runs, i = [], 0
    while i < len(a):
        if cov[i]: i += 1; continue
        j = i
        while j < len(a) and not cov[j]: j += 1
        if j - i >= min_run: runs.append((i, j))
        i = j
    return runs


def fuzzy_in(span, text, thr=0.6):
    n = len(span)
    if not n or len(text) < n // 2: return False
    for i in range(0, max(1, len(text) - n + 1), max(1, n // 4)):
        if difflib.SequenceMatcher(None, span, text[i:i + n], autojunk=False).ratio() >= thr:
            return True
    return False


def mask(s, runs):
    keep = [True] * len(s)
    for a, b in runs:
        for i in range(a, b): keep[i] = False
    return "".join(c for c, k in zip(s, keep) if k)


def classify(p, s, pagenums):
    if not p and s.isdigit() and any(n in s for n in pagenums): return "pagenum"
    # 只有副引擎有的纯数字：多半是页边的原版书页码（译著常见）被 PP 混进正文，但也可能是真年份 → 出图低优先
    if not p and s.isdigit() and len(s) <= 3: return "num"
    if not p and s.isdigit(): return "year"   # 4 位：可能是主引擎漏了年份，要看图
    if {p, s} <= {"一", ""} and p != s: return "dash"
    if len(p) == len(s) == 1 and {p, s} in ({"1", "l"}, {"0", "o"}): return "digit"
    return "char"


def ocr_lines(res):
    o = res.get("overall_ocr_res")
    if o: return list(zip(o["rec_texts"], o["rec_boxes"]))
    return [(c, bb) for lab, bb, c in blocks(res) if lab not in IGNORE and c]   # VL：退化成块级框


def _best(lines, sn, need_unique=False):
    """与探针最长公共子串最长的那一行。need_unique：第一名和第二名一样长（参考文献里一串
    "Colapinto, J." 开头的条目）就返回 None，让调用方加长探针再试。"""
    scores = []
    for t, box in lines:
        nt = norm(t)
        if not nt: continue
        r = difflib.SequenceMatcher(None, sn, nt, autojunk=False).find_longest_match(0, len(sn), 0, len(nt)).size
        scores.append((r, box))
    if not scores: return None
    scores.sort(key=lambda x: -x[0])
    if need_unique and len(scores) > 1 and scores[0][0] == scores[1][0]: return None
    return scores[0][1]


def locate(lines, probe):
    """返回要切的行框列表。probe 为 (前文, 分歧, 后文) 时分别找"前文+分歧"和"分歧+后文"所在的行：
    分歧恰在换行处时两者是相邻两行，两行都切（只切一行会切错行，家庭治疗概论初审里出现过）。"""
    if isinstance(probe, str):
        bb = _best(lines, norm(probe)); return [bb] if bb is not None else []
    left, mid, right = probe
    a = b = None
    for k in (8, 14, 20, 30):          # 有并列就加长上下文
        a = a or _best(lines, left[-k:] + mid, need_unique=k < 30)
        b = b or _best(lines, mid + right[:k], need_unique=k < 30)
        if a is not None and b is not None: break
    if a is None or b is None: return [x for x in (a, b) if x is not None]
    return [a] if list(a) == list(b) else [a, b]


def textlayer(pdf, page_name):
    m = re.fullmatch(r"p(\d+)", page_name)
    if not (pdf and m): return ""
    n = int(m.group(1)) + 1
    return subprocess.run(["pdftotext", "-raw", "-f", str(n), "-l", str(n), pdf, "-"],
                          capture_output=True, text=True).stdout


def main():
    a = sys.argv[1:]
    opt = lambda k: a[a.index(k) + 1] if k in a else None
    pdf, render, old_md = opt("--pdf"), opt("--render"), opt("--old")
    for k in ("--pdf", "--render", "--old"):
        if k in a: i = a.index(k); a = a[:i] + a[i + 2:]
    pri_root, sec_root, out = a[0], a[1], a[2]
    render = render or os.path.join(pri_root, "render")
    P, S = load_pages(pri_root), load_pages(sec_root)
    common = sorted(set(P) & set(S))
    if not common: sys.exit("两个目录没有同名页")
    if set(P) ^ set(S): print(f"⚠️ 只有一方有结果的页: {sorted(set(P) ^ set(S))[:10]}")
    os.makedirs(os.path.join(out, "sheets"), exist_ok=True)

    sites, unaligned, pages_norm = [], [], {}
    for page in common:
        pr, sr = json.load(open(P[page], encoding="utf-8")), json.load(open(S[page], encoding="utf-8"))
        # 主引擎以它的 md 为准（apply_review.py 改的就是这个文件），偏移量都指向它
        mdf = P[page][:-len("_res.json")] + ".md"
        praw = open(mdf, encoding="utf-8").read() if os.path.exists(mdf) else body(pr)
        sha = hashlib.sha1(praw.encode()).hexdigest()[:12]
        pn, ppos = norm_map(praw)
        sraw = body(sr)
        sn, spos = norm_map(sraw)
        pages_norm[page] = (pn, sn)
        ign = norm(" ".join(c for res in (pr, sr) for lab, _, c in blocks(res) if lab in IGNORE))
        pagenums = {norm(c) for res in (pr, sr) for lab, _, c in blocks(res) if lab == "number" and norm(c)}
        lines = ocr_lines(sr) if sr.get("overall_ocr_res") else ocr_lines(pr)

        def rawspan(i1, i2):
            """主引擎归一化区间 [i1,i2) → md 原文区间；空区间（插入）落在前一个保留字之后。"""
            if i1 < i2: return ppos[i1], ppos[i2 - 1] + 1
            at = ppos[i1 - 1] + 1 if i1 > 0 else (ppos[0] if ppos else 0)
            return at, at

        def ctx(a, b):
            return (praw[max(0, a - 15):a] + "【" + praw[a:b] + "】" + praw[b:b + 15]).replace("\n", "⏎")

        def add(kind, cls, ptext, stext, probe, a=None, b=None, ins=""):
            sites.append({"page": page, "kind": kind, "class": cls, "primary": ptext, "secondary": stext,
                          "context": ctx(a, b) if a is not None else "", "probe": probe, "lines": lines,
                          "raw_start": "" if a is None else a, "raw_end": "" if b is None else b,
                          "insert": ins, "sha": sha})

        def anchor_after(sx):
            """副引擎 sn[sx] 之前的一段上下文在主引擎里唯一出现 → 在它后面插入。返回 md 原文位置或 None。"""
            for k in (12, 8):
                c = sn[max(0, sx - k):sx]
                if len(c) >= 6 and pn.count(c) == 1:
                    return ppos[pn.find(c) + len(c) - 1] + 1
            return None

        # 1) 副引擎有、主引擎整段没有
        for x, y in uncovered(sn, pn):
            span = sn[x:y]
            if fuzzy_in(span, ign, 0.5) or fuzzy_in(span, pn): continue
            ins = sraw[spos[x]:spos[y - 1] + 1]
            at = anchor_after(x)
            if at is not None and x > 0 and "\n" in sraw[spos[x - 1]:spos[x]]:
                ins = "\n\n" + ins + "\n\n"     # 副引擎里这段是独立成段的
            add("drop", "drop", "", span, span[:30], at, at, ins)
        # 2) 只有 PDF 文字层有（劣质 OCR 层多为乱码，低优先，不给自动插入）
        tl = norm(textlayer(pdf, page))
        for x, y in uncovered(tl, pn):
            span = tl[x:y]
            if fuzzy_in(span, ign, 0.5) or fuzzy_in(span, pn) or fuzzy_in(span, sn): continue
            add("drop", "drop-t", "", span, span[:30])
        # 3) 只有主引擎有
        for x, y in uncovered(pn, sn + "|" + tl):
            a, b = rawspan(x, y)
            add("extra", "extra", pn[x:y], "", pn[x:y][:30], a, b, "")
        # 4) 主引擎内部的复读（VLM 失控生成的典型产物）
        for m in re.finditer(r"(.{4,30}?)\1{2,}", pn):
            a, b = rawspan(m.start(), m.end())
            add("extra", "repeat", m.group(0)[:60], m.group(1), m.group(0)[:30], a, b, "")
        # 5) 短分歧
        keep = [True] * len(sn)
        for x, y in uncovered(sn, pn):
            for i in range(x, y): keep[i] = False
        idx = [i for i in range(len(sn)) if keep[i]]
        so = "".join(sn[i] for i in idx)
        sm = difflib.SequenceMatcher(None, pn, so, autojunk=False)
        long_ = 0
        for tag, i1, i2, j1, j2 in sm.get_opcodes():
            if tag == "equal": continue
            if max(i2 - i1, j2 - j1) > 6: long_ += i2 - i1; continue
            p, s = pn[i1:i2], so[j1:j2]
            ins = sraw[spos[idx[j1]]:spos[idx[j2 - 1]] + 1] if j2 > j1 else ""
            a, b = rawspan(i1, i2)
            # 切图用副引擎（PP）的整页 OCR 行定位，所以探针中间取 PP 的读法
            add("sub", classify(p, s, pagenums), p, s, (pn[max(0, i1 - 30):i1], s or p, pn[i2:i2 + 30]), a, b, ins)
            sites[-1]["lctx"], sites[-1]["rctx"] = pn[max(0, i1 - 3):i1], pn[i2:i2 + 3]
        if pn and long_ / len(pn) > 0.05:
            unaligned.append((page, long_ / len(pn)))

    # ---- 重排旧书（patch_cleaned 场景）：副引擎/文字层独有的段落若旧 md 里已有 → 骨架会保留它，不必审 ----
    if old_md:
        tag = re.compile(r"\[\^[^\]\s]+\]:?|\[![A-Za-z]+\]|<!--.*?-->|<[^>]+>|!\[[^\]]*\]\([^)]*\)|\\[a-zA-Z]+|&#?\w+;", re.S)
        on = norm(tag.sub("", open(old_md, encoding="utf-8").read()))
        for s in sites:
            if s["class"] in ("drop", "drop-t"):
                span = s["secondary"]
                if sum(b - a for a, b in uncovered(span, on, 8, 8)) < 0.3 * len(span):
                    s["auto"] = "primary"; s["class"] += "+旧md有"
            elif s["class"] == "repeat" and s["primary"] in pages_norm[s["page"]][1]:
                s["auto"] = "primary"; s["class"] += "+原文如此"   # 副引擎也读出同样的重复（Corey, Corey, & Corey）

    # ---- 全书佐证：短分歧"前后各 2 字 + 候选"在本页以外的两个引擎正文里各出现 ≥2 次、另一候选在两边都 0 次 → 自动裁决
    # 要求两个引擎都支持，防止一个引擎拿自己的误读给自己投票；原书罕见写法（迷团）在别处没有佐证，照样出图
    corpus = {"P": "|".join(pages_norm[p][0] for p in common), "S": "|".join(pages_norm[p][1] for p in common)}
    auto = 0
    for s in sites:
        if s["kind"] != "sub" or s["class"] not in ("char", "num"): continue
        if max(len(s["primary"]), len(s["secondary"])) > 2: continue   # 大分歧（整格/整词）要看图
        # 一侧为空（少字/多字）不用书证："去掉这个字"的上下文天然比"带这个字"更常见，会偏向删字
        # （心理咨询书里把"体验还可以""生活是我们""因素。"的 还/是/。 都判没了）
        if not s["primary"] or not s["secondary"]: continue
        pn_, sn_ = pages_norm[s["page"]]
        k = 3 if re.search(r"[a-z0-9]", s["primary"] + s["secondary"]) else 2
        L, R = s["lctx"][-k:], s["rctx"][:k]
        if len(L) < k or len(R) < k: continue
        cnt = {}
        for side, cand in (("p", L + s["primary"] + R), ("s", L + s["secondary"] + R)):
            cnt[side] = min(corpus["P"].count(cand) - pn_.count(cand), corpus["S"].count(cand) - sn_.count(cand)), \
                        max(corpus["P"].count(cand) - pn_.count(cand), corpus["S"].count(cand) - sn_.count(cand))
        if cnt["p"][0] >= 2 and cnt["s"][1] == 0: s["auto"] = "primary"
        elif cnt["s"][0] >= 2 and cnt["p"][1] == 0: s["auto"] = "secondary"
        else: continue
        s["class"] += "+书证"; auto += 1

    # 破折号类默认信主引擎（PP 把破折号认成"一"）。但 VL 也会反过来把"一"认成破折号：主引擎空、副引擎"一"、
    # 后面紧跟的字和"一"能组成常用词（一妻多夫、一一对应、一个、一种）→ 不预填，出图看
    for s in sites:
        if s["class"] == "dash" and not s["primary"] and s["secondary"] == "一" and "】" in s["context"]:
            nxt = s["context"].split("】", 1)[1][:1]
            if nxt and nxt in YI_NEXT:
                s["class"] = "char"

    # ---- 切图 ----
    from PIL import Image, ImageDraw, ImageFont
    try: font = ImageFont.load_default(size=28)
    except TypeError: font = ImageFont.load_default()
    crops = []
    for k, s in enumerate(sites):
        s["n"] = k
        if s["class"] in PREFILL or s.get("auto"): continue
        img = os.path.join(render, s["page"] + ".png")
        bbs = locate(s["lines"], s["probe"])
        if not bbs or not os.path.exists(img): continue
        im = Image.open(img)
        parts = []
        for bb in bbs:   # 分歧跨行时是上下两行，竖着拼成一条
            x1, y1, x2, y2 = [int(v) for v in bb]
            y2 = min(y2, y1 + 400)
            box = (max(0, x1 - 20), max(0, y1 - 8), min(im.width, x2 + 20), min(im.height, y2 + 8))
            if box[2] <= box[0] or box[3] <= box[1]:
                sys.exit(f"{s['page']}: 框 {bb} 超出渲染图 {im.size}——两个引擎用的不是同一套渲染图？")
            parts.append(im.crop(box))
        c = parts[0] if len(parts) == 1 else Image.new("RGB", (max(p.width for p in parts), sum(p.height for p in parts)), "white")
        if len(parts) > 1:
            y = 0
            for p in parts: c.paste(p, (0, y)); y += p.height
        if c.width > 1300: c = c.resize((1300, int(c.height * 1300 / c.width)))
        crops.append((k, c))
    i = sheet = 0
    while i < len(crops):
        batch, h = [], 0
        while i < len(crops) and h + crops[i][1].height + 10 < 1800 and len(batch) < 14:
            batch.append(crops[i]); h += crops[i][1].height + 10; i += 1
        sh = Image.new("RGB", (1400, h + 10), "white"); d = ImageDraw.Draw(sh); y = 5
        for k, c in batch:
            d.text((4, y + 4), str(k), fill="red", font=font); sh.paste(c, (90, y))
            d.line((0, y + c.height + 4, 1400, y + c.height + 4), fill="#aaa"); y += c.height + 10
            sites[k]["sheet"] = sheet
        sh.save(os.path.join(out, "sheets", f"sheet_{sheet:03d}.png")); sheet += 1

    with open(os.path.join(out, "sites.tsv"), "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, delimiter="\t")
        w.writerow(COLS)
        for s in sites:
            w.writerow([s["n"], s["page"], s["class"], s["primary"], s["secondary"], s.get("sheet", ""), s["context"],
                        s.get("auto") or PREFILL.get(s["class"], ""), s["raw_start"], s["raw_end"], s["insert"], s["sha"]])
    from collections import Counter
    c = Counter(s["class"] for s in sites)
    print(f"{len(common)} 页，分歧 {len(sites)} 处: " + ", ".join(f"{k} {v}" for k, v in c.most_common()))
    print(f"已按类别预填 {sum(1 for s in sites if s['class'] in PREFILL)} 处（{'/'.join(PREFILL)}，主引擎对），"
          f"全书佐证自动裁决 {auto} 处；"
          f"需看图 {len(crops)} 处 → {sheet} 张审图板 {out}/sheets/，清单 {out}/sites.tsv")
    nodrop = sum(1 for s in sites if s["class"] == "drop" and s["raw_start"] == "")
    if nodrop: print(f"⚠️ {nodrop} 处漏段找不到插入位置，裁决为 secondary 也需手工补")
    open(os.path.join(out, "unaligned.txt"), "w").write("".join(f"{p}\t{r:.2f}\n" for p, r in unaligned))
    if unaligned:
        print(f"⚠️ {len(unaligned)} 页两引擎阅读顺序差异大（>5% 未对齐），短分歧可能漏报，建议整页看: "
              + " ".join(f"{p}({r:.0%})" for p, r in unaligned[:15]))


if __name__ == "__main__":
    main()
