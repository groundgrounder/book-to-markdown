#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""patch_cleaned.py <已清洗的旧 md> <新 OCR 逐页目录> <输出目录> [--pages A-B]
旧 md 已经做完整套后处理（标题层级、目录、脚注、callout），但当初的 OCR 丢了段、认错了字。
重新 OCR（双引擎 + 审图裁决）之后，不必把后处理重做一遍：以旧 md 为骨架，只把新 OCR 里
① 旧 md 整段没有的内容插回去，② 短的错字改过来，结构原样保留。

输出：
  <输出目录>/<书名>.md        打过补丁的 md。插入的段落包在 <!-- 补 pNNNN --> … <!-- /补 --> 里，
                              等排版那一步按周围格式（callout/脚注/表格）整理后再去掉标记
  <输出目录>/changes.tsv      每一处改动：类型、页、旧、新、上下文
  <输出目录>/skipped.tsv      没自动改的：标题行里的分歧、找不到插入位置的段落、疑似页眉页码/目录页
页码范围 --pages 用来跳过前后附件（版权页、CIP 等旧 md 有意删掉的页）。
--careful <unaligned.txt>（crosscheck.py 的输出）：这些页两引擎阅读顺序差太多，短分歧可能没进审图，
新 OCR 自己的错字还在 → 这些页只插段、不自动改字，改字全进 skipped.tsv。
--verify <副引擎目录> <sites.tsv>：改字只在有旁证时做——副引擎（PP）同一处也是这么读的，或者这一处
在审图里裁决过。都没有（典型：表格里 PP 对不上、整块记成 extra 的地方，VL 把原书"冗赘"读成"冗繁"）
→ 不改，进 skipped.tsv。强烈建议总是带上。
"""
import bisect, csv, difflib, glob, os, re, statistics, sys, unicodedata

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from crosscheck import uncovered, fuzzy_in  # noqa: E402

# 旧 md 里不是正文的标记：脚注引用/定义、callout 类型、HTML、图片、LaTeX 命令、实体、补丁标记
OLD_TAG = re.compile(r"\[\^[^\]\s]+\]:?|\[![A-Za-z]+\]|<!--.*?-->|<[^>]+>|!\[[^\]]*\]\([^)]*\)|\\[a-zA-Z]+|&#?\w+;", re.S)
NEW_TAG = re.compile(r"<[^>]+>|!\[[^\]]*\]\([^)]*\)|\\[a-zA-Z]+|&#?\w+;|^[ \t]*\d{1,3}[ \t]*$", re.M)   # 末项：页边原版页码
PUNCT_RUN = set("。，、；：！？…”’」』）)】〕.,;:!?\"' \t")   # 插入点两侧可整串替换的标点（不含换行、不含脚注标记）
FN_MARK = re.compile(r"^\s*(\$\s*\^\{[^}]*\}\s*\$|[①-⑳*]+)\s*$")


def norm_map(s, tag):
    skip = [False] * len(s)
    for m in tag.finditer(s):
        for i in range(m.start(), m.end()): skip[i] = True
    out, pos = [], []
    for i, ch in enumerate(s):
        if skip[i]: continue
        for c in unicodedata.normalize("NFKC", ch).lower():
            if unicodedata.category(c)[0] in "LN":
                out.append(c); pos.append(i)
    return "".join(out), pos


def load_verify(pp_root, sites_tsv):
    """页 → (副引擎整页归一化文本, 审图裁决过的"前3字+最终读法+后3字"集合)。"""
    import json
    from crosscheck import load_pages, body, norm
    out = {}
    for page, f in load_pages(pp_root).items():
        out[page] = (norm(body(json.load(open(f, encoding="utf-8")))), set())
    for r in csv.DictReader(open(sites_tsv, encoding="utf-8"), delimiter="\t"):
        d, ctx = (r["decision"] or "").strip(), r["context"]
        if not d or "【" not in ctx or r["page"] not in out: continue
        L, rest = ctx.split("【", 1); M, R = rest.split("】", 1)
        final = M if d == "primary" else r["insert"] if d == "secondary" else d[1:] if d.startswith("=") else None
        if final is None: continue
        out[r["page"]][1].add(norm(L)[-3:] + norm(final) + norm(R)[:3])
    return out


def clean_insert(t):
    """新 OCR 的原文 → 插进旧 md 的文字：VL 的 LaTeX 脚注标记还原成 ①，去掉首尾空白。"""
    t = re.sub(r"\$\s*\^\{([^}]*)\}\s*\$", r"\1", t)
    return t.strip()


def line_of(text, i):
    a = text.rfind("\n", 0, i) + 1
    b = text.find("\n", i)
    return text[a: b if b >= 0 else len(text)]


def main():
    a = sys.argv[1:]
    rng, careful, verify = None, set(), None
    if "--verify" in a:
        i = a.index("--verify"); verify = load_verify(a[i + 1], a[i + 2]); a = a[:i] + a[i + 3:]
    if "--careful" in a:
        i = a.index("--careful"); careful = {l.split()[0] for l in open(a[i + 1]) if l.strip()}; a = a[:i] + a[i + 2:]
    if "--pages" in a:
        i = a.index("--pages"); lo, hi = map(int, a[i + 1].split("-")); rng = (lo, hi); a = a[:i] + a[i + 2:]
    old_path, new_root, out = a
    os.makedirs(out, exist_ok=True)
    old = open(old_path, encoding="utf-8").read()
    pages = sorted(glob.glob(os.path.join(new_root, "**", "p[0-9][0-9][0-9][0-9].md"), recursive=True))
    edits, skipped, cursor, dashfix = [], [], 0, []

    # 预处理：PP 把破折号认成"一"（愉快一不愉快、种一属联想）。新 OCR 在两个汉字之间是破折号的地方，
    # 把旧 md 里同样两个字之间的"一"换成破折号。只换新 OCR 里确实出现过的"字—字"组合，不碰"统一""唯一"。
    pairs = set()
    for f in pages:
        for m in re.finditer(r"([一-鿿])\s*[—―－–~～-]{1,2}\s*([一-鿿])", open(f, encoding="utf-8").read()):
            pairs.add((m.group(1), m.group(2)))
    def _dash(m):
        if (m.group(1), m.group(2)) in pairs:
            dashfix.append(m.group(1) + "一" + m.group(2))
            return m.group(1) + "—"
        return m.group(0)
    old = re.sub(r"([一-鿿])一(?=([一-鿿]))", _dash, old)
    on, opos = norm_map(old, OLD_TAG)

    for f in pages:
        page = os.path.basename(f)[:-3]
        pno = int(page[1:]) + 1
        if rng and not (rng[0] <= pno <= rng[1]): continue
        raw = open(f, encoding="utf-8").read()
        nn, npos = norm_map(raw, NEW_TAG)
        if len(nn) < 20: continue
        # 定位：新页的 12 字片段在旧 md 里出现的位置，取中位数；从上一页附近往后找（两边页序一致）
        offs = []
        for i in range(0, len(nn) - 12, 20):
            seg = nn[i:i + 12]
            j = on.find(seg, max(0, cursor - 3000))
            if j < 0: j = on.find(seg)          # 游标前面也找：游标可能被上一页带偏了
            if j >= 0: offs.append(j - i)
        if len(offs) < 3:
            skipped.append(("unlocated", page, "", nn[:40], "这页在旧 md 里找不到（被整页删了？）")); continue
        o = int(statistics.median(offs))
        # 命中要扎堆才算定位成功：目录页的条目散落在全书各章标题处，中位数没有意义，
        # 拿它推游标会让后面所有页都找不到（家庭治疗概论首跑 350/431 页因此失败）
        near = sum(1 for x in offs if abs(x - o) < len(nn) + 1500) / len(offs)
        if near < 0.6:
            skipped.append(("unlocated", page, "", nn[:40], f"命中分散（{near:.0%}），多半是目录/索引页")); continue
        cursor = max(cursor, o)
        w0, w1 = max(0, o - 400), min(len(on), o + len(nn) + 400)

        # ① 整段缺失：新页里连续 ≥8 字在整本旧 md 都找不到（与顺序无关：旧 md 把脚注挪到章末也不算缺）
        drops = uncovered(nn, on, 8, 8)
        def _para_break(i):          # nn[i-1] 和 nn[i] 之间隔着原文空行
            return i <= 0 or i >= len(nn) or re.search(r"\n\s*\n", raw[npos[i - 1]:npos[i]])
        # 两段缺失之间只隔几个字（偶然和旧 md 某处对上的 8 字片段）→ 合成一段，否则碎段之间找不到唯一锚点
        merged = []
        for x, y in drops:
            if merged and x - merged[-1][1] <= 12: merged[-1] = (merged[-1][0], y)
            else: merged.append((x, y))
        # 再按"换行 + 脚注号"切开：正文末行和页底脚注常连在一起缺，合成一段插进去会把脚注塞进句子中间
        split = []
        for x, y in merged:
            cut = [x]
            for m in re.finditer(r"\n\s*(?=[①-⑳]|\$\s*\^\{)", raw[npos[x]:npos[y - 1] + 1]):   # 切点落在脚注号上
                k = next((i for i in range(x, y) if npos[i] >= npos[x] + m.end()), None)
                if k and k - cut[-1] >= 8 and y - k >= 8: cut.append(k)
            cut.append(y)
            split += [(cut[i], cut[i + 1]) for i in range(len(cut) - 1)]
        drops = split
        for x, y in drops:
            span = nn[x:y]
            digits = sum(c.isdigit() for c in span)
            if digits / len(span) > 0.6:
                skipped.append(("digits", page, "", span, "多半是目录页码/页眉，未插入")); continue
            if fuzzy_in(span, on[w0:w1], 0.6):
                skipped.append(("garbled", page, "", span, "旧 md 这附近有一段认得很烂的同内容，需人工替换")); continue
            r0, r1 = npos[x], npos[y - 1] + 1
            # 公式：VL 的 LaTeX 和旧 md 的公式图片对不上，插进去只会是一截 \mathrm{…} 碎片
            if "\\" in raw[r0:r1] or raw.count("$$", 0, r0) % 2 == 1:
                skipped.append(("formula", page, "", span, raw[r0:r1][:200])); continue
            # 脚注：补到原文这一行的行尾。脚注后半截常和书里别处的同书引文重合、不算"缺失"，只补前半截就成了残句
            if re.match(r"\s*(\$\s*\^\{[^}]*\}\s*\$|[①-⑳])", raw[r0:r1]):
                e = raw.find("\n", r1)
                r1 = e if e >= 0 else len(raw)
            ins = clean_insert(raw[r0:r1])
            # 前锚点、后锚点各找一个（缺失段之前/之后的一小段新文字，在旧 md 这一窗口里唯一出现）；
            # 都有而且指的不是同一处时信更长的那个（短锚点"自我心理学理论"容易配到别的句子）
            # 短锚点（<14 字）要再核一下锚点外侧：新 OCR 里锚点再往外 7 字，旧 md 里同一位置也得大体相同，
            # 否则锚点本身是"碰巧唯一"——锚点外侧那几个字也是缺失的一部分（uncovered 没认出来）
            def _ok(new_side, old_side):
                return not new_side or difflib.SequenceMatcher(None, new_side, old_side, autojunk=False).ratio() >= 0.5
            fa = fb = None
            for k in (14, 10, 7):
                c = nn[max(0, x - k):x]
                if len(c) >= 6 and on.count(c, w0, w1) == 1:
                    s0 = on.find(c, w0, w1)
                    if k < 14 and not _ok(nn[max(0, x - 14):x - k], on[max(0, s0 - (14 - k)):s0]): break
                    fa = (k, opos[s0 + len(c) - 1] + 1); break
            for k in (14, 10, 7):
                c = nn[y:y + k]
                if len(c) >= 6 and on.count(c, w0, w1) == 1:
                    e0 = on.find(c, w0, w1) + len(c)
                    if k < 14 and not _ok(nn[y + k:y + 14], on[e0:e0 + 14 - k]): break
                    fb = (k, opos[e0 - len(c)]); break
            if fa is None and fb is None:
                skipped.append(("noanchor", page, "", span, ins[:200])); continue
            # 前后锚点都有、旧 md 里两者之间却隔着文字：多半是短的那个碰巧在窗口里别处唯一（同段里的另一句）。
            # 有 14 字的就信它；两个都短 → 不猜，留给人看
            if fa and fb and max(fa[0], fb[0]) < 14 and not re.match(r"^[①-⑳*＊]|^\[\d+\]|^注[:：]", ins):
                ia, ib = bisect.bisect_left(opos, fa[1]), bisect.bisect_left(opos, fb[1])
                if ib - ia != 0:
                    skipped.append(("anchorconflict", page, "", span,
                                    f"前锚点后:{old[fa[1]:fa[1] + 20]!r} 后锚点前:{old[max(0, fb[1] - 20):fb[1]]!r} 补:{ins[:120]}"))
                    continue
            use_front = fb is None or (fa is not None and fa[0] >= fb[0])
            at = fa[1] if use_front else fb[1]
            # 标点归属：锚点只认字母数字，插入点两侧旧 md 原有的标点（"等。""领域）。"）会被留在补块的错误一侧、
            # 甚至自成一段。插入点处旧 md 的一串标点，如果和新 OCR 里"缺失段前的标点 + 缺失段后的标点"相同，
            # 就整串换成 前标点 + 补块 + 后标点
            gl = re.sub(r"\s", "", raw[npos[x - 1] + 1:r0]) if x else ""
            gr = re.sub(r"\s", "", raw[r1:npos[y]]) if y < len(nn) else ""
            gr = re.split(r"[①-⑳$^]", gr)[0]          # 页底脚注号之后的不算
            ra = rb = at
            if use_front:
                while rb < len(old) and old[rb] in PUNCT_RUN: rb += 1
            else:
                while ra > 0 and old[ra - 1] in PUNCT_RUN: ra -= 1
            run = re.sub(r"\s", "", old[ra:rb])
            NF = lambda s: unicodedata.normalize("NFKC", s)
            swap = bool(run) and NF(run) == NF(gl + gr)
            kind = ""
            if re.match(r"^[①-⑳*＊]|^\[\d+\]|^注[:：]", ins):
                # 页底脚注：锚点常落在跨页句子中间，挪到所在段落之后，排版时再转成 [^…] 格式
                pe = old.find("\n\n", at)
                ra = rb = at = pe if pe >= 0 else len(old)
                block, kind, swap = True, " 脚注", False
            else:
                # 独立成段只在新 OCR 里它前后都是空行、而且旧 md 插入点前面是句末时；
                # 页边的换行（VL 常在页首/页尾断行）不算——否则句中补的一行会把一句话切成三段
                pre_blank = _para_break(x) and x > 0
                post_blank = _para_break(y) and y < len(nn)
                before = re.sub(r"(\[\^[^\]]*\]|[①-⑳]|\s)+$", "", old[max(0, ra - 30):ra] + (gl if swap else ""))
                block = pre_blank and post_blank and (not before or before[-1] in "。！？…”’」』：:.!?）)")
            body = f"<!-- 补 {page}{kind} -->{ins}<!-- /补 -->"
            if block: body = f"\n\n<!-- 补 {page}{kind} -->\n{ins}\n<!-- /补 -->\n\n"
            if swap:
                # 旧 md 这串标点里的换行（段落边界）留在后标点之后
                tail = re.search(r"\s*$", old[ra:rb]).group(0)
                text = gl + body + gr + tail
                edits.append((ra, rb, text, "insert", page, old[ra:rb], span))
            else:
                edits.append((at, at, body, "insert", page, "", span))

        # ② 短分歧：去掉整段缺失后，新页与旧 md 对应窗口逐字比
        keep = [True] * len(nn)
        for x, y in drops:
            for i in range(x, y): keep[i] = False
        idx = [i for i in range(len(nn)) if keep[i]]
        nm = "".join(nn[i] for i in idx)
        win = on[w0:w1]
        sm = difflib.SequenceMatcher(None, win, nm, autojunk=False)
        blocks = [b for b in sm.get_matching_blocks() if b.size >= 8]
        if not blocks: continue
        lo_a, hi_a = blocks[0].a, blocks[-1].a + blocks[-1].size   # 只在两边真正对齐的范围内改
        ops = sm.get_opcodes()
        for oi, (tag, i1, i2, j1, j2) in enumerate(ops):
            if tag == "equal" or i1 < lo_a or i2 > hi_a or max(i2 - i1, j2 - j1) > 6: continue
            # 局部对齐要可信：分歧两侧各有 ≥10 字完全一致。否则多半是窗口对错了地方
            # （页尾重复、表格单元顺序不同），"改字"会把旧 md 的正确文字换成别处的字
            prev_eq = ops[oi - 1][2] - ops[oi - 1][1] if oi > 0 and ops[oi - 1][0] == "equal" else 0
            next_eq = ops[oi + 1][2] - ops[oi + 1][1] if oi + 1 < len(ops) and ops[oi + 1][0] == "equal" else 0
            old_s, new_s = win[i1:i2], nm[j1:j2]
            if min(prev_eq, next_eq) < 10:
                # 两处错字相距 <10 字（"泪丧，他担心这种泪丧"）时两处都会被挡掉。有旁证（副引擎同读、或审图裁决过）
                # 而且两侧各 ≥4 字一致就照改；否则记下来，不再静默跳过
                key = nm[max(0, j1 - 3):j1] + new_s + nm[j2:j2 + 3]
                pp_text, decided = verify.get(page, ("", set())) if verify is not None else ("", set())
                if not (min(prev_eq, next_eq) >= 4 and (key in pp_text or key in decided)):
                    if min(prev_eq, next_eq) >= 4:
                        skipped.append(("weakalign", page, old_s, new_s, (win[max(0, i1 - 8):i1] + "【" + old_s + "→" + new_s + "】" + win[i2:i2 + 8])))
                    continue
            ga, gb = w0 + i1, w0 + i2
            if gb > ga: ra, rb = opos[ga], opos[gb - 1] + 1
            else: ra = rb = opos[ga - 1] + 1 if ga > 0 else 0
            nr = raw[npos[idx[j1]]: npos[idx[j2 - 1]] + 1] if j2 > j1 else ""
            # 脚注标记：旧 md 用 [^ch5-1]，新 OCR 用 ① → 不是错字
            if (nr and FN_MARK.match(nr)) or (not new_s and re.fullmatch(r"[\d]+", old_s) and "[^" in old[max(0, ra - 12): rb + 12]):
                continue
            if not nr and "[^" in old[max(0, ra - 3): rb + 3]:
                continue
            # 新 OCR 里是上标（$ ^{1} $）：不能当正文字符插进旧 md（会变成"悲伤1和"）
            if nr and "^{" in raw[max(0, npos[idx[j1]] - 6): npos[idx[j1]]]:
                continue
            ln = line_of(old, ra)
            if "<td" in ln and max(len(old_s), len(new_s)) > 2:
                skipped.append(("table", page, old[ra:rb], nr, ln.strip()[:80])); continue   # 表格单元顺序两边可能不同
            if ln.lstrip().startswith("#") or re.match(r"^\s*-\s", ln) and ra < len(old) * 0.05:
                skipped.append(("heading", page, old[ra:rb], nr, ln.strip()[:80])); continue
            # 新 OCR 多出一串数字、旧 md 两边不是数字 → 页边原版页码（VL 有时把它接在句末），不插
            if not old_s and re.fullmatch(r"\d{1,4}", new_s) and not re.search(r"\d", old[max(0, ra - 1):ra + 1]):
                skipped.append(("pagenum", page, "", nr, line_of(old, ra).strip()[:80])); continue
            # 紧跟在完整年份后面（"Wachtel,1986" + "18" + ")"）：也是页边页码粘进了引文
            if not old_s and re.fullmatch(r"\d{1,3}", new_s) and re.search(r"(1[89]|20)\d\d[a-z]?$", old[max(0, ra - 6):ra]):
                skipped.append(("pagenum", page, "", nr, line_of(old, ra).strip()[:80])); continue
            # 插进一串数字里面（"198"+"1"+"1)"、"3"+"263"+"个"）：数字串内部的增删要么是页边页码粘连、要么是年份错位，不自动改
            if not old_s and new_s.isdigit() and re.search(r"\d$", old[max(0, ra - 1):ra]):
                skipped.append(("digitrun", page, "", nr, line_of(old, ra).strip()[:80])); continue
            # 插进来的是一个完整的词组（≥3 字、新 OCR 里它前后有标点或换行）而旧 md 这里是句末：多半是
            # 表格单元/小标题错位接到了正文后面（"关系变化"+"界限渗透性"），不插
            if not old_s and len(new_s) >= 3 and re.match(r"\s*[。，；：）)]|\s*\n", old[rb:rb + 2]):
                skipped.append(("cell", page, "", nr, line_of(old, ra).strip()[:80])); continue
            # 破折号：旧 md 这里已经是破折号了，新 OCR 把它认成"一"→ 别再插"一"
            if not old_s and new_s == "一" and re.search(r"[—―－-]", old[max(0, ra - 1):ra + 3]):
                continue
            # 新 OCR 一侧缺的是这些字、旧 md 是逗号分隔的数字列表（索引页）→ 不碰
            if re.search(r"\d,\s*$", old[max(0, ra - 4):ra]) and not old_s.isdigit():
                continue
            if old_s.isdigit() and not new_s:
                # 两侧都是汉字的 2–3 位数字 = 旧 md 里混进正文的页边原版页码（"家庭界 228 限"），删；
                # 其余（脚注号 ②→2、索引页的页码）别删
                around = old[max(0, ra - 2):ra].strip()[-1:] + old[rb:rb + 2].strip()[:1]
                if not (len(old_s) >= 2 and len(around) == 2 and all("一" <= ch <= "鿿" for ch in around)):
                    continue
            if old_s and not new_s:
                # 旧 md 多出来的字：新 OCR 在同一位置若是标点（破折号被认成"一"），换成那个标点；
                # 多字删除（不是页码）风险大，留给人看
                if 0 < j1 < len(idx):
                    gap = raw[npos[idx[j1 - 1]] + 1: npos[idx[j1]]].strip()
                    if 0 < len(gap) <= 3 and not re.search(r"[A-Za-z0-9一-鿿]", gap):
                        nr = gap
                # 夹带了别的标点（"）——"）→ 只取破折号，别把括号也带进去
                if old_s == "一" and nr and re.search(r"[—―－-]", nr):
                    nr = re.sub(r"[^—―－-]", "", nr)
                if len(old_s) > 1 and not old_s.isdigit() and not nr:
                    skipped.append(("delete", page, old[ra:rb], "", line_of(old, ra).strip()[:80])); continue
            if page in careful:
                skipped.append(("careful", page, old[ra:rb], nr, line_of(old, ra).strip()[:80])); continue
            if verify is not None:
                key = nm[max(0, j1 - 3):j1] + new_s + nm[j2:j2 + 3]
                pp_text, decided = verify.get(page, ("", set()))
                if key not in pp_text and key not in decided:
                    skipped.append(("unverified", page, old[ra:rb], nr, line_of(old, ra).strip()[:80])); continue
            edits.append((ra, rb, nr, "sub", page, old[ra:rb], new_s))

    # "挪字"：同一页里一处删掉 X、另一处插入同样的 X（≥2 字）= 对齐窗口把重复出现的文字（图注和正文都有
    # "凯莉·N.柯克西"）配错了位置，两条都不是真错字 → 都丢掉
    subs = [e for e in edits if e[3] == "sub"]
    moved = set()
    letters = lambda x: re.sub(r"[^\w]", "", x)
    for i, e in enumerate(subs):
        for f in subs[i + 1:]:
            if e[4] != f[4]: continue
            for d, g in ((e, f), (f, e)):   # d 删掉一段字（换成的只剩标点）、g 在别处插入同一段字
                if len(letters(d[5])) >= 2 and not letters(d[2]) and not g[5] and letters(g[2]) == letters(d[5]):
                    moved |= {id(e), id(f)}
    for e in edits:
        if id(e) in moved: skipped.append(("moved", e[4], e[5], e[2], ""))
    edits = [e for e in edits if id(e) not in moved]
    # 从后往前改；重叠的只认第一条
    edits.sort(key=lambda e: (e[0], e[1]))
    text, last, applied = old, len(old) + 1, []
    for e in reversed(edits):
        ra, rb, rep = e[0], e[1], e[2]
        if rb > last: continue
        ctx = (old[max(0, ra - 12):ra] + "【" + old[ra:rb] + "→" + (rep if e[3] == "sub" else "＋插入") + "】" + old[rb:rb + 12]).replace("\n", "⏎")
        text = text[:ra] + rep + text[rb:]; last = ra
        applied.append((e[3], e[4], e[5], e[2] if e[3] == "sub" else e[6], ctx))
    applied.reverse()

    name = os.path.basename(old_path)
    open(os.path.join(out, name), "w", encoding="utf-8").write(text)
    with open(os.path.join(out, "changes.tsv"), "w", encoding="utf-8", newline="") as fo:
        w = csv.writer(fo, delimiter="\t"); w.writerow(["type", "page", "old", "new", "context"]); w.writerows(applied)
    with open(os.path.join(out, "skipped.tsv"), "w", encoding="utf-8", newline="") as fo:
        w = csv.writer(fo, delimiter="\t"); w.writerow(["reason", "page", "old", "new", "note"]); w.writerows(skipped)
    ni = sum(1 for x in applied if x[0] == "insert")
    nc = sum(len(x[3]) for x in applied if x[0] == "insert")
    print(f"{len(pages)} 页 → 破折号还原 {len(dashfix)} 处，插入 {ni} 段 / {nc} 字，改字 {len(applied) - ni} 处；"
          f"未自动处理 {len(skipped)} 处 → {out}/")
    from collections import Counter
    if skipped: print("  未处理: " + ", ".join(f"{k} {v}" for k, v in Counter(s[0] for s in skipped).most_common()))


if __name__ == "__main__":
    main()
