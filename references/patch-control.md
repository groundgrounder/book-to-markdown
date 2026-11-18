# Bounded Patches and Review Acceptance

For re-OCR patches or substantial cleanup of existing Markdown. Preserve delivery paths and original-print policy. Do not import book-specific page ranges, spelling lists or patch-ID waivers into a general workflow.

## Cost Envelope

Agree a total budget before paid work: main session, text/image review, OCR APIs and retries. Reuse approved limits rather than repeatedly asking. Record measured usage where exposed; otherwise disclose unknown billing and cap calls/context/output/retries. No paid subagent calls does not prove zero total cost. Stop before exceeding the approved envelope.

Export candidate lists locally. Text packets default to at most 20 findings or 24000 serialized input characters (including the prompt); shrink for long tables. Every packet includes ID, exact current text/location, embedded VL/PP local text, source locators, allowed changes and output schema. A remote worker cannot read a local path. Explicitly unavailable sources need a reason, not guessed text. Return exact proposals or `needs_image`, not essays. Checkpoint each packet. The main session reads compact diffs/summaries and high-risk samples, not repeated whole chapters. Delegation must be authorized; do not fork full context for rote work or ignore the user's provider/model constraints. A local fallback still consumes main-session tokens.

## Inputs and Review States

Keep before snapshots and staged candidates. Fingerprint the PDF, old md, reviewed VL/PP files, decisions, raw reports, tools/options and editorial policy. Select relevant files explicitly, not unrelated render caches. Use zero-based `pNNNN` source IDs; record printed folios separately. Unknown location/classification stays unresolved, not line1/book-title fallback.

`review_contract.py` binds **existing** raw reports; it does not run or certify gates:

```bash
python3 scripts/review_contract.py snapshot run-config.json manifest.json
python3 scripts/review_contract.py assess run-config.json manifest.json findings.jsonl \
  --reviews reviews.jsonl --output assessment.json
python3 scripts/review_contract.py packets assessment.json text-batches
```

Config paths are relative to the config file. Patch-route example:

```json
{
  "route": "patch",
  "excluded_page_kinds": ["index", "bibliography"],
  "policy": {"printed_misprints": "preserve", "page_map": "explicitly verified"},
  "inputs": {
    "candidate": "staged/book.md",
    "old": "before/book.md",
    "source_pdf": "book.pdf",
    "vl": {"path": "vl/book/pages", "include": ["*.md", "*_res.json"]},
    "pp": {"path": "pp/book/pages", "include": ["*.md", "*_res.json"]},
    "decisions": "review/sites.tsv",
    "raw_reports": "round-01/raw",
    "tools": {"path": "skill/scripts", "include": ["*.py"]}
  }
}
```

Each findings JSONL line needs `book,page,page_kind,gate,kind,text,context,located`; include `left,right` and precise locators as well. Packet export additionally requires `vl_context,pp_context` (or an explicit `vl_unavailable_reason`/`pp_unavailable_reason`). The helper generates `id` and `context_sha256` independent of line number. Exclusions follow user scope; tables/callouts/glossary/appendix/unknown are not automatic exclusions.

Review JSONL: `id,context_sha256,status,reason,evidence`. Evidence is a nonempty list of `{path,sha256,locator}`, paths relative to the review file. The locator identifies the complete passage/page/crop, not merely a citation suffix. Hashes detect changed evidence; they cannot prove a human/model judgement is true.

- `reviewed_keep`: complete current region checked against identified sources.
- `excluded_nonbody`: page classification verified and outside explicit user scope.
- `pending`, `unlocated`, `deferred`: unresolved, still block acceptance.
- `fixed_verified`: history only; cannot close a live finding without gate recheck. The finding must stop appearing, or separately receive a justified KEEP decision.

`READY_FOR_FINAL_CHECK` means all **supplied** findings have valid records. It does not prove list completeness, gate execution or semantic correctness. Keep raw, reviewed-exception and unresolved counts separate. Changed inputs invalidate the snapshot; never relabel stale raw reports by overwriting a manifest.

## Re-OCR Patch Workflow (`patch_cleaned.py`)

