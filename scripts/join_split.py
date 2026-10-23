#!/usr/bin/env python3
"""Export locally evidenced joins; apply only explicitly approved plan IDs.

Dry run: join_split.py md old vl pp --pages p0021-p0370 --plan joins.json
Apply: same arguments --apply-plan joins.json --approve ID,ID --apply
       --backup-dir fresh-backup
The old bare --apply is intentionally rejected. A source match is a proposal,
not a review decision. Text notes and index entries are not body prose.
"""
import argparse
import bisect
import json
from pathlib import Path
import re

import apply_exact
from review_contract import atomic_write, canonical, digest, guard_outputs, read_text
from seam_check import END, PUN0, SKIP, norm

FN = re.compile(r'^\s*(?:\[\^[^]]+\]:|[①-⑳]|\*+|[-—]*译者注)')
TAILFN = re.compile(r'(\[\^[^]]*\]|[①-⑳]|\$\s*\^\{[^}]*\}?\s*\$?|\s)+$')


def body(text):
    first = text.lstrip()
    return (bool(first) and not SKIP.match(first) and not FN.match(first)
            and '译者注' not in text and not re.search(r'<[^>]+>', text)
            and not re.match(r'[（(][一二三四五六七八九十\d]+[)）]', first))


def closed(text):
    return TAILFN.sub('', text.rstrip()).endswith(END)


class Sources:
    def __init__(self, roots, pages):
        self.corpora, self.inputs = [], {}
        for root in roots:
            chunks, offsets, paths, total = [], [], [], 0
            for path in sorted(Path(root).glob('pages/p*/p[0-9][0-9][0-9][0-9].md')):
                page = int(path.stem[1:])
                if pages and not pages[0] <= page <= pages[1]:
                    continue
                raw = read_text(path)
                self.inputs[str(path.resolve())] = digest(raw)
                # Preserve real paragraph boundaries; omit source footnotes for
                # sentence lookup only. Target footnotes are never discarded.
                chunks.append('¶'.join(norm(p) for p in re.split(r'\n\s*\n', raw)
                                       if norm(p) and not FN.match(p)))
                offsets.append(total)
                paths.append(path)
                total += len(chunks[-1])
            self.corpora.append((''.join(chunks), offsets, paths))

    def evidence(self, query):
        results = []
        for corpus, offsets, paths in self.corpora:
            at = corpus.find(query)
            if at < 0 or corpus.find(query, at + 1) >= 0:
                continue
            first = bisect.bisect_right(offsets, at) - 1
            last = bisect.bisect_right(offsets, at + len(query) - 1) - 1
            selected = paths[first:last + 1]
            numbers = [int(path.stem[1:]) for path in selected]
            if len(selected) > 2 or any(b != a + 1 for a, b in zip(numbers, numbers[1:])):
                continue
            for path in selected:
                results.append({'path': str(path.resolve()), 'sha256': self.inputs[str(path.resolve())],
                                'locator': path.stem + ': contiguous join probe ' + query})
        return results


