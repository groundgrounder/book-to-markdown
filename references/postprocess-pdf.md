# Post-processing checklist for PDF→Markdown books (OCR or marker route)

Raw converter output is **not deliverable**. Run these steps in order. Steps marked ⚖️ need sample review before batch execution.

**总则：文字零增删** — the manual steps below move, join, and re-format content; they never rewrite it. OCR 错字修复 is a separate phase that runs BEFORE this checklist: in the scanned route, `crosscheck.py` → 看图裁决 → `apply_review.py` on the per-page md, then `merge_pages.py`. Anything you notice here goes into a human-check list (人工核对清单), not fixed inline.

**PaddleOCR-VL output specifics** (primary engine in the scanned route):
- Footnote markers arrive as LaTeX: `普洛克路斯忒斯之床 $ ^{*} $`, `$ ^{①} $` → normalize to the plain marker (`*`, `①`) before §3; they also throw off the `$` pairing check in §4.
- Boxed content (案例框/栏 X.Y) often comes out as an HTML `<table>`: a two-column "实录 | 评论" transcript becomes a real table. The box intro paragraphs can land inside a cell. That is content, not junk. Keep it and decide the callout form in §6.
- A paragraph that spans two columns comes out whole in the first block, and the continuation block is empty. Nothing is lost; don't "repair" it.
- Tables printed as images (e.g. 拱极模型图、奖赏协商表) are kept as images only. Neither engine writes the text inside into the md. PP's `res.json` image blocks do hold the recognized text, so pull it from there if the book needs it searchable.

**双源印证例外**：标题文字修复（缺字/断行/粘连）在书内两个独立来源逐字一致时允许修——目录、前言章节枚举、正文他处、同书平行结构任二互证即可（如目录 `第三章 自我与发展` + 前言 "第三章探讨了自我与发展" → 正文残损标题 `我与发展` 可直接补全）。单源但损伤模式高度确定（断点明确、语义唯一）也可修，逐条在报告里给出依据。正文段落不适用此例外。

Page anchors `<!-- 第N页 -->` exist only in the OCR route (`merge_pages.py`); marker output has none — anchor-specific instructions apply only where anchors exist.

## 1. Remove noise

- Delete whole pages: title pages, CIP/copyright pages, award/promo pages, blank pages, e-reader navigation pages ("封面 书名 版权…" or `[General Information]` blocks at the end). ⚖️ **Keep TOC, index, prefaces, exercises, references, appendices by default — ask the user before deleting any of these.**
- Delete lines: orphan page-number lines (`^\d{1,4}$`) — sample their context first (table digits can look identical).
- Page deletion regex: `\n\n\n<!-- 第N页 -->\n\n.*?(?=\n\n\n<!-- 第\d+页 -->|\s*$)`. If the anchor is inline (not on its own line), that page was part of a paragraph merge — do not delete.
- **Table-like blocks are content even when OCR drops them into the middle of a prose paragraph** — relocate them to where the text references them (见表6-4), never delete them. Misplaced tables read as "garbage" and deleted is a production incident (two tables of a published book, recovered only from `.bak`).

## 2. Merge split paragraphs

