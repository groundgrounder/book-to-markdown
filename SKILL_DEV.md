---
name: book-to-markdown
description: Convert books to clean single-file Markdown with images, heading hierarchy, and nested TOC — scanned PDFs via PaddleOCR-VL cross-checked against pp_structurev3 (only the disagreements are reviewed against the page image), text-layer PDFs via marker, EPUB via pandoc, plus Markdown back to EPUB and resumable batch mode for whole bookshelves. Use when converting 电子书/教材/扫描版 PDF/EPUB to Markdown or cleaning up OCR'd book text.
---

# book-to-markdown

> Internal documentation for the Claude Code skill（给 Claude Code skill 用的内部文档）.

Routes: **EPUB → pandoc** (text already digital), **text-layer PDF → marker**, **scanned PDF → PaddleOCR-VL + pp_structurev3 双引擎对拍**.

## Cost and Acceptance Contract

- For paid or multi-book work, agree the total budget before paid calls. Count the main session, text/image review, retries and OCR APIs. No paid subagents does **not** mean zero total cost. If billing is unavailable, disclose that limitation and cap batches, context, output and retries; do not promise an enforceable dollar ceiling without metering. Stop before exceeding the approved envelope.
- Export deterministic finding lists first. Text-only work gets small self-contained packets; reserve images for uncertain glyphs/layout. The main session reads summaries, changed regions and samples, not repeated whole-book dumps. Delegation must be authorized; respect no-fork/model/cost constraints. A local fallback still consumes main-session tokens.
- Re-OCR patching and substantial cleanup must follow [references/patch-control.md](references/patch-control.md): bounded edits, input fingerprints, per-finding evidence, staged delivery and final full-scope validation. Running gates is not passing them. Pending, unlocated or deferred in-scope findings block installation.

**为什么双引擎**（2026-10-20 试点，3 本扫描教材 29 页，逐处看原图定金标准）：单引擎的错误是静默的。旧流程（pp_structurev3 + PP-DocLayout-M）在难页上整段丢正文 12%（案例框、对话实录、照片旁的行、译者注），而 fidelity_diff 只跟 OCR 原始输出比，永远看不见。双引擎把审图重点缩小到分歧处，但下列数字仅是该试点结果；共同误读、原书误印和版面边界仍须高风险抽查，不能据此承诺全书零错：

| 方案 | 正文整段丢失 | 错字 | 英文丢空格 |
|---|---|---|---|
| 旧：PP balanced（DocLayout-M）| 9.2% | 0.17% | 6 处 |
| PP + PP-DocLayout_plus-L | 0.3%（一行表格）| 0.15% | 8 处 |
| PaddleOCR-VL-1.6 | 0.1%（索引两条）| 0.04–0.06% | 1 处 |
| VL 为主 + PP 对拍 + 看图裁决 | 0 | 0 | — |

两者的错误类型互补：VL 爱"顺手改对"原书（迷团→谜团、表露→透露、原书误印"过估估计"→过估计）、索引页偶尔漏条目；PP 把破折号认成"一"、页边原版页码混进正文、生僻字认错（癔→意）、英文丢空格。
More than a handful of books → batch mode: [references/batch.md](references/batch.md) — plan.tsv manifest, resumable queues, two-machine meet-in-the-middle, acceptance via `review_gates.py`.

## Step 0: Preflight (run first, always)

```bash
./scripts/preflight.sh <书架目录>
```

Prints the device tier and the exact OCR commands to use, plus warnings (VRAM/RAM/disk/battery/HF reachability/Syncthing sync dir/same-name PDF+EPUB collisions/oversized pages). Primary engine PaddleOCR-VL needs ≥6GB VRAM (<10GB automatically runs through `scripts/paddleocr_lowvram.py`). The tier picks the config for the pp_structurev3 cross-check engine:

| 档位 | 设备 | 配置 | 说明 |
|---|---|---|---|
| full | GPU ≥16GB 或 CPU | `configs/paddlex_full.yaml` | DocLayout_plus-L + server 识别 + SLANeXt，batch 8 |
| balanced | GPU 6–16GB | `configs/paddlex_balanced.yaml` + `--precision fp16` | 与 full 同一套模型，batch 1（6GB 实测放得下） |
| lite | GPU <6GB | `configs/paddlex_lite.yaml` + `--precision fp16` | mobile 识别 + DocLayout-M，**会整段漏正文**，必跑 `orphan_check.py` |

