#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""format_inserts.py extract|apply <patch 后的 md> <工作目录>
patch_cleaned.py 插进来的段落（<!-- 补 pNNNN --> … <!-- /补 -->）还是新 OCR 的原样格式，
要按周围的格式整理（callout 的 "> " 前缀、HTML 表格补成完整的表、页底脚注挪到合适位置、
图注/小标题独立成行），然后去掉标记。

extract：行内的普通插入（前后都是正文、不在 callout 里、不含表格标签）直接去标记；
         其余每块连同前后各 600 字写成 jobs/NNN.txt，交给文本子代理按 jobs/README 改写为 jobs/NNN.out.txt
apply：  逐块校验文字、标点和图片引用守恒；只许改格式。
         任一块漏交、改字或输入指纹失效，整批失败且不写成品；全部通过才原子写回。
"""
import os, re, sys, json
from pathlib import Path
from apply_exact import asset_refs, visible
from review_contract import atomic_write, digest, guard_outputs, read_text

BLK = re.compile(r"(\n\n)?<!-- 补 (p\d+)( 脚注)? -->\n?(.*?)\n?<!-- /补 -->(\n\n)?", re.S)
TAG = re.compile(r"<[^>]+>|!\[[^\]]*\]\([^)]*\)|\[\^[^\]\s]+\]:?|\[![A-Za-z]+\]")


def norm(s):
    return visible(s)


README = """你在整理一本书的 Markdown。每个 NNN.txt 里，【待整理】之间是一段从扫描页补回来的原文，
格式还是 OCR 的原样；上文/下文是书里它前后的内容（已经整理好的格式，仅供参照，不要改）。

把【待整理】这段改成和上下文一致的 Markdown 格式，写到 NNN.out.txt（只写改好的这一段，不要写上下文）：
- 上文是 callout（每行以 "> " 开头）而这段在框内：每行加 "> "，空行写成 ">"
- 是一个框（栏 X.Y …）的标题/开头：写成 "> [!note] 栏X.Y 标题"，后面内容每行 "> "
- 是 HTML 表格的一部分（含 </td><td>）：补成和上下文同样风格的完整 <table>…</table>，或者如果上下文里已经有
  这张表，就只输出缺的那几行 <tr>…</tr>
- 以 ①②③ 开头的页底脚注：原样保留为独立段落
- 图注、作者头衔（"G. 贝特森，哲学博士"）、小标题：独立成行
- 是一段完整的正文：原样输出

铁律：只改格式（加减 "> "、换行、HTML 标签、Markdown 符号），一个汉字、字母、数字都不许增、删、改，
标点和图片引用也必须原样保留、顺序不变。不确定怎么排就原样输出；需要改字时另走审图补丁，不在排版任务中改。
"""


def main():
    mode, md, work = sys.argv[1:4]
    jobs = os.path.join(work, "jobs")
    if mode == "extract":
        if Path(work).is_symlink() or (Path(work).exists() and any(Path(work).iterdir())):
            sys.exit('工作目录非空或为符号链接；使用新目录或继续现有apply，不覆盖起点。')
        os.makedirs(jobs, exist_ok=True)
        open(os.path.join(jobs, "README.txt"), "w", encoding="utf-8").write(README)
        t = read_text(md)
        out, last, n_auto, n_job = [], 0, 0, 0
        for m in BLK.finditer(t):
            body = m.group(4)
            prev = t[:m.start()].rstrip("\n").split("\n")[-1] if m.start() else ""
            simple = not m.group(1) and not prev.startswith(">") and "<t" not in body and "</t" not in body
            out.append(t[last:m.start()])
            if simple:
                out.append(body); n_auto += 1
            else:
                k = f"{n_job:03d}"
                out.append(f"<!-- 待排 {k} -->")
                open(os.path.join(jobs, f"{k}.txt"), "w", encoding="utf-8").write(
                    f"页 {m.group(2)}{'（脚注）' if m.group(3) else ''}\n\n【上文】\n{t[max(0, m.start() - 600):m.start()]}\n"
                    f"【待整理】\n{body}\n【/待整理】\n\n【下文】\n{t[m.end():m.end() + 600]}\n")
                open(os.path.join(jobs, f"{k}.orig.txt"), "w", encoding="utf-8").write(
                    (m.group(1) or "") + body + (m.group(5) or ""))
                n_job += 1
            last = m.end()
        out.append(t[last:])
        open(os.path.join(work, "staged.md"), "w", encoding="utf-8").write("".join(out))
        originals = {p.name: digest(p.read_bytes()) for p in Path(jobs).glob('*.orig.txt')}
        manifest = {'source_sha256': digest(t), 'staged_sha256': digest(''.join(out)),
                    'originals': originals, 'script_sha256': digest(Path(__file__).read_bytes()),
                    'format_guard_sha256': digest(Path(__file__).with_name('apply_exact.py').read_bytes()),
                    'contract_sha256': digest(Path(__file__).with_name('review_contract.py').read_bytes())}
        atomic_write(Path(work) / 'manifest.json', json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
        print(f"行内直接去标记 {n_auto} 处；需要排版 {n_job} 块 → {jobs}/NNN.txt（说明见 README.txt）")
    elif mode == 'apply':
        guard_outputs([md], [Path(work) / 'manifest.json', Path(work) / 'staged.md', jobs,
                             __file__, Path(__file__).with_name('apply_exact.py'),
                             Path(__file__).with_name('review_contract.py')])
        manifest = json.loads(read_text(Path(work) / 'manifest.json'))
        t = read_text(Path(work) / 'staged.md')
        if digest(read_text(md)) != manifest['source_sha256'] or digest(t) != manifest['staged_sha256']:
            sys.exit('源文件或staged已改变；拒绝套用旧排版结果。')
        if (digest(Path(__file__).read_bytes()) != manifest['script_sha256']
                or digest(Path(__file__).with_name('apply_exact.py').read_bytes()) != manifest['format_guard_sha256']
                or digest(Path(__file__).with_name('review_contract.py').read_bytes()) != manifest['contract_sha256']):
            sys.exit('排版工具已改变；重新extract并审阅。')
        bad = []
        for m in list(re.finditer(r"<!-- 待排 (\d{3}) -->", t))[::-1]:
            k = m.group(1)
            orig = read_text(Path(jobs) / f'{k}.orig.txt')
            if digest(orig) != manifest['originals'].get(f'{k}.orig.txt'):
                sys.exit(f'起点块{k}已改变；拒绝写入。')
            f = os.path.join(jobs, f"{k}.out.txt")
            new = read_text(f).strip("\n") if os.path.exists(f) else None
            if new is None or norm(new) != norm(orig) or asset_refs(new) != asset_refs(orig):
                bad.append(k)
                continue
            lead = "\n\n" if orig.startswith("\n\n") else ""
            trail = "\n\n" if orig.endswith("\n\n") else ""
            t = t[:m.start()] + lead + new + trail + t[m.end():]
        if bad:
            sys.exit(f'未写任何成品：缺结果/文字标点图片不守恒的块 {bad}；修复结果后重试。')
        left = len(re.findall(r"<!-- 补 |<!-- 待排 ", t))
        if left:
            sys.exit(f'仍有{left}个补丁/排版标记；未写成品。')
        atomic_write(md, t)
        print('全部排版块校验通过并写回；残留标记 0')
    else:
        sys.exit('mode must be extract or apply')


if __name__ == "__main__":
    main()
