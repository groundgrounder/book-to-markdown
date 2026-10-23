#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fidelity_diff.py <clean.md> <raw.md> — 清洗后的内容守恒校验(硬门禁)

把两个文件切成块(空行分隔)并归一化(去页锚点/标题符/引用符/列表符/HTML标签/目录点线,
全半角括号与直弯引号统一), 对块序列做 diff:

  相等块               -> 通过
  删除块 文本藏在对方某块内 -> 段落接合/块移动, 通过
  删除块 相似度>=0.75    -> 疑似改写(括号/引号/目录规范化), 列出待眼检
  删除块 无痕           -> 疑似丢失, 硬失败
  新增块 无痕           -> 警告(格式转换常产生新块), 列出待眼检

并统计双侧: 字数(去空白)/表格数/图片引用数/块数。
退出码: 0 = 守恒; 1 = 存在无痕删除, 或表格/图片引用数不一致。
选项: --skip-table-count / --skip-img-count (跨页续表合并等已知差异时眼检后放行)
用法: fidelity_diff.py <清洗后.md> <原始.md> [--skip-table-count] [--skip-img-count]
"""
import difflib, re, sys

FN_MARK = re.compile(r"[\u2460-\u2473]|\[\^[^\]]+\]")   # ①②③ 与 GFM 脚注引用/定义
IMG = re.compile(r"<img[\s>]|!\[[^\]]*\]\(", re.I)
TAB = re.compile(r"<table[\s>]", re.I)
TRANS = str.maketrans({"（": "(", "）": ")", "［": "[", "］": "]", "｛": "{", "｝": "}",
                       "“": '"', "”": '"', "‘": "'", "’": "'"})


def blocks(t):
    return [b.strip() for b in re.split(r"\n\s*\n", t) if b.strip()]


def norm(b):
    out = []
    for line in b.split("\n"):
        s = line.strip()
        s = re.sub(r"<!--\s*第\d+页\s*-->", "", s)      # 页锚点
        # 标题里的页码前缀 ("#### 195 情绪阻断" → "#### 情绪阻断"): 已批准的清理动作,
        # 只在标题行生效, 正文/表格里的数字不受影响
        s = re.sub(r"^(#{1,6})\s+\d{1,4}\s+(?=\S)", r"\1 ", s)
        s = re.sub(r"^#{1,6}\s+", "", s)                # 标题符
        s = re.sub(r"^>\s*\[!\w+\][-+]?\s*", "", s)     # callout 标记, 保留其后的标题文字
        s = re.sub(r"^>\s?", "", s)                     # 引用符
        s = re.sub(r"^\s*[-*+]\s+", "", s)              # 列表符
        s = re.sub(r"<[^>]+>", "", s)                   # HTML 标签
        s = s.translate(TRANS)                          # 全半角括号/直弯引号统一
        s = re.sub(r"^[—\-]{3,}$", "", s)               # 独立分隔线/脚注分隔线
        s = re.sub(r"\s+", "", s)                       # 去空白
        if s:
            out.append(s)
    return "\n".join(out)


def is_table(b):
    if TAB.search(b):
        return True
    lines = [l.strip() for l in b.split("\n") if l.strip()]
    return sum(1 for l in lines if l.startswith("|")) >= 2



def _cjk_near(t, i, j):
    """[i,j) 是一个候选页码片段。认为是「粘在正文里的页码」的条件:
    至少一侧紧邻汉字, 或该片段正好贴着块的首/尾 (页码被切在行尾的情况, 如
    「普罗卡斯卡和诺克罗斯（Prochaska&126」—— 左侧是 & 而非汉字)。
    """
    if i == 0 or j >= len(t):
        return True
    left = t[i - 1] if i > 0 else ""
    right = t[j] if j < len(t) else ""
    return bool(re.match(r"[\u4e00-\u9fff]", left or " ")) or bool(re.match(r"[\u4e00-\u9fff]", right or " "))


def best_ratio(t, pool):
    return max((difflib.SequenceMatcher(None, t, p).ratio() for p in pool), default=0.0)


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    clean, raw = args[0], args[1]
    skip_tab, skip_img = "--skip-table-count" in sys.argv, "--skip-img-count" in sys.argv
    # --allow-regex="PAT" (可重复): 已申报的删除 (页眉/页码/水印等噪音)。
    # 命中者归入「已申报删除」并逐条列出; 不计入无痕删除。正文段落永远不该命中这里。
    allow_pats = [v.split("=", 1)[1] for v in sys.argv[1:] if v.startswith("--allow-regex=")]
    ct = open(clean, encoding="utf-8").read()
    rt = open(raw, encoding="utf-8").read()
    cb, rb = blocks(ct), blocks(rt)
    cn, rn = [norm(b) for b in cb], [norm(b) for b in rb]
    cjoin, rjoin = "\n".join(cn), "\n".join(rn)

    cn_fn = [FN_MARK.sub("", x) for x in cn]
    cjoin_fn = "\n".join(cn_fn)

    joined, rewrite, lost, new_, allowed = [], [], [], [], []
    allow_res = [re.compile(p) for p in allow_pats]

    def classify(i):
        t = rn[i]
        if t in cjoin:
            joined.append(i)
        elif any(r.search(t) for r in allow_res):
            allowed.append(i)          # 已申报的删除 (标注/页眉/页码噪音), 逐条仍会列出
        elif best_ratio(t, cn) >= 0.75:
            rewrite.append(i)
        elif folio_stripped_match(t):
            joined.append(i)           # 断页接合处剥离了正文里粘着的页码
        elif fn_stripped_match(t):
            joined.append(i)           # 脚注标记 ①→[^ch5-4] 转换, 文字未丢
        else:
            lost.append(i)

    def fn_stripped_match(t):
        """raw 块里的脚注标记 ①②③ 被转成 GFM [^chN-x] 后, 块内容不再逐字相等, 且块可能
        同时被并合进长段落 → 相似度也上不去。两侧都去掉脚注标记后再比一次。"""
        a = FN_MARK.sub("", t)
        if a == t:
            return False
        return a in cjoin_fn or best_ratio(a, cn_fn) >= 0.75

    def folio_stripped_match(t):
        """raw 块里粘在正文中的页码 (如 「…更喜460」) 会让并合后的块既不相等、相似度也掉到
        0.75 以下。剥掉这类孤立的 2-4 位数字后再比一次: 命中即视为「并合+剥页码」,
        与标题页码前缀的处理同一口径 (正文内容没有被删, 删的只是页码)。

        页码可能粘在真实数字旁边 (「有3263个主要步骤」= 正文"有3个" + 页码263),
        所以对每个数字串枚举所有长 2-4 的连续子串删除方案, 逐个试。
        """
        variants = set()
        for run in re.finditer(r"\d+", t):
            s0 = run.start()
            for ln in range(2, 5):
                for off in range(0, len(run.group()) - ln + 1):
                    if not _cjk_near(t, s0 + off, s0 + off + ln):
                        continue
                    variants.add(t[:s0 + off] + t[s0 + off + ln:])
        for s in variants:
            if s in cjoin or best_ratio(s, cn) >= 0.75:
                return True
        return False

    sm = difflib.SequenceMatcher(None, rn, cn, autojunk=False)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            continue
        if tag == "delete":
            for i in range(i1, i2):
                if rn[i]:
                    classify(i)
        elif tag == "insert":
            for j in range(j1, j2):
                t = cn[j]
                if not t:
                    continue
                if t not in rjoin and best_ratio(t, rn) < 0.75:
                    new_.append(j)
        else:  # replace
            for i in range(i1, i2):
                if rn[i]:
                    classify(i)
            for j in range(j1, j2):
                t = cn[j]
                if not t:
                    continue
                if t not in rjoin and best_ratio(t, rn) < 0.75:
                    new_.append(j)

    def stats(t, bs):
        return dict(chars=len(re.sub(r"\s+", "", t)),
                    tables=sum(1 for b in bs if is_table(b)),
                    imgs=len(IMG.findall(t)), blocks=len(bs))

    rs, cs = stats(rt, rb), stats(ct, cb)
    print(f"字数(去空白): {rs['chars']} -> {cs['chars']} (差 {cs['chars']-rs['chars']:+d})")
    print(f"表格: {rs['tables']} -> {cs['tables']}" + ("  ⚠️" if rs['tables'] != cs['tables'] else ""))
    print(f"图片引用: {rs['imgs']} -> {cs['imgs']}" + ("  ⚠️" if rs['imgs'] != cs['imgs'] else ""))
    print(f"块: {rs['blocks']} -> {cs['blocks']}")
    print(f"已并入(接合/移动): {len(joined)}  疑似改写: {len(rewrite)}  无痕删除: {len(lost)}  无痕新增: {len(new_)}"
          + (f"  已申报删除: {len(allowed)}" if allowed else ""))
    for i in lost:
        print(f"  [丢失] raw#{i}: {rb[i][:60]!r}")
    for i in allowed:
        print(f"  [已申报删除] raw#{i}: {rb[i][:60]!r}")
    for i in rewrite:
        print(f"  [改写] raw#{i}: {rb[i][:60]!r}")
    for j in new_:
        print(f"  [新增] clean#{j}: {cb[j][:60]!r}")

    fail = bool(lost) or (not skip_tab and rs['tables'] != cs['tables']) \
        or (not skip_img and rs['imgs'] != cs['imgs'])
    print("守恒: " + ("FAIL(存在无痕删除或表格/图片数不一致)" if fail else "OK"))
    sys.exit(1 if fail else 0)


if __name__ == "__main__":
    main()