When an existing cleaned Markdown file has good structure (heading hierarchy, TOC, footnotes, callouts) but its earlier OCR dropped paragraphs or misread characters, keep the cleaned file as the skeleton and patch it from **reviewed** new OCR (`crosscheck.py` → `apply_review.py` first; otherwise VL's own errors are copied in).

In patch mode, set `drop`/`drop-t` sites to `primary` by default after batch-checking `uncovered(span, old_md)`: spans only PP/text-layer has are usually already in `old.md`, diagram labels inside images, or noise. Escalate only what is missing from both VL and `old.md`.

```bash
python3 scripts/patch_cleaned.py <old.md> "$W/vl/<book_name>" "$W/patch" \
  [--pages start-end] \
  --verify "$W/pp/<book_name>" "$W/review/sites.tsv" \
  --careful "$W/review/unaligned.txt"
```

- `--pages start-end`: skip front/back appendix pages intentionally omitted from `old.md`.
- `--verify`: apply a character change only if PP agrees at that spot or image review decided it (protects VL-only unaligned regions such as tables from VL's silent rewrites).
- `--careful`: on pages listed in `unaligned.txt`, apply insertions only and route every character fix to `skipped.tsv`.

### Insertion and Character-Fix Guards

- **Dash pre-pass**: converts `X一Y` → `X—Y` in `old.md` wherever the new OCR has a dash between Chinese characters (prevents PP's `—→一` habit from breaking alignment).
- **Span insertions**: spans present in new OCR and nowhere in `old.md` (checked order-insensitively across the whole file so moved chapter-end footnotes are not treated as missing) are inserted at unique anchors wrapped in `<!-- 补 pNNNN -->…<!-- /补 -->` (or `<!-- 补 pNNNN 脚注 -->` after their owning paragraph, extended to line end).
  - *Anchors*: require unique pre/post anchors in the `old.md` window. An anchor <14 chars must also roughly match on its outer side; on conflict, trust the ≥14-char anchor; if both are short, write `anchorconflict` to `skipped.tsv`.
  - *Punctuation*: anchors match letters and digits only; when the punctuation run at the insertion point equals `before_punct + after_punct`, replace the whole run so trailing periods are not stranded as standalone paragraphs.
  - *Inline vs. block*: start a new paragraph only when the new OCR has blank lines on both sides **and** `old.md` ends a sentence before the insertion point (VL wraps lines at page edges).
  - *Formulas*: spans containing LaTeX or inside `$$` are skipped as `formula` (`old.md` retains formula images).
- **Deferred items (`skipped.tsv`)**: headings, multi-character deletions, unanchored spans, and weak alignments (`weakalign`) go to `skipped.tsv`. Footnote marker differences (`[^ch5-1]` vs `①`) are ignored.
- **Character-fix guards**:
  - Locate each page by clustered hits before advancing the cursor (prevents scattered TOC matches from jumping the cursor to the back of the book).
  - Require ≥10 identical characters on both sides, or ≥4 characters each side **with** corroboration (PP agreement or review decision).
  - Never insert digit runs mid-sentence or right after a year (`Wachtel,1986` + `18` margin page numbers); do delete 2–3 digit margin numbers flanked by Chinese text.
  - Never insert `一` where `old.md` already has `—`; when `—` replaces `一`, replace only the dash.
  - Inside table rows, limit edits to ≤2 characters and never insert superscripts (`$ ^{1} $`) as body text.

### Post-Patch Gates (run all four after `format_inserts.py apply`)

Coverage checks (`uncovered = 0`) are order- and position-blind: books can pass coverage while still containing stranded periods, mid-sentence paragraph splits, wrong-anchor inserts, or silently blocked review decisions. Run all four gates on the unchanged final candidate and inspect every body-page hit:

```bash
python3 scripts/seam_check.py <new.md> <old.md> "$W/vl/<book>" "$W/pp/<book>"
python3 scripts/align_check.py <new.md> "$W/vl/<book>" "$W/pp/<book>" --old <old.md>
python3 scripts/decision_check.py <new.md> "$W/review/sites.tsv"
python3 scripts/new_doubles.py <old.md> <new.md>
```

- `seam_check.py`: flags `punct`/`open`/`seam`/`fnote`/`latex`/`dash` candidates (not automatic fixes); inspect and handle joins via `join_split.py`.
- `align_check.py`: aligns page-by-page on ≥8-character anchors (`missing` with `pp=1` indicates a likely drop; `moved` flags misplaced inserts; expect column-order noise on index/bibliography pages).
- `decision_check.py`: verifies every review decision landed in `<new.md>` (inspect blocked decisions and double-check uncertain crops with `recheck_sheets.py` since human/subagent review still has ~5–10% error).
- `new_doubles.py`: catches newly introduced doubled characters (`老师师`, `即将将`, `兄兄弟`) caused by VL page-break repeats or misread review glyphs, ignoring legitimate reduplication.

## Bounded Exact Edits

Bound a typo to its sentence; reconstruct a scrambled table/callout as a complete logical object. Confirm both printed edges and inspect surrounding prose. A box can sit between `雇` and `员`. A repeated name or next heading found by unconstrained search is not a safe end boundary.

`apply_exact.py` plan: `version:1, books:[{file,sha256,changes:[...]}]`. Required change fields:

```json
{
  "id": "region-001",
  "old": "exact bounded old region",
  "new": "reviewed replacement",
  "old_sha256": "SHA256 of exact old text",
  "left": "immediately preceding outside anchor",
  "right": "immediately following outside anchor",
  "max_chars": 4000,
  "mode": "reconstruct",
  "block_type": "callout",
  "source_pages": ["p0061", "p0062"],
  "reason": "boundaries and content checked against source",
  "evidence": [{"path": "source-page.png", "sha256": "file SHA256", "locator": "source page/object bounds"}],
  "deletion_reviews": []
}
```

Choose the cap per region; 4000 is not a universal rewrite licence. `format` mode preserves text/punctuation/image targets; `literal`/`reconstruct` require review of each removed visible span. Anchors are adjacent and empty only at actual file edges. All scopes must be unique, original-snapshot-bound and nonoverlapping. Report paths must not alias the plan, book, evidence, tools or each other.

```bash
python3 scripts/apply_exact.py plan.json --books-dir staged \
  --diff proposed.diff --deletions deletion-spans.json
# Review the diff. For each approved deletion, add id/sha256/text plus its
# own reason/evidence to the change's deletion_reviews. No batch-ID waiver.
python3 scripts/apply_exact.py plan.json --books-dir staged \
  --diff approved.diff --deletions deletion-spans.json \
  --approve region-001 --apply --backup-dir backups/batch-001
```

All selected books are validated before writes. Apply backs up and atomically replaces each file, attempting rollback on failure; it is not a multi-file atomic commit. Use one writer; re-read final hashes. Patch replay proves reproducibility, not content conservation.

For joins, export a verified body source range, inspect complete regions, then apply selected IDs:

```bash
python3 scripts/join_split.py staged/book.md before/book.md vl/book pp/book \
  --pages p0021-p0370 --plan joins.json
python3 scripts/join_split.py staged/book.md before/book.md vl/book pp/book \
  --pages p0021-p0370 --apply-plan joins.json --approve ID1,ID2 \
  --apply --backup-dir backups/joins-001
```

Only independent candidates are exported; regenerate for dependent joins. No blanket full-book apply. Translator notes, index/bibliography entries and quoted headings are not continuations.

`format_inserts.py apply` fails the entire batch on absent results, changed text/punctuation/assets or stale source/tool/job hashes. It does not silently substitute raw jobs or collapse unrelated whitespace. A text-only guard still cannot prove callout membership or cell associations; those need source-image review.

## Insufficient Evidence

- A shared author/title or last 30 citation characters proves neither complete footnote identity nor placement. Check full note, printed citation pages and owning passage; repeated same-book citations can be legitimate.
- A formula image somewhere is insufficient. Name the exact image, match it to the source formula and verify its final relative path exists.
- `moved`/`extra` are hypotheses. Locate current and intended positions with nearby body anchors; do not delete merely because text occurs elsewhere.
- Tables need cell/row labels, meaningful empty cells and associations checked, not just flattened text or balanced tags. An unrecoverable clipped scan edge stays unresolved; do not invent it.
- A crop with a nearby sentence is not verified. Target glyph and neighbors must be visible. Ambiguous locators need full-page/high-resolution review with page/site/bounds/input hashes.
- Do not waive all deletions in a patch or all findings on a body page. Each removed span needs its own evidence/disposition. Restore accidental deletion before proceeding.
- Distinguish original-print errors from OCR errors. Unless the user approves a correction edition, preserve print; approved normalization needs a whitelist and change list.

## Checkpoints and Installation

After a batch, check edited regions, adjoining source pages, joins and image/footnote ownership. This is a checkpoint, not a full-book PASS. Run full gates on a stable candidate, repeating when changes invalidate them rather than after every character. Preserve scope, commands, exit codes and hashed reports; declining raw counts alone are not quality evidence.

Publish only when all applicable full-scope gates ran on the unchanged candidate, every in-scope finding is fixed/rechecked or evidence-backed KEEP, images resolve, and the diff has no unexplained content loss. Record source/candidate/decision/policy/tool hashes and acceptance, back up the destination, then install. File existence or a `.done` filename alone is not acceptance.

Regression tests:

```bash
python3 -m unittest discover -s tests -p 'test_*.py' -v
```
