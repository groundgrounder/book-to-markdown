# book-to-markdown

**English** | [简体中文](README.zh-CN.md)

Turn scanned PDFs, text-layer PDFs, and EPUBs into clean, single-file Markdown—with images, heading hierarchy, and a nested table of contents.

An agent skill for **Claude Code, Codex, and pi**. Give your agent a book and an output path; it handles environment checks, route selection, conversion, cleanup, and validation.

## How it works

| Input | Conversion route | What the workflow does |
| --- | --- | --- |
| Scanned PDF | PaddleOCR-VL + pp_structurev3 | Cross-checks two OCR engines and reviews their disagreements against the source page. |
| Text-layer PDF | marker | Uses embedded text to preserve headings, tables, formulas, and images without unnecessary OCR. |
| EPUB | pandoc | Extracts digital text and images, then cleans up markup. |

Also supports resumable bookshelf batches, reviewed re-OCR patches for existing Markdown, and Markdown → EPUB export.

**Pilot & batch experience:** validated in a 277-book / 87k-page batch workflow, with a page-by-page gold-standard pilot (3 scanned textbooks, 29 pages) reducing paragraph loss from 9.2% (single-engine legacy layout) to 0% after dual-engine review. Shared OCR mistakes and original misprints still require spot-checks against the book.

## Install

```bash
npx skills add groundgrounder/book-to-markdown -g
```

Or simply ask your agent:

```text
Install the skill from https://github.com/groundgrounder/book-to-markdown
```

<details>
<summary>Manual install or one-off use</summary>

- **Manual:** clone the repo into `~/.claude/skills/book-to-markdown/` (Claude Code), `~/.codex/skills/book-to-markdown/` (Codex), or `~/.agents/skills/book-to-markdown/` (pi), then start a new session (or `/reload` in pi).
- **Without installing:** ask an agent with local file and shell access to read `/path/to/book-to-markdown/SKILL.md` and follow its workflow.

</details>

## Usage

> Before a paid conversion, set a hard usage or spending limit in your agent host or API provider dashboard if available, and agree on a total task budget—retries and image review can consume many tokens.

Ask your agent directly (or start with `/book-to-markdown`, `$book-to-markdown`, or `/skill:book-to-markdown`):

- **Convert a book** (PDF or EPUB; scanned PDFs need a vision-capable model):
  ```text
  Convert /path/to/book.pdf to Markdown in /path/to/output.
  ```
- **Convert a bookshelf** (resumable batch plan):
  ```text
  Use book-to-markdown to convert the PDF and EPUB books in /path/to/books in resumable batch mode.
  ```
- **Re-OCR an already-cleaned Markdown file**:
  ```text
  Use book-to-markdown to re-OCR /path/to/book.pdf and patch /path/to/cleaned.md.
  ```

Your agent runs the preflight check and route setup automatically. To inspect hardware and disk space manually beforehand (read-only):

```bash
bash /path/to/book-to-markdown/scripts/preflight.sh /path/to/books
```

## Requirements

- An agent with access to your books, a macOS or Linux shell (WSL on Windows), and an output directory; scanned-PDF review also requires image inspection.
- Bash and Python. **Only scanned PDFs require Python 3.12 (via `uv`), PaddleOCR, and PaddlePaddle**—EPUB (`pandoc`) and text-layer PDF (`marker-pdf` + Poppler) routes do not.
- Models for `marker` and OCR download on first use.
- For PaddleOCR-VL, a GPU with at least 6 GB VRAM is recommended. `pp_structurev3` runs on CPU at ~10–30 s/page, which is best suited for short books or sample pages.

Agent access and model/API costs depend on your chosen host and provider.

## Documentation

[SKILL.md](SKILL.md) is the agent entry point with route selection, core commands, and quality gates. Route-specific details live in `references/` (which retain their original language, mostly Chinese):

- [setup.md](references/setup.md) — first-time environment setup.
- [ocr-pipeline.md](references/ocr-pipeline.md) — dual-engine scanned-PDF workflow, low-VRAM/CPU tiers, watchdog, and image review.
- [postprocess-pdf.md](references/postprocess-pdf.md) / [postprocess-epub.md](references/postprocess-epub.md) — cleanup and review checklists.
- [batch.md](references/batch.md) — resumable bookshelf processing.
- [patch-control.md](references/patch-control.md) — patching previously cleaned Markdown with reviewed OCR.

## Reading the output

For reading long converted Markdown books on macOS, [Hortus](https://github.com/groundgrounder/Hortus) is a native Mac Markdown reader (Rust core, no WebView) that also renders large Mermaid diagrams in columns so surrounding notes stay readable.

## License

[MIT](LICENSE)
