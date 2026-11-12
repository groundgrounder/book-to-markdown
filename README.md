# book-to-markdown

**English** | [简体中文](README.zh-CN.md)

> Before starting a conversion, set a hard usage or spending limit in your agent host or API provider dashboard if available. Treat this as a safety cap in addition to an agreed task budget: a model can get stuck retrying or over-reviewing and consume many tokens.

An agent skill for **Claude Code, Codex, and pi** that turns scanned PDFs, text-layer PDFs, and EPUBs into clean Markdown, with images, heading hierarchy, and a nested table of contents.

Give your agent a book and an output location. The skill guides it through environment checks, route selection, conversion, OCR review, cleanup, and validation.

[TODO: comparison image]

## Install the skill

Download or clone this repository locally, then ask your agent:

```text
Install the book-to-markdown skill from /absolute/path/to/book-to-markdown
into your personal skills directory. Keep SKILL.md, SKILL_DEV.md, scripts/,
references/, configs/, and LICENSE together with their relative paths intact.
Tell me when it is available and how to invoke it.
```

Use the location and invocation for your agent:

| Agent | Personal skill directory | Start your request with |
| --- | --- | --- |
| Claude Code | `~/.claude/skills/book-to-markdown/` | `/book-to-markdown` |
| Codex | `~/.codex/skills/book-to-markdown/` | `$book-to-markdown` |
| pi | `~/.agents/skills/book-to-markdown/` | `/skill:book-to-markdown` |

Open a fresh agent session after installation; in pi, you can also use `/reload`. The agent can then read the skill's description and select it for book-conversion requests, or you can invoke it explicitly as shown above. See the host documentation for [Claude Code](https://code.claude.com/docs/en/skills), [Codex](https://developers.openai.com/codex/skills/), and [pi](https://github.com/badlogic/pi-mono/blob/main/packages/coding-agent/docs/skills.md).

For a one-off task without installation, tell any agent with local file and shell access:

```text
Read /absolute/path/to/book-to-markdown/SKILL.md and follow its workflow
for the book-conversion request below.
```

## Ask your agent to convert a book

After loading the skill, send a request like this. Replace the paths with your own; the same request works for an EPUB.

```text
Convert /absolute/path/to/book.pdf to a single Markdown file in
/absolute/path/to/output, with images in an adjacent folder.
Check the environment, set up the dependencies needed for this book, and
choose the conversion route. Preserve headings, tables, formulas, and images.
Keep the source file. Finish the cleanup and validation, and report anything
that still needs review.
```

Your agent handles the commands. For scans, use an agent/model that can inspect page images: the workflow cross-checks two OCR engines and reviews their disagreements against the source.

For a whole bookshelf:

```text
Use book-to-markdown to convert the PDF and EPUB books in /absolute/path/to/books.
Create a resumable batch plan first. Agree the total budget before paid calls,
keep the source files, and report each book's completion and review status.
```

For a book you have already cleaned:

```text
Use book-to-markdown to re-OCR /absolute/path/to/book.pdf and patch
/absolute/path/to/cleaned.md. Preserve its existing structure and formatting.
Use reviewed OCR, back up the original, and validate every changed region.
```

## Why

- **Scanned PDFs:** PaddleOCR-VL as the primary engine, cross-checked against pp_structurev3. Review focuses on disagreements. Pilot: 3 textbooks, 29 pages, 0% paragraph loss after review. This is a pilot result; shared OCR mistakes still need spot-checks.
- **Text-layer PDFs:** marker preserves headings, tables, formulas, and images without unnecessary OCR.
- **EPUBs:** pandoc extracts digital text and images, followed by markup cleanup.
- **Resumable:** scanned-PDF jobs skip completed pages after a crash; batch plans track whole bookshelves.

## Environment

The agent needs access to your books, a shell, and an output directory. It follows the bundled setup guide to check and install the tools for the selected route:

| Route | Conversion tools |
| --- | --- |
| EPUB | pandoc |
| Text-layer PDF | marker-pdf (`marker_single`), Poppler |
| Scanned PDF | PaddleOCR, PaddlePaddle, `paddlex[ocr]`; a GPU with at least 6 GB VRAM is recommended for PaddleOCR-VL. The pp_structurev3 CPU fallback is slower. |

The scripts use Bash and Python; the OCR setup uses Python 3.12 via uv. Models download on first use. Agent access and any model/API costs depend on your chosen host and provider. Preflight checks the environment and prints recommendations; it does not install dependencies itself.

## Workflow and documentation

[SKILL.md](SKILL.md) is the agent entry point. [SKILL_DEV.md](SKILL_DEV.md) contains the full shared workflow and quality gates. The guides in `references/` retain their original language, mostly Chinese:

- [setup.md](references/setup.md) — first-time environment setup.
- [postprocess-pdf.md](references/postprocess-pdf.md) / [postprocess-epub.md](references/postprocess-epub.md) — cleanup and review checklists.
- [batch.md](references/batch.md) — resumable bookshelf processing.
- [patch-control.md](references/patch-control.md) — patching a previously cleaned book with new OCR.

## Reading the output

[Hortus](https://github.com/groundgrounder/Hortus) renders large Mermaid diagrams in columns so the text stays readable. It is a native Mac app with a Rust core and no WebView.

## License

[MIT](LICENSE)
