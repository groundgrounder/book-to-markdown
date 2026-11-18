---
name: book-to-markdown
description: Convert scanned PDFs, text-layer PDFs, and EPUBs to clean single-file Markdown with images, heading hierarchy, and nested TOC, plus Markdown to EPUB, re-OCR patching, and resumable bookshelf batches. Use when converting 电子书/教材/扫描版 PDF/EPUB to Markdown or cleaning up OCR'd book text.
license: MIT
---

# book-to-markdown

Routes: **EPUB → pandoc** (`epub2md.sh`), **text-layer PDF → marker**, **scanned PDF → PaddleOCR-VL + pp_structurev3**, **cleaned Markdown re-OCR → patch**, **Markdown → EPUB** (`md2epub.sh`).

## Conventions and Contract

- **Paths**: Resolve all bundled scripts, references, and configs relative to this skill directory (`SKILL_DIR`). Use absolute paths for the user's books, work directory, and outputs.
- **Cost & Delegation**: For paid or multi-book jobs, agree the total budget before paid calls (main session, text/image review, retries, OCR APIs). When metering is unavailable, disclose it and cap batches, context, output, and retries; stop before exceeding the approved envelope. Delegate only when authorized and within model/cost limits; export bounded finding packets instead of whole-book dumps.
- **Acceptance**: Running gates is not passing them. Every in-scope finding must be fixed and rechecked or backed by per-finding evidence; pending, unlocated, or deferred body findings block delivery.
- **Bookshelf batches**: More than a handful of books → read [references/batch.md](references/batch.md) first (manifest, resumable queues, multi-machine coordination).

## Step 0: Preflight

```bash
"$SKILL_DIR/scripts/preflight.sh" <bookshelf_or_dir>
```

Inspects device tier (`full`/`balanced`/`lite`/CPU), disk space, HuggingFace/mirror reachability, power state, NFC same-name PDF+EPUB collisions, and oversized pages (>800 pt). First run on a new machine → [references/setup.md](references/setup.md) (PaddleOCR/PaddlePaddle are needed **only** for scanned PDFs).

## Step 1: Detect the Route

- **EPUB** → Route A (`epub2md.sh`).
- **Already-cleaned Markdown needing re-OCR** → Route D (patch route).
- **Markdown → EPUB** → Route E (`md2epub.sh`).
- **PDF** → Sample 15 pages at the 10% mark:
  ```bash
  pdftotext -f <10%_page> -l <+15_pages> book.pdf - | tr -d '[:space:]' | wc -c
  ```
  - **<100 chars**, **garbled text**, or **repeating watermark phrases only** → Route C (scanned OCR).
  - **>2000 clean chars** → verify it is genuine typeset text, not a third-party hidden OCR layer:
    ```bash
    pdfinfo book.pdf | grep -E 'Producer|Creator'   # ABBYY / Paper Capture / calibre / Pdg2Pic / FreePic2Pdf
    pdffonts -l 5 book.pdf                          # HiddenHorzOCR / GlyphLessFont / unembedded MingLiU
    pdfimages -f 30 -l 31 -list book.pdf            # One full-page image (~300 ppi) per page = scan
    ```
    - Any hidden-OCR hit → **Route C** (third-party OCR layers ran 2–5% character error in pilot tests; pass `--pdf book.pdf` to `crosscheck.py` so that layer becomes a free third reference for dropped paragraphs).
    - Clean typeset PDF → **Route B** (`marker`). If marker mangles the layout, fall back to Route C.

## Step 2: Execute Conversion

### Route A: EPUB → Markdown

```bash
"$SKILL_DIR/scripts/epub2md.sh" <book.epub> <outdir>
```

Uses `pandoc -t gfm --wrap=none --extract-media=media` and strips anchor/SVG/hard-break noise. Unsemantic EPUBs using `<font size>` + bold produce no `#` headings initially (normal). Complete [references/postprocess-epub.md](references/postprocess-epub.md) before delivery.

### Route B: Text-Layer PDF → Markdown

```bash
marker_single <book.pdf> --output_dir <outdir> --disable_ocr
# If huggingface.co is unreachable: export HF_ENDPOINT=https://hf-mirror.com
```

`--disable_ocr` reuses embedded text (~4× faster). Proceed to Step 3 (page-bottom footnotes interrupting paragraphs are the main issue here).

### Route C: Scanned PDF → Markdown (Dual-Engine OCR)

Single-engine OCR drops paragraphs silently (12% on hard pages in pilot testing). Cross-checking `PaddleOCR-VL` (primary, contextual) against `pp_structurev3` (glyph-by-glyph) narrows image review to disagreements (~0.4–1.1 sites/page; 0% paragraph loss after review in pilot, though shared misreadings and original misprints still need spot-checks).