⚠️ 旧版 balanced 用 PP-DocLayout-M 省显存，代价是版面漏框、正文整段丢失（见上表）。版面模型是 PP 路线最关键的一环，宁可降 batch 也别降版面模型。

First run on a new machine → one-time install: [references/setup.md](references/setup.md).

## Step 1: Detect the route (PDFs only)

Sample 15 pages at the 10% mark:

```bash
pdftotext -f <10%处> -l <+15页> book.pdf - | tr -d '[:space:]' | wc -c
```

- Clean text (>2000 chars) → text layer exists, **skip OCR**, use marker (an order of magnitude faster, keeps headings/tables/formulas/images):
  ```bash
  marker_single book.pdf --output_dir out --disable_ocr
  ```
  (`--disable_ocr` uses the embedded text instead of Surya re-recognition — 4× faster. HF unreachable → `export HF_ENDPOINT=https://hf-mirror.com`)
- marker output goes through the same PDF post-processing below — page-bottom footnotes interrupting paragraphs are the common case here (checklist §2–3).
- <100 chars → scanned → OCR pipeline below.
- A few hundred chars of **repeating watermark text** (the same short phrase stamped on every page) → scanned. pp_structurev3's `markdown_ignore_labels` drops headers/footers/page numbers, so these watermarks never reach the md — judge watermark presence by the delivered md, not the source's text layer.
- Garbled text → junk OCR layer embedded by the scanner → scanned.
- **Clean-looking text that is really someone else's OCR → scanned.** The char count can't tell a typeset PDF from a scan with a hidden OCR layer, and that layer passes the >2000 test. Check before choosing marker:
  ```bash
  pdfinfo book.pdf | grep -E 'Producer|Creator'        # Paper Capture / ABBYY / calibre / Pdg2Pic / FreePic2Pdf
  pdffonts -l 5 book.pdf                               # HiddenHorzOCR / GlyphLessFont / 未嵌入的 MingLiU
  pdfimages -f 30 -l 31 -list book.pdf                 # 每页一张整页大图（~300ppi）= 扫描件
  ```
  Any hit → OCR route. Those layers ran 2–5% character error in the pilot (千/于, 间/问, 么/幺, 入/人) — 15× worse than PaddleOCR-VL — so `marker --disable_ocr` would just inherit them. Pass the PDF to `crosscheck.py --pdf` instead: the layer becomes a free third source for spotting dropped paragraphs.
- If marker mangles the layout, fall back to OCR, or run one page through both and pick the better output.

## Step 2: Scanned-PDF OCR pipeline（双引擎）

```bash
W=<work>   # 放在非同步目录：渲染图 + 两份逐页结果，每本 ~1GB
./scripts/pdf_ocr.sh book.pdf $W/vl --engine vl                                   # 主引擎 PaddleOCR-VL
./scripts/pdf_ocr.sh book.pdf $W/pp --engine pp --config configs/paddlex_balanced.yaml --device gpu --precision fp16
./scripts/crosscheck.py $W/vl/<书名> $W/pp/<书名> $W/review --pdf book.pdf        # 对拍 → sites.tsv + 审图板
#   审图：看 $W/review/sheets/*.png，按编号在 sites.tsv 的 decision 列填 primary / secondary / =文字
./scripts/apply_review.py $W/review/sites.tsv $W/vl/<书名>                         # 裁决写回逐页 md（可重跑）
./scripts/merge_pages.py <out.md> $W/vl/<书名>                                     # 合并 + 页数核对
```

