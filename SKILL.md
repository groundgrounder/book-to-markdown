---
name: book-to-markdown
description: Convert scanned PDFs, text-layer PDFs, and EPUB books into clean Markdown with images, heading hierarchy, and a table of contents. Use for book conversion, OCR cleanup, re-OCR patches, and resumable bookshelf batches.
license: MIT
---

# book-to-markdown

Read [SKILL_DEV.md](SKILL_DEV.md) before starting. It contains the complete workflow, cost and acceptance contract, route selection, and quality gates shared by Claude Code, Codex, pi, and other agents.

Resolve all bundled paths relative to this skill directory. Use absolute paths for the user's books, work directory, and output. Run shell helpers with Bash and Python helpers with the appropriate Python interpreter; some helpers are not marked executable.

Follow the workflow's preflight and setup guidance, then load the references for the relevant route. If preflight is blocked, report the cause and distinguish it from successful validation. Scanned-PDF review requires inspecting source page images; unresolved findings remain pending.
