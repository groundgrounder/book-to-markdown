#!/usr/bin/env python3
"""Preview and apply reviewed bounded replacements. Never rewrites an OCR book.

All books, scopes, evidence files and per-deletion approvals are validated
before writes. Backups are mandatory for apply. Files are atomically replaced
one at a time; rollback is attempted on failure (not a multi-file atomic commit).
"""
import argparse
import difflib
import html
import json
import os
from pathlib import Path
import re
import shutil
import tempfile

from review_contract import atomic_write, canonical, digest, evidence_ok, guard_outputs, read_text


def visible(text):
    text = re.sub(r'<!--.*?-->|</?[A-Za-z][^>]*>', '', text, flags=re.S)
    text = re.sub(r'(?m)^\s*(?:>\s*)+', '', text)
    text = re.sub(r'(?m)^\s*(?:#{1,6}\s+|[-+*]\s+)', '', text)
    text = re.sub(r'\[![A-Za-z]+\]', '', text)
    text = re.sub(r'[*`_]', '', text)
    return re.sub(r'\s+', '', html.unescape(text))


def asset_refs(text):
    return tuple(a or b for a, b in re.findall(r'!\[[^]]*\]\(([^)]+)\)|<img[^>]*\bsrc=["\']([^"\']+)', text))


def deletions(old, new):
    old, new = visible(old), visible(new)
    out = []
    for tag, start, end, _, _ in difflib.SequenceMatcher(None, old, new, autojunk=False).get_opcodes():
        if tag not in {'delete', 'replace'}:
            continue
        removed = old[start:end]
        # A moved span must retain its occurrence count inside THIS region.
        if removed and old.count(removed) > new.count(removed):
            identity = canonical({'offset': start, 'text': removed})
            out.append({'id': digest(identity)[:24], 'sha256': digest(removed), 'text': removed})
    return out


def direct_child(root, name):
    path = root / name
    if path.is_symlink() or path.resolve().parent != root.resolve():
        raise ValueError('Book must be a direct, non-symlink child of --books-dir.')
    return path


def prepare(root, plan, evidence_base, selected=None):
    if plan.get('version') != 1:
        raise ValueError('Plan version must be 1.')
    prepared, review, seen_ids, seen_paths = {}, [], set(), set()
    for book in plan['books']:
        path = direct_child(root, book['file'])
        if path in seen_paths:
            raise ValueError('Duplicate book in plan.')
        seen_paths.add(path)
        before = read_text(path)
        if digest(before) != book['sha256']:
            raise ValueError(f'Snapshot changed: {path.name}')
        changes = []
        for change in book['changes']:
            identity = change['id']
            if identity in seen_ids:
                raise ValueError('Duplicate change ID.')
            seen_ids.add(identity)
            if selected is not None and identity not in selected:
                continue
            old, new = change['old'], change['new']
            if not old or old == new or before.count(old) != 1:
                raise ValueError(f'Nonunique/missing/no-op scope: {identity}')
            start = before.index(old)
            end = start + len(old)
            if digest(old) != change['old_sha256']:
                raise ValueError(f'Region hash mismatch: {identity}')
            if len(old) > change['max_chars'] or len(new) > change['max_chars']:
                raise ValueError(f'Region cap exceeded: {identity}')
            left, right = change['left'], change['right']
            if (not left and start != 0) or (not right and end != len(before)):
                raise ValueError(f'Empty anchor is allowed only at an actual file edge: {identity}')
            if not before[:start].endswith(left) or not before[end:].startswith(right):
                raise ValueError(f'Boundary anchor mismatch: {identity}')
            if not change.get('block_type') or not change.get('source_pages') or not change.get('reason', '').strip():
                raise ValueError(f'Region type/pages/reason required: {identity}')
            if not evidence_ok(change.get('evidence'), evidence_base):
                raise ValueError(f'Missing/stale evidence: {identity}')
            if change.get('mode') not in {'format', 'reconstruct', 'literal'}:
                raise ValueError(f'Unknown edit mode: {identity}')
            if change['mode'] == 'format':
                if visible(old) != visible(new) or asset_refs(old) != asset_refs(new):
                    raise ValueError(f'Format-only edit changes punctuation/text/assets: {identity}')
            needed = deletions(old, new)
            approvals = change.get('deletion_reviews', [])
            if len({item['id'] for item in approvals}) != len(approvals):
                raise ValueError('Duplicate deletion approvals.')
            approvals = {item['id']: item for item in approvals}
            for item in needed:
                answer = approvals.get(item['id'], {})
                valid = (answer.get('sha256') == item['sha256'] and answer.get('text') == item['text']
                         and bool(answer.get('reason', '').strip())
                         and evidence_ok(answer.get('evidence'), evidence_base))
                review.append(item | {'book': path.name, 'change': identity, 'approved': bool(valid)})
            changes.append((start, end, new))
        ordered = sorted(changes)
        if any(first[1] > second[0] for first, second in zip(ordered, ordered[1:])):
            raise ValueError(f'Overlapping scopes: {path.name}')
        after = before
        for start, end, new in reversed(ordered):
            after = after[:start] + new + after[end:]
        if changes:
            prepared[path] = (before, after)
    if selected is not None and selected - seen_ids:
        raise ValueError('Unknown approved IDs: ' + ', '.join(sorted(selected - seen_ids)))
    return prepared, review


