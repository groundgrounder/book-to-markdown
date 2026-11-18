# Scanned-PDF Dual-Engine OCR Pipeline

Detailed reference for the scanned-PDF route (`PaddleOCR-VL` primary + `pp_structurev3` cross-check). Read this before running OCR jobs, configuring low-VRAM/CPU tiers, or reviewing `crosscheck.py` output.

## Why Dual-Engine Cross-Checking

Single-engine OCR drops content silently. In a 2026-10-20 page-by-page gold-standard pilot (3 scanned textbooks, 29 pages), `fidelity_diff.py` only compared against raw OCR output and could not see paragraphs the OCR missed completely:

| Setup | Dropped paragraphs | Char error | Dropped English spaces |
|---|---|---|---|
| Old: PP balanced (`DocLayout-M`) | 9.2% (12% on hard pages) | 0.17% | 6 |
| PP + `PP-DocLayout_plus-L` | 0.3% (1 table row) | 0.15% | 8 |
| `PaddleOCR-VL-1.6` | 0.1% (2 index items) | 0.04–0.06% | 1 |
| VL primary + PP cross-check + image review | 0 | 0 | — |

The two engines fail in complementary ways:
- **PaddleOCR-VL** is language-model-backed and nudges rare or misprinted text toward common wording (`迷团→谜团`, `表露→透露`, original misprint `过估估计→过估计`, hyphenated `Rich-ardo→Richard`), and occasionally skips index entries.
- **pp_structurev3 (PP)** reads glyph by glyph, catching VL's over-corrections, while tending to misread `—` as `一`, pull margin page numbers into prose, misread rare glyphs (`癔→意`), and drop spaces in English text.

Cross-checking narrows image review to disagreements. Pilot numbers are a baseline, not a zero-error guarantee: shared misreadings, original-print typos, and layout boundaries still require targeted spot-checks.

## Device Tiers and Configs

`preflight.sh` selects the `pp_structurev3` config tier; primary engine `PaddleOCR-VL` needs ≥6 GB VRAM (<10 GB runs automatically through `scripts/paddleocr_lowvram.py`):

| Tier | Hardware | Config | Notes |
|---|---|---|---|
| `full` | GPU ≥16 GB or CPU | `configs/paddlex_full.yaml` | `DocLayout_plus-L` + server rec + SLANeXt, batch 8 |
| `balanced` | GPU 6–16 GB | `configs/paddlex_balanced.yaml` + `--precision fp16` | Same models as `full`, batch 1 (fits in 6 GB) |
| `lite` | GPU <6 GB | `configs/paddlex_lite.yaml` + `--precision fp16` | Mobile rec + `DocLayout-M`; **drops whole paragraphs**, must run `orphan_check.py` |

Never downgrade the layout model (`DocLayout_plus-L` → `DocLayout-M`) just to save VRAM; reduce batch size instead.

### Low-VRAM and No-GPU Execution

- **6 GB VRAM**: Stock PaddleOCR-VL loads checkpoints into VRAM and upcasts the visual encoder to fp32 (>5.6 GB peak, causing OOM). `scripts/paddleocr_lowvram.py` loads weights in RAM first and keeps bf16 end-to-end (~1.8 GB resident, ~3.7 GB peak).
- **Avoid `FLAGS_use_cuda_managed_memory`**: On NVIDIA it spills VRAM overflow into system RAM, which can trigger a global OS OOM and kill the terminal/session.
- **<6 GB VRAM or CPU only**: Run PP alone (`--engine pp`), then **must** run:
  ```bash
  "$SKILL_DIR/scripts/orphan_check.py" "$W/pp/<book_name>"
  ```
  It compares `overall_ocr_res` against layout blocks to catch silently dropped paragraphs (case boxes, two-column dialogue right columns, lines beside photos, bottom lines, translator footnotes).
- **CPU speed**: Typically 10–30 s/page; best suited for short books or sample pages, paired with resumable runs.
- **6 GB RTX 4050 benchmark** (100 consecutive pages): VL ~12 s/page, PP ~1.8 s/page (~2 hours for both engines on a 500-page book).

## Execution, Watchdog, and Long Runs

```bash
W=<work_dir>   # Non-synced directory: rendered pages + dual outputs (~1 GB per book)
"$SKILL_DIR/scripts/pdf_ocr.sh" book.pdf "$W/vl" --engine vl
"$SKILL_DIR/scripts/pdf_ocr.sh" book.pdf "$W/pp" --engine pp --config "$SKILL_DIR/configs/paddlex_balanced.yaml" --device gpu --precision fp16
```

