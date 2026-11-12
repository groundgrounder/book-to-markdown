# book-to-markdown

**English** | [简体中文](README.zh-CN.md)

Turn scanned PDFs, text-layer PDFs, and EPUBs into clean, single-file Markdown—with images, heading hierarchy, and a nested table of contents.

An agent skill for **Claude Code, Codex, and pi**. Give your agent a book and an output location; it handles environment checks, route selection, conversion, cleanup, and validation.

## How it works

| Input | Conversion route | What the workflow does |
| --- | --- | --- |
| Scanned PDF | PaddleOCR-VL + pp_structurev3 | Cross-checks two OCR engines and reviews their disagreements against the source page. |
| Text-layer PDF | marker | Uses the embedded text to preserve headings, tables, formulas, and images without unnecessary OCR. |
| EPUB | pandoc | Extracts digital text and images, then cleans up the markup. |

The skill also supports resumable bookshelf batches, reviewed re-OCR patches for existing Markdown, and Markdown → EPUB export.

**Pilot result:** after dual-engine review, a 3-textbook, 29-page pilot had 0% paragraph loss. This small pilot is not a guarantee of error-free output; shared OCR mistakes and other source mismatches still require spot-checks against the book.

## Quick start

### 1. Clone and install

```bash
git clone https://github.com/groundgrounder/book-to-markdown.git
```

Then ask your agent:

```text
Install the book-to-markdown skill from /absolute/path/to/book-to-markdown
into your personal skills directory. Keep SKILL.md, SKILL_DEV.md, scripts/,
references/, configs/, and LICENSE together with their relative paths intact.
Tell me when it is available and how to invoke it.
```

| Agent | Personal skill directory | Start your request with |
| --- | --- | --- |
| Claude Code | `~/.claude/skills/book-to-markdown/` | `/book-to-markdown` |
| Codex | `~/.codex/skills/book-to-markdown/` | `$book-to-markdown` |
| pi | `~/.agents/skills/book-to-markdown/` | `/skill:book-to-markdown` |

Open a fresh agent session after installation; in pi, you can also use `/reload`. The agent can select the skill for book-conversion requests, or you can invoke it explicitly. See the host documentation for [Claude Code](https://code.claude.com/docs/en/skills), [Codex](https://developers.openai.com/codex/skills/), and [pi](https://github.com/badlogic/pi-mono/blob/main/packages/coding-agent/docs/skills.md).

For one-off use without installation, ask an agent with local file and shell access to read `/absolute/path/to/book-to-markdown/SKILL.md` and follow its workflow.

### 2. Check your environment

```bash
bash /absolute/path/to/book-to-markdown/scripts/preflight.sh /absolute/path/to/books
```

Preflight is read-only: it reports hardware, available tools, disk space, and recommended OCR settings. It does not install dependencies. On a new machine, follow the [setup guide](references/setup.md) for the tools needed by your route.

### 3. Convert your first book

> Before a paid conversion, set a hard usage or spending limit in your agent host or API provider dashboard if available. For paid or multi-book work, also agree on a total task budget: retries and image review can consume many tokens.

Send your agent a request like this, replacing the paths with your own:

```text
Convert /absolute/path/to/book.pdf to a single Markdown file in
/absolute/path/to/output, with images in an adjacent folder.
Check the environment, set up the dependencies needed for this book, and
choose the conversion route. Preserve headings, tables, formulas, and images.
Keep the source file. Finish the cleanup and validation, and report anything
that still needs review.
```

The same request works for an EPUB. Your agent handles the commands. For scanned PDFs, use an agent or model that can inspect page images so OCR disagreements can be reviewed against the source.

## More workflows

Convert a whole bookshelf with a resumable plan:

```text
Use book-to-markdown to convert the PDF and EPUB books in /absolute/path/to/books.
Create a resumable batch plan first. Agree the total budget before paid calls,
keep the source files, and report each book's completion and review status.
```

Re-OCR a book without rebuilding its existing structure:

```text
Use book-to-markdown to re-OCR /absolute/path/to/book.pdf and patch
/absolute/path/to/cleaned.md. Preserve its existing structure and formatting.
Use reviewed OCR, back up the original, and validate every changed region.
```

## Requirements

- An agent with access to your books, a shell, and an output directory; scanned-PDF review also requires image inspection.
- Bash and Python. The OCR setup uses Python 3.12 via uv.
- The route-specific tools listed above. Models download on first use.
- For PaddleOCR-VL, a GPU with at least 6 GB VRAM is recommended. The pp_structurev3 CPU fallback is slower.

Agent access and model/API costs depend on your chosen host and provider.

## Documentation

[SKILL.md](SKILL.md) is the agent entry point. [SKILL_DEV.md](SKILL_DEV.md) contains the complete workflow and quality gates. The guides in `references/` retain their original language, mostly Chinese:

- [setup.md](references/setup.md) — first-time environment setup.
- [postprocess-pdf.md](references/postprocess-pdf.md) / [postprocess-epub.md](references/postprocess-epub.md) — cleanup and review checklists.
- [batch.md](references/batch.md) — resumable bookshelf processing.
- [patch-control.md](references/patch-control.md) — patching previously cleaned Markdown with reviewed OCR.

## Reading the output

[Hortus](https://github.com/groundgrounder/Hortus) renders large Mermaid diagrams in columns so the surrounding text stays readable.

## License

[MIT](LICENSE)
