#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""new_doubles.py <旧 md> <新 md>
补丁后的终检：列出新 md 里比旧 md 多出来的叠字（"老师师""即将将""兄兄弟"）。
VL 在页首会把上一页末字重复一次、审图时也可能误判，这两类错都会留下叠字；
"等等/仅仅/叔叔/妹妹"这类本来就是叠词，自动略过，剩下的逐条看。
"""
import collections, re, sys

WORDS = set("等等 仅仅 常常 往往 渐渐 刚刚 人人 个个 天天 年年 处处 时时 事事 样样 种种 久久 默默 慢慢 "
            "轻轻 静静 深深 紧紧 偷偷 悄悄 匆匆 纷纷 频频 屡屡 步步 层层 节节 代代 世世 家家 户户 "
            "妈妈 爸爸 哥哥 姐姐 弟弟 妹妹 叔叔 婶婶 姑姑 舅舅 伯伯 爷爷 奶奶 宝宝 星星 夫夫 "
            "看看 想想 谈谈 试试 说说 听听 走走 问问 做做 歇歇 不不 是是 好好 多多 稍稍 略略 明明 "
            "".split())


# 跨词边界的正常叠字：前一个词以 X 结尾、后一个词以 X 开头（斯卡夫|夫妇、有关|关系、独特|特征）
CROSS = re.compile(r"夫夫妇|关关系|特特[征性点色]|将将来|人人[们格]|的的确|子子女|生生[活命物理长]|学学[习生科]")


def doubles(t):
    return collections.Counter(m.group(1) * 2 for m in re.finditer(r"([一-鿿])\s*\1", t)
                               if not CROSS.match(t, m.start()))


def main():
    old, new = (open(p, encoding="utf-8").read() for p in sys.argv[1:3])
    co, cn = doubles(old), doubles(new)
    flagged = {k: cn[k] - co.get(k, 0) for k in cn if cn[k] > co.get(k, 0) and k not in WORDS}
    if not flagged:
        print("没有新增的可疑叠字"); return
    for k, n in flagged.items():
        for m in re.finditer(k[0] + r"\s*" + k[0], new):
            if CROSS.match(new, m.start()): continue
            print(f"{k} +{n}: …{new[max(0, m.start() - 15):m.end() + 10]!r}…")
    sys.exit(1)


if __name__ == "__main__":
    main()
