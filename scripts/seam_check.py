#!/usr/bin/env python3
"""接缝检查：补丁后的 md 里，补块有没有插错位置、插残缺。

缺字检查（uncovered / 金标准）只看"该有的字有没有"，看不出这些：
  punct   段首是标点、旧 md 没有这段 → 补块插在了句末标点前面，标点被挤成单独一段
  seam    段内某段文字在旧 md 和两个引擎（整本按页序连起来）里都找不到 → 行内补丁接错了地方
  open    段落在句子中间断开（结尾没有句末标点），旧 md 里这个段尾不存在 → 补块把一个句子截成两半
  fnote   补进来的脚注是 VL 某条脚注的前一截（后半截恰好和旧 md 别处的同书引文重合，被当成"已有"）
  latex   段里有 LaTeX 命令却没有成对的 $ → 公式碎片
  dash    "字—字"/"字一字"和主引擎读法相反：破折号预处理把"一妻多夫""一一对应"的"一"换成了"—"，
          或者反过来。只看主引擎（PP 一律读成"一"）。VL 自己也会把破折号读成"一"（我—你、存在—人本主义），
          所以这一类只是候选，要逐条看（必要时看图）再改
窗口比较前去掉空白、markdown/HTML 标记、脚注号、LaTeX 命令，全半角标点统一。

用法: seam_check.py <新.md> <旧.md> <主引擎目录> [<副引擎目录>] [-n 12]
输出: 类别<TAB>行号<TAB>内容[<TAB>建议]；最后一行是各类计数
"""
import argparse, collections, glob, re

P = str.maketrans({"（": "(", "）": ")", "，": ",", "：": ":", "；": ";", "！": "!", "？": "?",
                   "“": '"', "”": '"', "‘": "'", "’": "'", "—": "-", "―": "-", "–": "-",
                   "．": ".", "［": "[", "］": "]", "〔": "[", "〕": "]", "　": " "})
STRIP = re.compile(r"<!--.*?-->|<[^>]+>|\[\^[^\]]*\]:?|[①-⑳]|\\[a-zA-Z]+|[{}_^$*#>|`~]|\s", re.S)
PUN0 = "：，。；、）！？”』」"
END = tuple("。！？…”’）)」』：；:;.!?")
SKIP = re.compile(r"^(#|<|\||!\[|\$\$|\[\^|[-*+] |\d+\.\s|[①-⑳]|图\s*\d|表\s*\d|注[:：])")


def norm(s):
    return STRIP.sub("", s).translate(P)


def grams(s, n):
    return {s[i:i + n] for i in range(len(s) - n + 1)}


def paras(text):
    """(起始行号, 段落文字)；空行分段"""
    out, buf, start = [], [], 0
    for i, ln in enumerate(text.split("\n")):
        if ln.strip():
            if not buf: start = i + 1
            buf.append(ln)
        elif buf:
            out.append((start, "\n".join(buf))); buf = []
    if buf: out.append((start, "\n".join(buf)))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("new"); ap.add_argument("old"); ap.add_argument("roots", nargs="+")
    ap.add_argument("-n", type=int, default=12)
    a = ap.parse_args()
    n = a.n
    old = open(a.old, encoding="utf-8").read()
    old_paras = paras(old)
    old_set = {p for _, p in old_paras}
    old_tails = {norm(p)[-n:] for _, p in old_paras}
    ok = grams(norm(old), n)
    vl_fn, vl_txt = [], ""                               # 主引擎里的脚注行，查截断用；主引擎全文，查破折号
    for k, r in enumerate(a.roots):
        pages = [open(f, encoding="utf-8").read() for f in sorted(glob.glob(f"{r}/pages/p*/p*.md"))]
        ok |= grams("".join(norm(t) for t in pages), n)
        # 去掉页底脚注再连一遍：跨页的句子中间隔着上一页的脚注，正文接起来以后也算见过
        ok |= grams("".join(norm(x) for t in pages for x in re.split(r"\n\s*\n", t)
                            if not re.match(r"\s*(\$\s*\^\{|[①-⑳])", x)), n)
        if k == 0:
            vl_txt = "".join(norm(t) for t in pages)
            vl_fn = [ln.strip() for t in pages for ln in t.split("\n") if re.match(r"\s*[①-⑳]", ln)]
    vl_fn_n = [(norm(x), x) for x in vl_fn]

    out = []
    for ln, p in paras(open(a.new, encoding="utf-8").read()):
        if p in old_set:
            continue
        first = p.lstrip()
        if first[0] in PUN0:
            out.append(("punct", ln, p[:60]))
        if re.search(r"\\[a-zA-Z]+", p) and p.count("$") % 2 == 1 or re.search(r"\\[a-zA-Z]+\{", p) and "$" not in p:
            out.append(("latex", ln, p[:80]))
        if re.match(r"[①-⑳]", first) and "\n" not in p:
            pn = norm(p)
            longer = [x for xn, x in vl_fn_n if xn.startswith(pn) and len(xn) >= len(pn) + 4]
            if pn and longer:
                out.append(("fnote", ln, p, longer[0]))
        for m in re.finditer(r"(?<=[一-鿿])([—―]{1,2}|一)(?=[一-鿿])", p):
            L, R = norm(p[max(0, m.start() - 4):m.start()])[-3:], norm(p[m.end():m.end() + 4])[:3]
            if len(L) < 3 or len(R) < 3: continue
            as_dash, as_yi = (L + "-" in vl_txt and L + "-" + R in vl_txt), (L + "一" + R) in vl_txt
            if m.group(1) == "一" and as_dash and not as_yi:
                out.append(("dash", ln, p[max(0, m.start() - 6):m.end() + 6], "一→—"))
            elif m.group(1) != "一" and as_yi and not (L + "-" + R) in vl_txt and (L + R) not in vl_txt:
                out.append(("dash", ln, p[max(0, m.start() - 6):m.end() + 6], "—→一"))
        if not SKIP.match(first):
            pn = norm(p)
            if len(pn) >= 20 and not p.rstrip().endswith(END) and pn[-n:] not in old_tails:
                out.append(("open", ln, "…" + p.rstrip()[-40:]))
            bad = [pn[i:i + n] not in ok for i in range(len(pn) - n + 1)]
            i = 0
            while i < len(bad):
                if bad[i]:
                    j = i
                    while j + 1 < len(bad) and bad[j + 1]: j += 1
                    out.append(("seam", ln, pn[max(0, i - 4): j + n + 4])); i = j + 1
                else:
                    i += 1
    for r in out:
        print("\t".join(str(x) for x in r))
    c = collections.Counter(r[0] for r in out)
    print("# " + "  ".join(f"{k}={c[k]}" for k in ("punct", "open", "seam", "fnote", "latex", "dash")), flush=True)


if __name__ == "__main__":
    main()