- **pdf_ocr.sh**: renders every page to PNG first (scale 2.0 = 144 DPI, same as PaddleX reading the PDF directly; 300 DPI measured no better for either engine), then feeds pending pages in batches. **Resumable**: pages with a `res.json` are skipped, so rerun the same command after any crash. Each page gets its own `pages/pNNNN/` dir, because crop filenames only encode box coordinates and would overwrite each other across pages. Ends by checking every page has a result (exit 1 + list otherwise).
- **Watchdog**: PaddleOCR-VL's local backend can stall forever on a page: one CPU core at 100%, GPU at 0%, stack frozen inside a GPU op (one page once ran 8 h). On one test page it failed 4 of 5 runs, while `CUDA_LAUNCH_BLOCKING=1` went 3/3 at the same speed (an async kernel race), so pdf_ocr.sh always sets it for VL. The watchdog stays as a backstop. A batch with no new page for `STALL` seconds (default 300) gets its stack dumped to `ocr.log` and is killed. That page is retried alone; a second failure records it in `bad_pages` and moves on. Three bad pages in a row stops the run, since that's an environment problem. Fill bad pages by copying the same page dir from the PP run.
- **Speed** (6GB RTX 4050, 100 consecutive pages): VL ~12 s/page, PP ~1.8 s/page. Two engines on a 500-page book ≈ 2 h.
- **crosscheck.py** needs no gold standard. It flags only where the engines disagree: drops (whole spans one side lacks), extras, VL repetition loops, short character differences. `pagenum`/`dash`/`digit` were always the primary engine's call in the pilot, so they come prefilled. Review load: ~0.4 sites per page on ordinary pages (100-page run: 38 sites, 12 of them real VL errors such as dropped line-end characters, 闵→冈, and "vol. 1"→"vol. I"), ~1.1 per page on hard pages (case boxes, tables, index). **The review needs eyes on the page image.** The cheap subagent (deepseek-v4.1-flash) can read images. Calibration: of 34 sites with known answers, it answered 30 and got 27 right. All 3 misses were an italic "vol. 1" read as "I" (on ambiguous glyphs its language prior wins, so it errs in the same place as VL). Workflow: have it review the sheets first and output `#编号 A|B|N|? 原文` → `./scripts/review_fill.py sites.tsv answers.txt` fills in the decisions and writes `recheck.txt`, which lists the `?`/`N` sites, any site with Latin letters or digits, and a random 10% sample. The main model re-checks only those. **Dispatch small batches (≤2–3 sheets per agent) and append to the answers file after each sheet.** It takes about 1.5 minutes per item, so a 9-sheet batch runs 3 hours, and one connection reset from the API loses the whole batch (this happened three times in a row).
- Pages marked `未对齐` (engines disagree on reading order by >5%: index pages, tables, two-column dialogue) can hide short differences inside large misalignments. Look at those pages whole.
- Crop location: the left and right context each pick a line; stack both at a line break. The reviewer must see the target and neighbors, not a plausible nearby sentence. `recheck_sheets.py` records page/site/bounds/input hashes; ambiguous or missing locations fall back to a full page labelled `UNLOCATED`, not a verified crop. The first version's short probes put 49 of 705 crops on the wrong line.
- No GPU / <6GB → PP alone (`--engine pp`), then **must** run `./scripts/orphan_check.py $W/pp/<书名>`. It finds lines the whole-page OCR read that never landed in any layout block, which are the silently dropped paragraphs.
- `--formula`: math-heavy books only, PP engine. **Default off**: the formula model is 713MB and its warmup can exhaust RAM and freeze the whole run. VL recognizes formula blocks natively; untested on a math-heavy book.
- `--render SCALE`: lower it for physically oversized pages (>800pt wide, the script warns), otherwise vision-model cost explodes 10–20×.
- Long runs: `nohup ... & disown`, and the launching command **must return immediately** (a killed launcher takes the process group with it). On Linux, pdf_ocr.sh runs the engine inside `systemd-run --user --scope -p MemoryMax=<half of RAM>`, so an OOM kills only the OCR process and not the terminal or desktop. Anti-sleep on macOS: `caffeinate -dims -w <script PID>`; only AC power prevents lid-close sleep.

### Re-OCR a book that's already been cleaned

The old md went through the full post-processing (heading tiers, TOC, footnotes, callouts), but its OCR dropped paragraphs and misread characters. Don't redo the post-processing. Keep the old md as the skeleton and patch it with the new reviewed OCR:

```bash
./scripts/patch_cleaned.py <旧.md> $W/vl/<书名> $W/patch [--pages 起-止]   # 跳过旧 md 有意删掉的前后附件页
```