def build_plan(md, old_path, roots, pages=None):
    text, old = read_text(md), read_text(old_path)
    sources = Sources(roots, pages)
    blocks = list(re.finditer(r'\S(?:[^\n]|\n(?!\s*\n))*', text))
    old_paragraphs = {match.group() for match in re.finditer(r'\S(?:[^\n]|\n(?!\s*\n))*', old)}
    reserved, changes = [], []

    def propose(first, last, replacement, reason, evidence):
        start, end = blocks[first].start(), blocks[last].end()
        if not evidence or any(start < b and end > a for a, b in reserved):
            return
        before = text[start:end]
        if text.count(before) != 1 or before == replacement:
            return
        reserved.append((start, end))
        changes.append({'id': digest(canonical([before, replacement]))[:24],
                        'old': before, 'new': replacement, 'old_sha256': digest(before),
                        'left': text[max(0, start - 48):start], 'right': text[end:end + 48],
                        'max_chars': max(len(before), len(replacement)), 'mode': 'reconstruct',
                        'block_type': 'sentence_join', 'reason': reason, 'evidence': evidence,
                        'source_pages': sorted({Path(item['path']).stem for item in evidence})})

    for index, match in enumerate(blocks):
        value = match.group()
        if index and value.lstrip()[:1] in PUN0 and value not in old_paragraphs:
            punctuation = re.match(r'\s*([' + PUN0 + r']+)\s*', value)
            mark, rest = punctuation.group(1), value[punctuation.end():]
            previous = blocks[index - 1]
            if body(previous.group()) and not closed(previous.group()):
                evidence = sources.evidence(norm(previous.group())[-8:] + norm(mark) + norm(rest)[:8])
                propose(index - 1, index, previous.group().rstrip() + mark + rest,
                        'Restore punctuation inside its evidenced sentence; inspect the complete scope.', evidence)
            continue
        if not body(value) or closed(value) or len(norm(value)) < 6:
            continue
        following = index + 1
        notes = []
        while following < len(blocks) and len(notes) < 3 and re.match(r'^\s*(?:\[\^[^]]+\]:|[①-⑳])', blocks[following].group()):
            notes.append(blocks[following].group())
            following += 1
        if following >= len(blocks):
            continue
        next_value = blocks[following].group()
        if not body(next_value) or max(len(norm(value)), len(norm(next_value))) < 30:
            continue
        query = norm(value)[-8:] + norm(next_value)[:8]
        evidence = sources.evidence(query)
        space = ' ' if re.match(r'[A-Za-z0-9]$', value.rstrip()) and re.match(r'[A-Za-z0-9(]', next_value.lstrip()) else ''
        joined = value.rstrip() + space + next_value.lstrip()
        if notes:
            joined += '\n\n' + '\n\n'.join(notes)
        propose(index, following, joined, 'Join an evidenced sentence; preserve intervening notes after its complete paragraph.', evidence)
    inputs = sources.inputs | {str(Path(md).resolve()): digest(text), str(Path(old_path).resolve()): digest(old)}
    for filename in ('join_split.py', 'seam_check.py', 'apply_exact.py', 'review_contract.py'):
        path = Path(__file__).with_name(filename)
        inputs[str(path.resolve())] = digest(path.read_bytes())
    return {'version': 1, 'inputs': inputs, 'page_range': pages,
            'books': [{'file': Path(md).name, 'sha256': digest(text), 'changes': changes}]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('md', type=Path)
    parser.add_argument('old', type=Path)
    parser.add_argument('roots', nargs='+', type=Path)
    parser.add_argument('--pages', help='Inclusive source IDs, e.g. p0021-p0370 (not printed page numbers).')
    parser.add_argument('--plan', type=Path)
    parser.add_argument('--apply-plan', type=Path)
    parser.add_argument('--approve')
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--backup-dir', type=Path)
    args = parser.parse_args()
    pages = None
    if args.pages:
        if not re.fullmatch(r'p\d{4}-p\d{4}', args.pages):
            parser.error('--pages must use pNNNN-pNNNN IDs')
        pages = [int(part[1:]) for part in args.pages.split('-')]
        if pages[0] > pages[1]:
            parser.error('Reversed page range')
    if args.apply:
        if not args.apply_plan or not args.approve or not args.backup_dir or not pages:
            parser.error('--apply requires --apply-plan, --approve, --backup-dir, and a verified --pages range')
        plan = json.loads(read_text(args.apply_plan))
        current = build_plan(args.md, args.old, args.roots, pages)
        if plan != current:
            raise ValueError('Join plan is stale or altered; regenerate and review it.')
        selected = set(args.approve.split(','))
        prepared, reviews = apply_exact.prepare(args.md.resolve().parent, plan, args.apply_plan.resolve().parent, selected)
        if any(not item['approved'] for item in reviews):
            raise ValueError('Join would delete visible text; use a separately reviewed exact patch.')
        if not prepared:
            raise ValueError('No matching approved edits.')
        apply_exact.commit(prepared, args.backup_dir)
        print(f'Applied {len(selected)} approved joins; rerun to discover dependent joins.')
    else:
        plan = build_plan(args.md, args.old, args.roots, pages)
        if args.plan:
            guard_outputs([args.plan], plan['inputs'])
            atomic_write(args.plan, json.dumps(plan, ensure_ascii=False, indent=2) + '\n')
        for item in plan['books'][0]['changes']:
            print(item['id'], ','.join(item['source_pages']), item['reason'], sep='\t')
        print(f'# {len(plan["books"][0]["changes"])} independent candidates; no book changed')


if __name__ == '__main__':
    main()
