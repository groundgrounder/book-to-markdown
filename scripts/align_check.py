#!/usr/bin/env python3
"""逐页局部对齐：成品 md 和审过的主引擎逐页结果比，找"这一页的这个位置少了/多了/不一样"。

uncovered（新页的 8 字片段在整本旧 md 里找不找得到）有个洞：一句话丢了，但它的每个 8 字片段
碰巧在书里别处出现过（"埃里克森的自我心理学理论"），就被当成"已有"。这里按页定位后，只拿 ≥8 字的
一致片段当锚点逐段对齐，锚点之间的每个缺口都是一处分歧。

  missing  主引擎这一页有、成品 md 对应位置没有（≥--min 字）。副引擎（PP）同页也有这段 → pp=1
  moved    成品 md 有、主引擎这一页对应位置没有，但这段字在主引擎本页/邻页别的位置有
           → 多半是插错地方的补块（正确位置会同时报一条 missing）。给了 --old 时旧 md 原有的不报
  extra    同上，但主引擎本页和邻页都没有（旧 md 的残留乱码、页眉、表格行序不同）
整段在成品 md 别处（大体）原样出现的（脚注挪到章末、图注挪位）不报。
--small：另外统计 <min 字的短分歧，按副引擎投票分成 引擎一致≠成品 / 成品=副引擎 / 都不像。

用法: align_check.py <成品.md> <主引擎目录> [<副引擎目录>] [--min 6] [--pages A-B] [--old 旧.md] [--small]
输出 TSV（stdout）: page kind line pp text left right
"""
import argparse, difflib, glob, os, re, statistics, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from patch_cleaned import norm_map, OLD_TAG, NEW_TAG  # noqa: E402


def pieces(raw, pos, x, y, mn):
    """标准化下标区间 [x,y) 按原文里的空行切成几段，丢掉短于 mn 的"""
    out, s = [], x
    for i in range(x + 1, y):
        if re.search(r"\n\s*\n", raw[pos[i - 1]:pos[i]]):
            out.append((s, i)); s = i
    out.append((s, y))
    return [(p, q) for p, q in out if q - p >= mn]


def elsewhere(seg, fn):
    """seg 在 fn 别处（大体）原样出现：首/尾 10 字当锚点，对上后整段相似度 ≥0.85。
    旧 md 把脚注挪到章末时常顺手改过一两个字，要求逐字相同会把它们全报成缺失"""
    if seg in fn: return True
    if len(seg) < 16: return False
    for key, back in ((seg[:10], False), (seg[-10:], True)):
        i = fn.find(key)
        while i >= 0:
            s = max(0, i + 10 - len(seg) - 4) if back else i
            if difflib.SequenceMatcher(None, seg, fn[s:s + len(seg) + 4], autojunk=False).ratio() >= 0.85:
                return True
            i = fn.find(key, i + 1)
    return False


class Book:
    def __init__(self, md_path, vl_root, pp_root=None):
        self.md = open(md_path, encoding="utf-8").read()
        self.fn, self.fpos = norm_map(self.md, OLD_TAG)
        self.files = sorted(glob.glob(os.path.join(vl_root, "pages", "p*", "p[0-9][0-9][0-9][0-9].md")))
        self.order = [os.path.basename(f)[:-3] for f in self.files]
        self.vraw = {p: open(f, encoding="utf-8").read() for p, f in zip(self.order, self.files)}
        self.vl = {p: norm_map(t, NEW_TAG) for p, t in self.vraw.items()}
        self.pp = {}
        if pp_root:
            for f in glob.glob(os.path.join(pp_root, "pages", "p*", "p[0-9][0-9][0-9][0-9].md")):
                self.pp[os.path.basename(f)[:-3]] = norm_map(open(f, encoding="utf-8").read(), NEW_TAG)[0]

    def line(self, i):
        return self.md.count("\n", 0, self.fpos[min(i, len(self.fpos) - 1)]) + 1

    def scan(self, rng=None):
        """逐页 yield (page, k, gaps)；gap = (fa, fb, va, vb)：成品 fn[fa:fb] 对应主引擎 nn[va:vb]（整本 fn 下标）。
        页首/页尾缺口只有主引擎一侧（成品那侧是锚点外的别页内容，不算）"""
        fn, cursor = self.fn, 0
        for k, page in enumerate(self.order):
            if rng and not (rng[0] <= int(page[1:]) + 1 <= rng[1]): continue
            nn = self.vl[page][0]
            if len(nn) < 20: continue
            offs = []
            for i in range(0, len(nn) - 12, 20):
                j = fn.find(nn[i:i + 12], max(0, cursor - 3000))
                if j < 0: j = fn.find(nn[i:i + 12])
                if j >= 0: offs.append(j - i)
            if len(offs) < 3: continue
            o = int(statistics.median(offs))
            if sum(1 for x in offs if abs(x - o) < len(nn) + 1500) / len(offs) < 0.6: continue
            cursor = max(cursor, o)
            w0, w1 = max(0, o - 400), min(len(fn), o + len(nn) + 400)
            sm = difflib.SequenceMatcher(None, fn[w0:w1], nn, autojunk=False)
            # 只拿 ≥8 字的匹配当锚点；锚点之间的零碎巧合匹配（"当然""理论"）会把一个缺口切碎、藏起来
            anc = [b for b in sm.get_matching_blocks() if b.size >= 8]
            if not anc: continue
            g = [(w0 + anc[0].a, w0 + anc[0].a, 0, anc[0].b)]
            g += [(w0 + x.a + x.size, w0 + y.a, x.b + x.size, y.b) for x, y in zip(anc, anc[1:])]
            e = w0 + anc[-1].a + anc[-1].size
            g.append((e, e, anc[-1].b + anc[-1].size, len(nn)))
            yield page, k, [x for x in g if x[1] > x[0] or x[3] > x[2]]


