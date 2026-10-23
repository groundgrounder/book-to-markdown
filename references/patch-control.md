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