- **Rendering & Resumability**: `pdf_ocr.sh` renders all pages to PNG at `scale 2.0` (144 DPI; 300 DPI measured no better for either engine). Completed pages with `res.json` are skipped on rerun. Each page gets its own `pages/pNNNN/` directory because crop filenames only encode box coordinates. The script verifies every page produced output at exit (exits 1 otherwise).
- **Watchdog & GPU Kernel Stalls**: PaddleOCR-VL's local backend can freeze inside an async GPU op (100% CPU, 0% GPU). `pdf_ocr.sh` sets `CUDA_LAUNCH_BLOCKING=1` (fixed 4/5 failure rate on test pages to 3/3 pass) and runs a stall watchdog (`STALL=300` seconds default). Stalled batches dump stacks to `ocr.log`, terminate, and retry the single page; a second failure logs to `bad_pages` and skips. Three consecutive bad pages abort the run. Backfill any `bad_pages` by copying the corresponding page directory from the PP run.
- **Debugging VL stalls**: `B2M_DEBUG_VL=1` logs per-block generation time and minute stack dumps; `kill -USR1 <pid>` dumps all thread stacks on demand.
- **Useful flags**:
  - `--formula`: Math-heavy books on PP only. Off by default because the 713 MB formula model warmup can exhaust system RAM. VL handles formulas natively (not yet benchmarked on math-heavy books).
  - `--render SCALE`: Lower for oversized pages (>800 pt wide; `preflight.sh` warns), otherwise vision-model cost spikes 10–20×.
  - PP detection limit: `pdf_ocr.sh` already passes `--text_det_limit_type max --text_det_limit_side_len 2400` to avoid 300 DPI detection OOMs.
- **Background & Memory Safety**: Launch long runs with `nohup ... & disown` so the launcher returns immediately. On Linux, `pdf_ocr.sh` uses `systemd-run --user --scope -p MemoryMax=<half of RAM>` when available so OOM kills only the OCR scope. On macOS, use `caffeinate -dims -w <pid>` and AC power (battery lid-close sleeps regardless). NixOS `LD_LIBRARY_PATH=/run/opengl-driver/lib` is handled automatically by `pdf_ocr.sh` and `preflight.sh`.

## Cross-Checking and Image Review

```bash
"$SKILL_DIR/scripts/crosscheck.py" "$W/vl/<book_name>" "$W/pp/<book_name>" "$W/review" --pdf book.pdf
# Review $W/review/sheets/*.png and fill primary / secondary / =text in sites.tsv
"$SKILL_DIR/scripts/apply_review.py" "$W/review/sites.tsv" "$W/vl/<book_name>"
"$SKILL_DIR/scripts/merge_pages.py" <out.md> "$W/vl/<book_name>"
```

- **What `crosscheck.py` flags**: Missing spans (`drop`), extra spans (`extra`), VL repetition loops, and short character differences. `pagenum`/`dash`/`digit` default to primary except where `—` is followed by common `一`-words (`一个/一种/一对/一妻…`), which go to image review.
- **Review load**: ~0.4 sites/page on ordinary pages (in a 100-page test: 38 sites, 12 real VL errors such as dropped line-end characters, `闵→冈`, `vol. 1→vol. I`), ~1.1 sites/page on dense pages (case boxes, tables, indices).
- **Hidden OCR layer in source PDF**: Passing `--pdf book.pdf` lets `crosscheck.py` use an existing embedded OCR text layer as a free third reference for catching dropped paragraphs.
- **Unaligned pages (`未对齐`)**: Pages with >5% reading-order disagreement (indices, tables, two-column dialogue) can hide short errors inside large shifts — inspect those pages whole.
- **Crop verification**: `recheck_sheets.py` records page/site/bounds/input hashes; ambiguous or missing crop anchors fall back to a full page marked `UNLOCATED`.
- **Optional lightweight vision reviewer**: Reviewing sheets requires looking at the page images. When authorized and within budget, you can pre-screen sheets with a cheaper vision model/subagent (in a 34-site calibration, a lightweight vision model answered 30 and got 27 right, missing 3 italic `vol. 1` → `I` glyphs where language priors override ambiguous ink):
  - Dispatch **small batches (≤2–3 sheets per agent)** and append after each sheet so API resets do not lose hours of work.
  - Have it output `#ID A|B|N|? 原文`, then run:
    ```bash
    "$SKILL_DIR/scripts/review_fill.py" "$W/review/sites.tsv" answers.txt
    ```
  - `review_fill.py` writes `recheck.txt` containing all `?`/`N` sites, any site with Latin letters or digits, and a random 10% sample. The main model re-checks only `recheck.txt`.

## OCR-Specific Pitfalls

1. **Unreferenced OCR crops pile up**: `pp_structurev3` saves crops for every region, though <20% are typically referenced by the Markdown. Sweep unreferenced crops only **after** delivery — if the source PDF is removed later, those crops are the only remaining visual originals.
2. **Original-print misprints vs. OCR errors**: On similar-shape pairs where only one form is a common word (`入/人`, `己/已`, `干/于`), both VL and lightweight vision reviewers get pulled by context (in one 400+ page book with ~120 printed `入→人` typos, a lightweight vision reviewer agreed with VL's silent "fix" 108/111 times). Sample suspicious pairs at high resolution (e.g. 600 DPI) against a confirmed glyph from the same book. Review records what is printed; normalizing original-print typos requires explicit user approval.
3. **VL hallucinates across page breaks**: Because each page is processed independently, VL sometimes completes a trailing fragment (`知觉、记` → `记忆和感受` when the next page starts `忆、想象和思考`) or doubles a split character across pages (`这位老` + `师` → `老师师`). Always check the neighboring page when a disagreement sits at the top or bottom edge of a page.
4. **VL also misreads `一` as `—`**: The mirror image of PP's `—→一` habit (`一妻多夫` → `—妻多夫`). `crosscheck.py` routes `—` followed by common `一`-words to image review instead of auto-prefilling.