def commit(prepared, backup_dir):
    backup_dir = Path(backup_dir)
    if backup_dir.exists():
        raise ValueError('Backup directory must be fresh.')
    for path, (before, _) in prepared.items():
        if read_text(path) != before:
            raise ValueError(f'Concurrent modification: {path.name}')
    backup_dir.mkdir(parents=True)
    pending, installed = {}, []
    try:
        for path, (_, after) in prepared.items():
            shutil.copy2(path, backup_dir / path.name)
            fd, name = tempfile.mkstemp(prefix='.' + path.name + '.', dir=path.parent)
            pending[path] = Path(name)
            with os.fdopen(fd, 'wb') as stream:
                stream.write(after.encode('utf-8'))
                stream.flush()
                os.fsync(stream.fileno())
            os.chmod(name, path.stat().st_mode & 0o777)
        for path, (before, _) in prepared.items():
            if read_text(path) != before:
                raise ValueError(f'Concurrent modification: {path.name}')
        for path in prepared:
            os.replace(pending[path], path)
            installed.append(path)
    except Exception:
        for path in reversed(installed):
            atomic_write(path, read_text(backup_dir / path.name))
        raise
    finally:
        for temp in pending.values():
            if temp.exists():
                temp.unlink()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('plan', type=Path)
    parser.add_argument('--books-dir', type=Path, required=True)
    parser.add_argument('--diff', type=Path, required=True)
    parser.add_argument('--deletions', type=Path, required=True)
    parser.add_argument('--approve', help='Comma-separated change IDs; omitted previews all changes.')
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--backup-dir', type=Path)
    args = parser.parse_args()
    selected = set(args.approve.split(',')) if args.approve else None
    plan = json.loads(read_text(args.plan))
    protected = [args.plan, __file__, Path(__file__).with_name('review_contract.py')]
    for book in plan['books']:
        protected.append(direct_child(args.books_dir, book['file']))
        for change in book['changes']:
            for record in [change] + change.get('deletion_reviews', []):
                protected.extend(args.plan.resolve().parent / item['path'] for item in record.get('evidence', []))
    protected.extend(plan.get('inputs', {}))
    guard_outputs([args.diff, args.deletions], protected)
    prepared, review = prepare(args.books_dir, plan, args.plan.resolve().parent, selected)
    atomic_write(args.diff, ''.join(''.join(difflib.unified_diff(old.splitlines(True), new.splitlines(True),
                 fromfile=str(path) + '.before', tofile=str(path))) for path, (old, new) in prepared.items()))
    atomic_write(args.deletions, json.dumps(review, ensure_ascii=False, indent=2) + '\n')
    if args.apply:
        if not selected or not args.backup_dir:
            raise ValueError('--apply requires explicit --approve IDs and --backup-dir.')
        if any(not item['approved'] for item in review):
            raise ValueError('Unreviewed deletion spans; no book was written.')
        if not prepared:
            raise ValueError('No approved edits.')
        commit(prepared, args.backup_dir)
        print(f'Applied {len(selected)} bounded edits; backups: {args.backup_dir}')
    else:
        print(f'Preview: {len(prepared)} books, {sum(not item["approved"] for item in review)} deletion spans await review.')


if __name__ == '__main__':
    main()