- Pre-pass: wherever the new OCR has a dash between two Chinese characters, change "X一Y" in the old md to "X—Y". PP reading dashes as "一" is the most common old error, and leaving it breaks the alignment.
- Whole spans the new OCR has but are found nowhere in the old md get inserted at a unique anchor and wrapped in `<!-- 补 pNNNN -->…<!-- /补 -->`. Page-bottom footnotes go after their paragraph (`<!-- 补 pNNNN 脚注 -->`) and are extended to the end of their line. The format pass then reshapes them to the surrounding style (callout / `[^…]` / table) and strips the markers. Insertion rules, each from a defect found after the first three books were installed (pitfall 20):
  - Anchors: one before the span and one after, each unique in the old md's window. A short anchor (<14 characters) also has to roughly match on its outer side, or it's a coincidental hit ("把自我心理学理论" matched a different sentence and half of another sentence got inserted there). When the two disagree, trust the 14-character one; if both are short → `anchorconflict` in skipped.tsv.
  - Punctuation: anchors only see letters and digits. When the run of punctuation at the insertion point in the old md equals the new OCR's "punctuation before the span + punctuation after it", the whole run is replaced with before + span + after. Otherwise "…努力程度等" + insert + "。" leaves 。 as a paragraph by itself.
  - Inline vs block: a span becomes its own paragraph only if the new OCR has blank lines on both sides *and* the old md has a sentence end before the insertion point. VL breaks lines at page edges, so trusting its newlines splits one sentence into three paragraphs.
  - Spans containing LaTeX, or inside `$$`, are skipped (`formula`). The old md has the formula as an image, and the insert would be a `\mathrm{…}` fragment.
- Short differences take the new OCR's reading. Headings, multi-character deletions, and spans with no anchor go to `skipped.tsv` for a person to handle. Footnote marker differences (`[^ch5-1]` vs ①) are ignored.
- Coverage is checked order-insensitively against the whole old md, so footnotes the old md moved to chapter ends don't count as missing.
- **Run it only on reviewed new OCR** (after crosscheck → apply_review). Otherwise VL's own errors (闵→冈, dropped line-end characters) get written into the old md too.
- **Always pass `--verify $W/pp/<书名> $W/review/sites.tsv`**: a character only gets changed if the new PP reads it the same way at that spot, or if the spot was decided in review. In regions PP can't align (some tables, recorded whole as `extra`), VL's characters never got cross-checked. In the family-therapy book, VL read the original "冗赘" as "冗繁" there, and without this guard the correct old-md text would have been overwritten.
- Pass `--careful $W/review/unaligned.txt`: on those pages the engines disagree on reading order, short differences may not have reached review, and the new OCR's own errors may still be there. Those pages only get insertions; every character fix goes to skipped.tsv.
- Character-fix guards, each one added after a real false fix in the family-therapy book's first run:
  - Locate each page in the old md by its own hits, and only advance the cursor when the hits cluster. Scattered TOC hits once pushed the cursor to the back of the book, and 350/431 pages couldn't be found.
  - Only change characters where the alignment on both sides is trustworthy (≥10 identical characters each side). Otherwise a page-end repeat or swapped table cells can swap 一致。与此同时 for a passage from somewhere else. Exception: with ≥4 on each side *and* corroboration (PP reads it the same way, or review decided it), apply anyway. Two typos <10 characters apart ("泪丧，他担心这种泪丧") otherwise block each other and both stay wrong. Ones that are still too weak go to skipped.tsv as `weakalign`, not silently dropped.
  - Never insert a run of digits mid-sentence or right after a year (`Wachtel,1986`+`18`): that's the original-edition margin page number glued on. Do delete a 2–3 digit number in the old md with Chinese on both sides (家庭界 228 限).
  - Don't insert "一" where the old md already has a dash. When a dash replaces "一", take only the dash, not the surrounding parentheses or quotes.
  - Inside table rows, only apply ≤2-character fixes. Never insert a superscript (`$ ^{1} $`) into the old md as body text.