**Read [references/ocr-pipeline.md](references/ocr-pipeline.md) before launching OCR** for device-tier configs, low-VRAM/CPU rules (`orphan_check.py`), watchdog/long-run handling, and vision-review batching.

```bash
W=<non_synced_work_dir>   # ~1 GB per book for rendered PNGs + dual outputs
"$SKILL_DIR/scripts/pdf_ocr.sh" book.pdf "$W/vl" --engine vl
"$SKILL_DIR/scripts/pdf_ocr.sh" book.pdf "$W/pp" --engine pp --config "$SKILL_DIR/configs/<tier>.yaml" --device <gpu|cpu> [--precision fp16]
"$SKILL_DIR/scripts/crosscheck.py" "$W/vl/<book_name>" "$W/pp/<book_name>" "$W/review" --pdf book.pdf
# Inspect $W/review/sheets/*.png (and full 未对齐 pages); record primary / secondary / =text in sites.tsv
"$SKILL_DIR/scripts/apply_review.py" "$W/review/sites.tsv" "$W/vl/<book_name>"
"$SKILL_DIR/scripts/merge_pages.py" <out.md> "$W/vl/<book_name>"
```

Then proceed to Step 3.

### Route D: Re-OCR Patch on Cleaned Markdown

Keep the existing cleaned Markdown as skeleton and patch it from **reviewed** OCR (`crosscheck.py` → `apply_review.py` first). **Read [references/patch-control.md](references/patch-control.md)** for `patch_cleaned.py --verify --careful`, bounded exact edits (`apply_exact.py`, `join_split.py`, `format_inserts.py`), evidence packets (`review_contract.py`), and the four required post-patch gates (`seam_check.py`, `align_check.py`, `decision_check.py`, `new_doubles.py`).

### Route E: Markdown → EPUB

```bash
"$SKILL_DIR/scripts/md2epub.sh" <book.md> [--mathjax]
```

Forces `-f gfm` (the default `markdown` reader silently drops `<img>` tags) and runs a triple image check (`md refs = EPUB media = xhtml <img>`). Splits at H2, auto-sets title/lang, and uses an adjacent `cover.jpg`. Prefer plain blockquotes over Obsidian callouts if EPUB is the target. Formula-heavy books with non-Chinese filenames should pass `--mathjax` (MathML conversion can stall for hours).

## Step 3: PDF Post-Processing (Routes B & C)

Run the conservative mechanical scripts first, then **always** complete [references/postprocess-pdf.md](references/postprocess-pdf.md):

```bash
"$SKILL_DIR/scripts/polish_book.py" <book.md>
"$SKILL_DIR/scripts/toc_fix.py" <book.md>
"$SKILL_DIR/scripts/cip_clean.py" <book.md>
"$SKILL_DIR/scripts/fidelity_diff.py" <clean.md> <raw.md>
"$SKILL_DIR/scripts/review_gates.py" <dir>
```

## Step 4: Quality Gates (Before Delivery)

- **Source completeness (Route C)**: Every `crosscheck.py` site decided (`apply_review.py` reports 0 undecided) and `未对齐` pages inspected whole; PP-only runs report 0 from `orphan_check.py`; `merge_pages.py` reports `pages N/N, none missing`.
- **Route D**: All four post-patch gates (`seam_check.py`, `align_check.py`, `decision_check.py`, `new_doubles.py`) pass on the unchanged final candidate with zero pending body findings.
- **Format & structure**: `review_gates.py` defect-level items = 0; `heading_audit.py` hits triaged; `fidelity_diff.py` shows zero unexplained deletions and matching table/image counts (for ~10 MB+ files where `fidelity_diff.py` times out, verify by replaying scripted edits on `.bak` and byte-comparing).
- **Checklist & anchors**: Every item in the route checklist ([PDF](references/postprocess-pdf.md) / [EPUB](references/postprocess-epub.md)) checked; `<!-- 第N页 -->` anchors stripped as the final step (keep the anchored intermediate internally only).

## Cross-Route Pitfalls

- **Spaces/parens in Markdown image links**: Percent-encode ` ` → `%20`, `(` → `%28`, `)` → `%29` in Markdown destinations; URL-decode before existence checks.
- **Front-matter boundaries**: Never delete "to next heading" in unheaded front matter; use line-level stop conditions (`cip_clean.py`) and back up before in-place edits.
- **Misleading labels and misplaced tables**: `pp_structurev3` `seal` boxes can be manga panels or figures; tiny EPUB images are often inline formulas (only ~2×2 px solid spacers are junk); table-like blocks dropped mid-paragraph are real content — relocate, never delete.
- **Unicode normalization**: Compare filenames in NFC before dedupe/collision checks (macOS stores NFD).
