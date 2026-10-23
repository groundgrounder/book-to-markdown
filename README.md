# book-to-markdown

**English** | [简体中文](README.zh-CN.md)

Convert books to clean single-file Markdown — scanned PDFs, text-layer PDFs, and EPUBs — with images, heading hierarchy, and a nested table of contents.

[TODO: comparison image]

## Why

- **Scanned PDFs:** PaddleOCR-VL as the primary engine, cross-checked against pp_structurev3. Review disagreements against the page image instead of rereading every page. Pilot: 3 textbooks, 29 pages, 0% paragraph loss after review. This is a pilot result; shared OCR mistakes still need spot-checks.
- **Text-layer PDFs:** marker preserves headings, tables, formulas, and images without unnecessary OCR.
- **EPUBs:** pandoc extracts digital text and images, followed by lightweight markup cleanup.
- **Resumable:** scanned-PDF jobs skip completed pages after a crash. A batch workflow handles whole bookshelves.

## Quick Start

Run these commands from the repository root.

### 1. Install

Install the OCR environment with [uv](https://docs.astral.sh/uv/); on an NVIDIA GPU machine, replace `paddlepaddle` with `paddlepaddle-gpu`.

```bash
uv tool install --python 3.12 paddleocr --with paddlepaddle
uv pip install --python ~/.local/share/uv/tools/paddleocr/bin/python 'paddlex[ocr]' python-docx
```

Install pandoc for EPUBs and Poppler for PDFs with your package manager; add `marker-pdf` for text-layer PDFs. See [setup.md](references/setup.md) for environment details.

### 2. Check your environment

```bash
./scripts/preflight.sh /absolute/path/to/books
```

Preflight checks the OCR environment and prints device-specific recommendations and scanned-PDF commands; it does not install dependencies.

### 3. Convert one book

Start with an EPUB (use an absolute input path):

```bash
./scripts/epub2md.sh /absolute/path/to/book.epub "$PWD/out"
```

The result is `out/book/book.md`, with extracted images alongside it. Follow the [EPUB checklist](references/postprocess-epub.md) to finish the cleanup. For PDFs, follow the [route selection and OCR workflow](SKILL_DEV.md#step-1-detect-the-route-pdfs-only), then the [PDF checklist](references/postprocess-pdf.md). Conversion produces a draft; review and cleanup complete the book.

## Full Documentation

The guides in `references/` retain their original language (mostly Chinese):

- [setup.md](references/setup.md) — first-time installation.
- [postprocess-pdf.md](references/postprocess-pdf.md) / [postprocess-epub.md](references/postprocess-epub.md) — cleaning the output.
- [batch.md](references/batch.md) — processing many books with resumable queues.
- [patch-control.md](references/patch-control.md) — re-OCR a book that has already been cleaned.

[SKILL_DEV.md](SKILL_DEV.md) contains the internal Claude Code skill workflow, dual-engine details, quality gates, and known pitfalls.

## Reading the output

[Hortus](https://github.com/groundgrounder/Hortus) renders large Mermaid diagrams in columns so the text stays readable. It is a native Mac app with a Rust core and no WebView.

## Requirements

- Python 3.12, managed with uv, and Bash.
- PaddleOCR with PaddlePaddle and the `paddlex[ocr]` extras for scanned PDFs. A GPU with at least 6 GB VRAM is recommended for PaddleOCR-VL; the pp_structurev3 CPU fallback is slower. Models download on first use.
- `marker-pdf` (`marker_single`) for text-layer PDFs.
- pandoc for EPUB conversion; Poppler (`pdftotext`, `pdfimages`, `pdffonts`) for PDF inspection. Install these separately; preflight does not install them.

## License

[MIT](LICENSE)