- **If a passage is garbled, reconstruct its complete logical region rather than accumulating tiny repairs.** Define source pages, region type, exact old text/hash, outside left/right anchors and a size cap. Confirm both printed boundaries: a callout's last paragraph is not necessarily the page's last paragraph, and a table can split a body word across pages. Separately rejoin outside prose. Use `apply_exact.py`, inspect its diff and per-deletion report, then apply explicit approved IDs. Never find the end by an unconstrained search for a repeated word. The cut “雇员”, displaced case targets and table16.2 boundary overrun are regression cases in `tests/test_patch_controls.py`.
- **Post-patch gates (run all four after format_inserts apply; the coverage gates can't see these):**
  - `seam_check.py <新.md> <旧.md> $W/vl/<书> $W/pp/<书>`: `punct`/`open`/`seam`/`fnote`/`latex`/`dash` are candidates, not automatic fixes. Export joins with `join_split.py <新.md> <旧.md> <VL> <PP> --pages pNNNN-pNNNN --plan joins.json`; inspect full regions, then use the same inputs with `--apply-plan joins.json --approve ID,ID --apply --backup-dir <fresh-dir>`. Bare `--apply` is rejected; source IDs are zero-based, not printed folios. Keep index/bibliography out of a body join plan.
  - `align_check.py <新.md> $W/vl/<书> $W/pp/<书> --old <旧.md>`: aligns page by page on ≥8-character anchors. `missing` = the page has it, the md doesn't have it at that spot (pp=1 means PP agrees); `moved` = an insert in the wrong place. This catches sentences that `uncovered` counts as present because their 8-grams happen to occur elsewhere in the book. Index/bibliography pages show up as noise from column order.
  - `decision_check.py <新.md> $W/review/sites.tsv`: every review decision actually landed in the md. Patch guards block some, and the review itself is wrong ~5–10% of the time (it ruled "即你将" as "即将将"), so check each hit, with `recheck_sheets.py` crops when unsure, rather than applying blindly.
- Final check: `new_doubles.py <旧.md> <新.md>` lists doubled characters the new md has and the old md didn't ("老师师", "即将将", "兄兄弟"), skipping real reduplicated words and cross-word repeats such as 斯卡夫|夫妇. VL repeating the first character of the next page at a page break, and the reviewer misreading 你 as 将, both leave this kind of trace. It caught a 即你将→即将将 in the family-therapy book.
- `format_inserts.py extract` writes bounded formatting jobs with surrounding context. Use a text worker only if authorized. `apply` checks source/tool/job hashes and text, punctuation and asset conservation; any missing/altered job fails the entire batch without a book write. It does not silently restore raw text and continue. Image review must still verify callout membership and table associations.
- **Acceptance is per finding, not a smaller counter.** Preserve raw reports and reviewed exceptions separately. A footnote needs full text, citation page and owning passage checked; matching its last 30 characters proves neither completeness nor placement. A formula exemption identifies the actual image, not any asset. Deletions need exact-span evidence, not a blanket batch-ID waiver. Tables and callouts are not category exemptions. Unknown locations remain pending; page exclusions must match user scope.
- Check touched regions plus neighboring source pages after each batch. Before install, run all relevant gates on the unchanged final candidate, check assets and diff conservation, back up the destination, then publish. Checkpoints bind source/old-md/page drafts/decisions/scripts/options/policy hashes. `review_contract.py` implements fingerprints and evidence packets; review readiness is not semantic correctness or installation PASS.
- In the patch scenario, set `drop`/`drop-t` sites to `primary` by default. Spans only PP or the text layer has are either already in the old md (it was also from PP, so the skeleton keeps them), text inside figures (genograms, structure diagrams; the old md kept those as images too), or garbage. Family-therapy book: of 57 + 34 such spans, 39 were already in the old md, and only 1 was body text missing everywhere (an item in a box). Before deciding, check them against the old md in one batch (`uncovered(span, 旧md)`) and pick out only what's missing from both.

## PDF post-processing (both routes)

The scripts handle the mechanical cleanup (conservative by design); the judgment-heavy remainder is the manual checklist.

```bash
./scripts/polish_book.py <book.md>   # 标题层级重排(书名唯一H1/卷H2/章H3), 去页码前缀, 孤立页码行, 目录点线, 公式幻觉截断
./scripts/toc_fix.py <book.md>       # 印刷目录→嵌套列表; 无目录则从标题树合成; 报告条目-正文匹配率
./scripts/cip_clean.py <book.md>     # 行级精确删除版权页/CIP(遇标题/图片/目录条目/完整句即停, 不吃前言)
./scripts/fidelity_diff.py <clean.md> <raw.md>  # 内容守恒: 与清洗前的原始输出比对, 表格/图片/段落零丢失(硬门禁)
./scripts/review_gates.py <目录>     # 全量客观校验: $$配平/锚点/图片/乱码/HTML标签配对 + 结构项分级
```

Then ALWAYS run the manual checklist for the remainder: [references/postprocess-pdf.md](references/postprocess-pdf.md) (callouts, reference lists, punctuation normalization, chunked parallel cleanup). Page anchors exist only in the OCR route; footnote rejoin/relocate (checklist §2–3) applies to both — OCR configs keep footnote regions (NOT in `markdown_ignore_labels`), marker always inlines footnote text.

## EPUB → Markdown

```bash
./scripts/epub2md.sh <book.epub> <outdir>
```

Key pandoc flags: `-t gfm` (Obsidian-friendly), `--wrap=none` (prevents CJK text being hard-wrapped at 72 cols), `--extract-media=media` (extracts images, rewrites relative paths). Built-in cleanup strips `<a>`-wrapped headings, `<span id>` anchors, SVG cover blocks, and trailing `\` hard breaks.

Note: some EPUBs lack semantic headings (fake them with `<font size>` + bold). Getting no `#` headings out is normal for such files — promote levels by `<font size="N">` patterns case by case.

Then run the EPUB-side checklist: [references/postprocess-epub.md](references/postprocess-epub.md) (markup-level cleanup: fake-heading promotion, span/font stripping, internal-link hygiene, TOC injection).

## Markdown → EPUB

```bash
./scripts/md2epub.sh <book.md>
```

Images embedded (refs resolved via `--resource-path`), chapters split at H2, metadata title/lang auto; a `cover.jpg` beside the md becomes the cover. The reader is fixed to `-f gfm` (the md is gfm-produced — the default `markdown` reader silently drops `<img>` tags, pitfall 9) and the script self-verifies the image triple: md refs = EPUB media = `<img>` in xhtml, aborting on mismatch. Obsidian callouts degrade to plain blockquotes in EPUB readers — if EPUB is the target, prefer plain blockquotes for boxed content. Formula-heavy books (数学/代数/几何/分析/物理 in the name) automatically use `--mathjax` — see the texmath pitfall below.

## Quality gates (before delivery)

- **Against the source, not just the raw output** (scanned route): every `crosscheck.py` site decided, and `apply_review.py` reporting 0 undecided. PP-only books (no VL): `orphan_check.py` reports 0 orphan lines. `fidelity_diff.py` (below) only proves cleanup didn't lose anything relative to the OCR output. It is blind to what the OCR itself dropped.
- `merge_pages.py` reports `pages N/N, none missing` (it exits 1 on gaps, **including missing trailing pages**).
- `scripts/review_gates.py <目录>` — defect-level items ($$ 配平/锚点/图片/乱码/标签配对) must be zero; structural items go to manual review.
- `scripts/heading_audit.py <book.md>` — heading-level sanity: first heading is the lone H1, no downward level skips (H2→H4), no setext leftovers, no mixed chapter levels. Heuristic — hits need semantic triage, not blind execution (正文引文含"第X章"字样和套装书有/无卷部的章级差异是已知误报源).
- `scripts/fidelity_diff.py <clean.md> <raw.md>` — content conservation vs the pre-clean output: zero unexplained deletions, table/image counts match (catches whole-table/paragraph loss no format check can see).
- Every box in the route checklist's final gate ticked ([PDF](references/postprocess-pdf.md) / [EPUB](references/postprocess-epub.md)) — heading hierarchy, TOC↔正文 1:1, spot-check against the original.
- Page anchors `<!-- 第N页 -->` stripped as the LAST post-processing step (still needed mid-pipeline for page deletion/merges/per-page math fixes). The anchored file stays an internal intermediate for page reruns; only the stripped file ships.

## Pitfalls (all hit in production)

1. **Image refs with spaces/parens break Markdown links** — `![](书名 含(括号).imgs/x.jpg)` truncates at the first space/`(`. Percent-encode in refs: space→`%20`, `(`→`%28`, `)`→`%29`; URL-decode refs before existence checks. HTML `<img src="...">` attributes tolerate spaces; Markdown destinations do not.
2. **"Delete to next heading" is a loaded gun** — front matter (版权页→总序→前言→目录) often has no headings between blocks; a section-level delete eats real content. Use line-level boundaries (stop at heading/image/TOC-entry/sentence-ending long line — `cip_clean.py` implements this) and back up before in-place rewrites (convention in batch.md §5).
3. **texmath hangs on huge formula counts** — pandoc → EPUB with default MathML rendering took 11h+ on a 500-page math book. Use `--mathjax` for formula-heavy books (reader support varies; the md keeps the LaTeX either way).
4. **Region-type labels lie** — pp_structurev3's `seal` boxes are often manga panels or content images, not stamps. "Tiny images" in publisher EPUBs are usually inline formulas (¼, C₂) — deleting them deletes characters. Near-solid-color 2×2px images, however, are decorative spacers and safe to delete.
5. **Unreferenced OCR crops pile up** — pp_structurev3 saves every region crop; typically <20% are referenced by the md. Sweep unreferenced files after delivery (24k files / 134MB per ~50 books in practice), but remember the source PDF may already be gone — those crops are the only visual originals left.
6. **Unicode filenames** — compare basenames in NFC before dedupe/collision checks; macOS stores NFD, so "Žižek.pdf" and "Žižek.epub" can look like different strings.
7. **marker on first run** — model downloads from huggingface.co can stall silently for 30+ min; check the cache dir is growing.
8. **Misplaced tables read as "garbage" and deleted** — OCR can drop a whole table into the middle of a prose paragraph; a cleanup agent judging "junk" has deleted entire tables this way (two tables of a 6th-ed textbook, recovered only from `.bak`). Table-like blocks are content: relocate, never delete (checklist §1); `fidelity_diff.py` vs the raw file is the backstop.
9. **pandoc's default reader silently drops images from gfm input** — packing a gfm-produced md with the default `markdown` reader dropped 38 of 166 `<img>` tags with zero warnings (parser-state issue on big files; minimal repros pass). Only the triple count (md refs = EPUB media = xhtml `<img>`) catches it. `md2epub.sh` now forces `-f gfm` and runs the triple check itself. Also: pandoc ≥3.9 renamed `--epub-chapter-level` to `--split-level`.
10. **fidelity_diff.py is O(n²)** — times out on 10MB-class books. The stronger big-file proof is **transform-replay**: script the edit operations, replay them on the `.bak`, and byte-compare with the new file — zero unexplained diff lines is exact conservation, and faster than fuzzy matching.
11. **The layout model silently drops whole paragraphs.** pp_structurev3 only writes text that falls inside a layout box into the md. PP-DocLayout-M misses gray-background case boxes, the right column of two-column dialogue transcripts, lines next to photos, last lines at the page bottom, and translator footnotes. The whole-page OCR did read those lines (`overall_ocr_res` has them), so `orphan_check.py` can find them. One of three 6th-edition textbooks lost 70% of a page this way, and every downstream outline and question bank lost those case studies with it.
12. **OOM silently skips pages, and the logged exit code can lie.** When paddleocr hits GPU OOM partway through a book, it writes nothing for the remaining pages. In bash, `echo "... $(date) exit=$?"` captures the exit code of `date`, not paddleocr. Capture `rc=$?` on the very next line. Missing pages at the end of a book are invisible to a min..max page-range check, so always compare against the PDF's page count (merge_pages.py does this now).
13. **Don't use `FLAGS_use_cuda_managed_memory` to dodge VRAM OOM.** On NVIDIA it spills overflow into system RAM. On a 15GB laptop that triggered a global OOM that killed WeChat, Steam, and the terminal running the agent. Shrink the model's VRAM instead (bf16, load weights to RAM first, smaller batches), and keep long runs inside a `systemd-run --scope -p MemoryMax=` (pdf_ocr.sh does this).
14. **PaddleOCR-VL on 6GB.** Stock loading copies the whole checkpoint into VRAM, upcasts the visual encoder to fp32 on the GPU, and peaks above 5.6GB, so it OOMs. `paddleocr_lowvram.py` loads weights into RAM first and keeps the whole model bf16 (the checkpoint ships in bf16), which brings it to 1.8GB resident and a 3.7GB peak. Separately, VL's local backend can deadlock in a GPU kernel on some pages. Run it with `CUDA_LAUNCH_BLOCKING=1`; the pdf_ocr.sh watchdog is the backstop (Step 2). Debugging: `B2M_DEBUG_VL=1` makes the wrapper print per-block generation time and a stack dump every minute, and `kill -USR1 <pid>` dumps all thread stacks on demand.
15. **PP text detection OOMs at 300 DPI.** The default `limit_type=min, limit_side_len=736` never downscales a page whose short side is already >736 px, so detection runs on the full ~2400×3000 image. pdf_ocr.sh passes `--text_det_limit_type max --text_det_limit_side_len 2400`.
16. **NixOS**: paddle needs `LD_LIBRARY_PATH=/run/opengl-driver/lib`, otherwise `libcuda.so.1` can't be found and preflight misreports "no GPU". Scripts use `#!/usr/bin/env bash` because `/bin/bash` doesn't exist there. Both pdf_ocr.sh and preflight.sh handle the library path.
17. **VL "corrects" the original.** Being a language model, it nudges rare or misprinted wording toward the common form: 迷团→谜团, 表露→透露, 原书误印"过估估计"→过估计, a hyphenated "Rich-ardo" → Richard. Single-engine output cannot reveal this. The PP cross-check catches it because PP reads glyph by glyph. For study material, where exact wording matters, don't skip the cross-check.
18. **The book's own misprints: VL and the vision subagent "fix" them together.** The family-therapy book prints dozens of 入 as 人 (卷人、介人、陷人、引人…, ~120 places against ~280 correct). VL reads them as 入 from context, and deepseek, re-checking from the crops, mostly agreed with VL (108/111). Under 600 DPI you can see the glyph is 人: in this font 入 starts its left stroke low and short, while these start high and run long. Calibration on everyday text can't catch this. On similar-shape pairs where only one reading is a real word (入/人、己/已、干/于), a language model is pulled by context, so the main model has to sample them at high resolution against a known-good 入 from the same book. Whether to fix the book's misprints is a separate decision for the user. Review records only what's printed.
19. **VL fills in across page breaks.** The page is the processing unit, so VL can't see the next page. When a sentence breaks at the page edge, it sometimes completes it: the end of a page reads "知觉、记" and VL writes "记忆和感受", while the next page actually starts "忆、想象和思考". A word split at the top of a page gets doubled: "这位老" + the next page's "师" → "老师师". PP doesn't do this. In the cross-check it shows up as a short span that only VL has, so it ends up in review. A reviewer who looks only at the crop will rule it correct (the crop has the first half and the invented part reads naturally), so when a disagreement sits at the very start or end of a page, check the neighbouring page too.
20. **Coverage gates pass while text sits in the wrong place.** After all three 347 books passed "uncovered = 0 + pilot gold standard 0.1%", page-by-page alignment still found: periods stranded as their own paragraph (~45), sentences split into three paragraphs by mid-line inserts (~130), half-sentences inserted after the wrong anchor, inserted formula LaTeX fragments next to the formula image, truncated footnotes, and review decisions the patch guards silently dropped (泪丧, 慈普, 宜布, 困感…). Coverage asks "is every 8-gram somewhere in the book", which is blind to order and position. Run the four post-patch gates (seam/align/decision/new_doubles) before installing. Count them per book; zero is not expected for index/bibliography pages, but body-page hits each need a look.
21. **VL also misreads "一" as a dash.** The reverse of PP's dash→"一" habit (the pre-pass above): "一妻多夫", "一一对应" came out as "—妻多夫", "—一对应". The dash prefill (PP-is-wrong) then wrote the dash into the md. crosscheck now sends dash sites where the next character forms a common 一-word (一个/一种/一对/一妻…) to image review instead of prefilling.