Signal: a paragraph fragment does NOT end with sentence-final punctuation (。！？；：…"）】》) and its continuation is NOT a new block (heading/list/table/formula/figure caption/第X章节). Two interruption shapes:

- **Across pages (OCR route, anchors present)**: judge the page's last NON-footnote line (footnote lines carry ①②③/[*]/注 markers — see §3). Join with the next page's first line into one line, keeping the anchor inline: `…任<!-- 第6页 -->务…`. The footnote block stays at its page position.
- **Around a footnote block (both routes; the common case in marker books)**: fragment → footnote block → continuation in sequence. Move the footnote block aside, join the two fragments into one line, place the footnote block right after the completed paragraph.

Exclude: TOC entries (dot leaders / trailing numbers), copyright-keyword lines, short lines (<8 chars), HTML table rows. Prefer under-merging over wrong merges.

## 3. Footnotes (①②③ / [*] / 注：)

Footnotes survive conversion in both routes — OCR configs keep the `footnote` region label (NOT in `markdown_ignore_labels`); marker inlines footnote text as ordinary lines. They land at the page bottom and interrupt whatever paragraph runs onto the next page.

- Identify: leading marker (①②③④⑤ / [*] / [1] / 注：), clustered position (just before the page anchor in OCR output; sandwiched between a paragraph fragment and its continuation in marker output). Delete leftover separator lines (──── / ――――) above them.
- After §2 rejoins the paragraph, keep the footnote block intact with its original markers, placed after the completed paragraph.
- ⚖️ Clean, unambiguous markers (every ① in the text matches exactly one ① footnote): convert to GFM footnotes with unique IDs — markers restart every page, so namespace by page or chapter (`[^p42-2]` / `[^ch3-1]`), definitions collected at chapter end. Obsidian renders these. Ambiguous or mangled markers → keep the block form; do not force the conversion.

## 4. Fix math delimiters

- Total `$$` must be even. Split by page anchors to locate odd pages, then fix broken formula lines (typical: `$$…$` missing one `$`; a stray `$$` inside prose).
- Inline `$` must pair per line (except inside HTML table rows, which renderers don't parse).
- χ² is often misread as `$^²2` or `$x^{2}` — normalize to `χ²`.

## 5. Unify heading hierarchy ⚖️

- `#` = book title only. Part level (编/部分/前言/目录/参考文献) → `##`; chapters → one deeper; sections → one deeper still; （一）/一、/1. → one more. Chapter fixtures (本章要点/思考与练习/【资料卡】/原始文献/综述文章/延伸阅读) → section level (one below chapter).
- Fix garbled headings; normalize one space after 第X章/第X节; drop duplicate part headings (keep first body occurrence).
- **标题损伤五类**（按可机械性排序，前两类纯级别操作，后三类涉文字走双源印证）:
  1. **系统性偏深**：全书 章=H2、节=H4 而 H3 空缺（跳变成百上千处）→ 该语义层整体提升 1 级，不要逐点修。
  2. **断章**：章号孤立成行（`第二章` 单独一行、`## 蛋白质结构基础` 在下一行）→ 合并；章号整个丢失（正文标题无号、孤立行也不存在）→ 按目录恢复。章号也可能粘在上一条参考文献行尾（`…513-528.附录B`）→ 剥离移入标题。
  3. **标题文字损伤**：OCR 吃字（`我与发展`←自我与发展，模式：吃掉"第N章"行 + 标题首字起）、全角/半角混淆 → 双源印证修复（总则）。
  4. **粘连与重复分裂**：标题行尾粘着整段正文（`## 信号通路可分为以下两类。`）→ 切开，正文全保留；同一标题断成两个还重叠（`自我提升和自我满` + `升和自我满足的文化差异`）→ 合成去重叠。
  5. **碎片标题化**：正文整句/代码行/表格行/图注/页眉页脚被提了 `#` → 去 `#` 还原为正文行（文字不动）；页眉/页脚/图号残片（`MBoC7 e1.24/1.24` 类）直接从标题行剥离删除。
- **Misplaced structural headings** (编/部 titles landing inside a chapter intro) → relocate to their position in the heading tree. The fidelity check (§9/§11) then sees a move, not a deletion.
- **OCR order scrambling** (blocks out of reading order) → reorder the blocks, keep every line.
- Broken headings `第节`/`第章` (numeral eaten by OCR): restore numeral from the TOC and fix level.
- Missing section headings: cross-check TOC entries against body section headings chapter by chapter. Locate the insertion point via the **numbering restart** (一、 numbering restarts at section boundaries) and insert the heading.
- TOC pages → nested list (`- ` with indentation; strip dot leaders and page numbers). ⚖️ Ask the user before dropping TOC page numbers.
- **Rebuild `## 目录` from the final heading tree once every heading edit is done** — earlier rebuilds go stale. Exclude non-body entries (本章内容小结/思考题), strip 残留 `·` and intra-word spaces (听 觉→听觉), drop stray `·`/space fragments OCR leaves on otherwise-empty lines.

## 6. Boxed content → callouts (知识框/资料卡)

OCR books pack recurring boxes (知识应用/学术争鸣/研究进展/人物介绍/资料卡…) that arrive as plain prose, indistinguishable from body text until a type label shows up.

- ⚖️ Pick the target style once per book: Obsidian callout (`> [!note] 类型：标题`) or plain blockquote (`> **类型：标题**`). Callouts degrade to plain blockquotes in EPUB readers — when EPUB is the target, plain blockquotes skip that conversion.
- Detect by searching the book for its box-type labels — every hit marks a box. Intact boxes convert mechanically: prefix `> ` per line, one `> [!note] 类型：标题` header line.
- Broken boxes (common): content truncated by a page break with body prose interleaved, or lines scrambled inside the box. Reassemble with 文字零增删 — every line lands either inside the box or back in the body, none duplicated. If the original order is unrecoverable, keep the box intact in reading order, mark it 【OCR乱序待人工核对】, and log it in the human-check list.
- Completion: every box in the book either converted or flagged; no body prose inside a box; no box line left in the body.

## 7. Reference lists (参考文献)

- Ensure a `## 参考文献` heading exists; add it if missing.
- Split glued entries (two references run together on one line — signals: a numbered entry restarts mid-line, or an author/title/publisher/year sequence repeats without a break).
- Rejoin wrapped lines: continuation lines don't end with sentence-final punctuation.
- Completion: every entry on its own line; entry order preserved; each entry starts where the previous one ends.

## 8. Punctuation normalization (OCR route only)

OCR text mixes half/full-width brackets and straight/curly quotes arbitrarily.

- Brackets: unify per book — full-width in Chinese prose, half-width inside ASCII contexts. ⚖️ Ask once per book if the direction is unclear.
- Quotes: restore curly quotes in Chinese prose with a script (pair-matching like `fix_quotes.py`), then hand-fix unmatched spots.
- Leftovers: a straight quote that also exists in the raw OCR output is OCR-original mixing, not a cleanup miss — leave it. Only fix quotes that the raw file does not contain.
- Completion: no half-width bracket opening into Chinese prose; quote pairs closed within the paragraph; every remaining straight quote traced to the raw file.

## 9. Big books: bounded cleanup batches

A large book's cleanup starts with deterministic findings and bounded evidence packets. Read [patch-control.md](patch-control.md) for cost, exact patches and review states. Parallel agents are optional and require authorization; do not send whole chapters for sparse corrections.

- Group findings by source region (front/tail separate); a worker proposes exact replacements in its packet, never edits the shared candidate. Cap packet size; uncertain glyphs/layout go to image review.
- Per chunk, before merging: `fidelity_diff.py <chunk-clean> <chunk-raw>` — every 无痕删除/无痕新增 eyeballed and classified as an expected move/join, or fixed. On 10MB-class files `fidelity_diff.py` is O(n²) and times out — script the edit operations, replay them on the `.bak`, and byte-compare with the new file instead.
- Recombine chunks in order, then verify the chunks and the main file agree.
- **并行 agent 纪律**（多 agent 同时改一个书架时同样适用）: 每个 agent 的全量报告写入独立文件（`<任务名>.md`，文件名在任务契约里写死，避免并发写入彼此覆盖），回传主会话只要一行总结；任务里给的扫描计数一律标注"是估计值，按实地全量修"（正则预扫只给下限，曾报 x1 实地 x12）。
- Keep the raw `.bak` until delivery — it is the only arbiter of conservation.

## 10. Remove page anchors

Anchors have served their purpose (page deletion, paragraph merges, per-page math fixes) — strip them all before delivery. This must be the LAST processing step.

- Inline anchors inside merged paragraphs: delete the anchor text only, no padding — `…任<!-- 第6页 -->务…` → `…任务…`.
- Standalone anchor lines: delete the whole line and collapse the leftover double blank line.
- Verify: `grep -c '<!-- 第' out.md` → 0. Keep the pre-strip anchored file only as an internal intermediate for page reruns — never deliver it.

## 11. Final gate (all must pass)

- [ ] `$$` even; inline `$` paired
- [ ] no `<!-- 第N页 -->` anchors left
- [ ] all `<img src="imgs/…">` targets exist
- [ ] `fidelity_diff.py <clean> <raw>`: zero 无痕删除; table count and image ref count match (or the delta is a documented, eyeballed merge)
- [ ] div/table/tr/td tags paired
- [ ] exactly one H1 (book title); chapter level consistent book-wide
- [ ] `## 目录` rebuilt from the final heading tree; non-body entries excluded; no `·`/intra-word-space residues; entries ↔ body headings 1:1
- [ ] no `�`, no 30+ dot-leader runs, no `第节` broken headings
- [ ] no footnote separator lines (────/――――) left; footnote blocks intact, markers preserved, placed after their paragraph
- [ ] scanned route: every `crosscheck.py` site decided and applied (`apply_review.py` reports 0 undecided); `未对齐` pages looked at whole; PP-only books: `orphan_check.py` = 0
- [ ] patch route: all four gates ran on the unchanged final candidate; each in-scope finding is fixed-and-rechecked or has exact-context source-bound KEEP evidence; zero pending/unlocated/deferred body findings. Keep raw and effective unresolved counts separate.
- [ ] spot-check 2–3 pages against the original (formula pages, table pages, two-column pages, footnote pages)

## Notes

- Parts of a book processed at lower DPI show a higher odd-character rate (~1% vs ~0.4%) — expected when the *scan itself* is low-res. Rendering a 300 ppi scan at 300 vs 144 DPI made no measurable difference for either engine (2026-10-20 pilot). Re-run individual pages from the original PDF if any page is badly degraded.
- Lost inter-word spaces in English parenthetical glosses/references are chronic in pp_structurev3 output (`newhistoryofpsychology`); PaddleOCR-VL keeps them. Do NOT auto-fix PP output (word-segmentation false positives).
- OCR 错字 (天折→夭折 class) are handled by the crosscheck phase before this checklist; anything noticed during format cleanup goes to the human-check list instead of being fixed inline.
