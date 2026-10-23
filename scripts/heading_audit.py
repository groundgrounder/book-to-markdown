#!/usr/bin/env python3
# 层级审计.py <file.md> — 标题层级疑点: 首标题非H1 / 向下跳变 / setext残留 / 章级混用
import re, sys
p = sys.argv[1]
t = open(p, encoding="utf-8").read()
t = re.sub(r"```.*?```", "", t, flags=re.S)
lines = t.split("\n")
heads = []
for i, l in enumerate(lines):
    m = re.match(r"^(#{1,6})\s+(.*)", l)
    if m: heads.append((len(m.group(1)), m.group(2).strip()[:40], i+1))
    elif i+1 < len(lines) and re.match(r"^={2,}\s*$", lines[i+1]) and l.strip():
        heads.append((1, "SETEXT=:"+l.strip()[:38], i+1))
if not heads:
    print("无标题"); sys.exit(0)
prob = []
if heads[0][0] != 1: prob.append(f"首标题H{heads[0][0]}@L{heads[0][2]}")
jumps = {}
for (l1,_,_),(l2,_,n2) in zip(heads, heads[1:]):
    if l2 > l1 + 1: jumps.setdefault(f"H{l1}->H{l2}", []).append(n2)
for k, v in jumps.items(): prob.append(f"跳变{k}x{len(v)}(如L{v[0]})")
st = [h for h in heads if h[1].startswith("SETEXT=:")]
if st: prob.append(f"setext=x{len(st)}(如L{st[0][2]})")
ch = {}
for lv, tx, n in heads:
    if re.match(r"^(第[0-9一二三四五六七八九十百零]+章|Chapter\s+\d+|CHAPTER\s+\d+)", tx):
        ch[lv] = ch.get(lv, 0) + 1
if len(ch) > 1 and sum(ch.values()) > 5: prob.append(f"章级混用{ch}")
print(p + "\t" + (";".join(prob) if prob else "CLEAN"))