def vote(bk, page, fa, fb, va, vb):
    """短分歧的副引擎投票：'v' 副引擎同主引擎、'f' 副引擎同成品、'' 都不像或都像"""
    P = bk.pp.get(page)
    if P is None: return ""
    fn, nn = bk.fn, bk.vl[page][0]
    L, R = fn[max(0, fa - 4):fa], fn[fb:fb + 4]
    v, f = (L + nn[va:vb] + R) in P, (L + fn[fa:fb] + R) in P
    return "v" if v and not f else "f" if f and not v else ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("md"); ap.add_argument("vl"); ap.add_argument("pp", nargs="?")
    ap.add_argument("--min", type=int, default=6)
    ap.add_argument("--pages")
    ap.add_argument("--old", help="补丁前的旧 md：moved 只报旧 md 里没有的（补块），旧 md 自己的脚注位置不算")
    ap.add_argument("--small", action="store_true")
    a = ap.parse_args()
    rng = tuple(int(x) for x in a.pages.split("-")) if a.pages else None
    bk = Book(a.md, a.vl, a.pp)
    fn, md = bk.fn, bk.md
    on = norm_map(open(a.old, encoding="utf-8").read(), OLD_TAG)[0] if a.old else ""
    print("page\tkind\tline\tpp\ttext\tleft\tright")
    n_miss = n_extra = 0
    small = {"v": 0, "f": 0, "": 0}
    for page, k, gaps in bk.scan(rng):
        nn, vpos = bk.vl[page]
        nb = "".join(bk.vl[p][0] for p in bk.order[max(0, k - 1):k + 2])   # 前后页：判断 extra 是不是本来就在邻页
        for fa, fb, va, vb in gaps:
            if max(fb - fa, vb - va) < a.min:
                if a.small and fb > fa or a.small and va > 0 and vb < len(nn):
                    small[vote(bk, page, fa, fb, va, vb)] += 1
                continue
            # 主引擎这边缺口按原文空行切开：页底脚注和正文是两段，脚注挪到章末不算缺
            for x, y in pieces(bk.vraw[page], vpos, va, vb, a.min):
                seg = nn[x:y]
                if elsewhere(seg, fn): continue
                has_pp = int(page in bk.pp and seg in bk.pp[page])
                print(f"{page}\tmissing\t{bk.line(fa)}\t{has_pp}\t{seg}\t{fn[max(0, fa - 12):fa]}\t{fn[fa:fa + 12]}")
                n_miss += 1
            for x, y in pieces(md, bk.fpos, fa, fb, a.min):
                seg = fn[x:y]
                if len(seg) >= 12 and fn.count(seg) > 1: continue        # 书里重复出现的整段（图注/引文）
                kind = "moved" if seg in nb else "extra"                 # moved：字是这页的，位置不对
                if kind == "moved" and on and seg in on: continue        # 旧 md 原本就这么排（脚注位置）
                print(f"{page}\t{kind}\t{bk.line(x)}\t\t{seg}\t{fn[max(0, x - 12):x]}\t{fn[y:y + 12]}")
                n_extra += 1
    print(f"# missing={n_miss} extra/moved={n_extra}", file=sys.stderr)
    if a.small:
        print(f"# 短分歧（<{a.min} 字）：副引擎同主引擎≠成品 {small['v']}，副引擎同成品 {small['f']}，"
              f"说不清 {small['']}", file=sys.stderr)


if __name__ == "__main__":
    main()
