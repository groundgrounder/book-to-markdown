# Post-processing checklist for EPUB→Markdown

EPUB text is digitally native — **no OCR errors, no page splits, no page anchors**. The artifacts are markup-level. Run in order; ⚖️ = needs user input.

## 1. Remove noise (copyright / pricing / ads)

EPUB has no page anchors — noise lives in **sections** at the top (or end) of the file. Delete by heading-to-heading range or keyword-line match:

- **Copyright/CIP sections**: identify by keywords `ISBN`, `图书在版编目`, `CIP`, `版权所有`, `定价：`, `出版发行`, `印刷`, `开本`, `印次`. Typically 1–2 sections near the top.
- **Promo/ads**: 编辑推荐、媒体推荐、名家推荐、获奖信息、同系列书目广告（"××系列"、"推荐阅读"）, often at front or back.
- Orphan digit-only lines left from page headers (rare in EPUB but happens in badly-made files).
- ⚖️ **Keep by default, ask before deleting**: 目录, 索引, 前言/序言, 内容简介 (debatable), 习题, 参考文献, 附录. Show the user what will be deleted (heading + first line) and get confirmation.

## 2. Promote fake headings

- Source using `<font size="N"> **标题** </font>` instead of `h1–h6`: rank sizes descending → map to `#`/`##`/`###`. Verify against the book's structure (chapters vs sections) before batch-applying.
- Books with semantic headings: check level sanity (exactly one `#`, chapters at one consistent level) and unify as needed.
- 标题损伤（断章/缺字/粘连/碎片标题化/系统性偏深）与 PDF 路线同款——按 [postprocess-pdf.md](postprocess-pdf.md) §5 的五类处理；标题文字修复走该文件总则的双源印证例外。EPUB 同样会吃到这些（转换器断行/OCR 源 EPUB），不是扫描书专利。

## 3. Strip formatting wrappers (keep text)

- Kindle/Calibre style spans: `<span class="kindle-cn-bold">晶</span>` → `晶` (or `**晶**` when the class means bold/emphasis — decide per class, per book ⚖️). `<span class="kaiti">` (楷体) usually marks emphasis in Chinese books.
- `<font color="...">text</font>` → `text`. Any other `<font>` wrappers after heading promotion → unwrap.
- **Preserve** `<sup>`/`<sub>` (they carry meaning: 8th, x², H₂O).
- After cleanup, `<span`/`<font` count should be ~0 (except whitelisted).

## 4. Internal links `[text](#anchor)`

- TOC-page link lists → convert to nested plain list (strip links, indent by level).
- Endnote/footnote refs (`[1](#...fn1)`): ⚖️ keep if targets exist in-file (functional jump links), otherwise strip to plain `1`. Validate: extract every `](#xxx)` target and check a matching anchor/id exists.

## 5. TOC handling

- If the converted file has no usable TOC, build one from the heading tree (`## 目录` + nested list) and inject after the title. Matches the PDF-side format.
- If a TOC page exists as links → see step 4.

## 6. Multi-book sets

- Box sets (套装共N册) land in one file. Offer to split by top-level part headings into one file per book.

## 7. Final gate

- [ ] no copyright/pricing/ads residue (`ISBN`, `定价：`, `版权所有`, 推荐语 sections gone)
- [ ] no `<span`/`<font`/`<svg` left (except whitelisted `<sup>/<sub>`)
- [ ] all internal link targets resolve (or links stripped by choice)
- [ ] all `media/` image refs exist on disk
- [ ] exactly one H1; chapter level consistent; heading tree reads like the book's TOC
- [ ] no Calibre class names left in headings (`class="calibre…"`)

## Notes

- `\[` and similar pandoc escapes are **correct** GFM (render as literal `[`) — do not "fix" them.
- No math-delimiter or character-error checks needed (native text). Spot-check only for conversion-time structure loss: dropped tables, list flattening, missing blockquotes.
