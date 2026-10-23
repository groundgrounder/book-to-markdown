#!/usr/bin/env python3
"""Content-bound review manifests and small, self-contained review packets.

This records review evidence, not semantic truth. It never edits a book and
never treats a table, suffix match, or matching author name as an exemption.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import tempfile


def digest(data):
    if isinstance(data, str):
        data = data.encode('utf-8')
    return hashlib.sha256(data).hexdigest()


def read_text(path):
    return Path(path).read_bytes().decode('utf-8')


def canonical(data):
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def atomic_write(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix='.' + path.name + '.', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(text.encode('utf-8'))
            stream.flush()
            os.fsync(stream.fileno())
        if path.exists():
            os.chmod(name, path.stat().st_mode & 0o777)
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def resource(spec, base):
    if isinstance(spec, str):
        spec = {'path': spec}
    path = (base / spec['path']).resolve(strict=True)
    if path.is_file():
        return {'path': str(path), 'sha256': digest(path.read_bytes())}
    patterns = spec.get('include', ['*'])
    members = {}
    for member in sorted(path.rglob('*')):
        if '__pycache__' in member.parts or '.git' in member.parts:
            continue
        relative = member.relative_to(path)
        if member.is_file() and any(relative.match(pattern) for pattern in patterns):
            members[relative.as_posix()] = digest(member.read_bytes())
    if not members:
        raise ValueError(f'No input files selected: {path}')
    return {'path': str(path), 'sha256': digest(canonical(members)), 'files': members}


def guard_outputs(outputs, protected):
    """Reject report paths aliasing inputs, including symlinks and hard links."""
    paths = [Path(path).resolve() for path in outputs]
    sources = [Path(path).resolve() for path in protected]
    for index, path in enumerate(paths):
        for source in sources + paths[:index]:
            aliases = (path == source or (source.is_dir() and path.is_relative_to(source)))
            if not aliases and path.exists() and source.exists():
                aliases = path.samefile(source)
            if aliases:
                raise ValueError(f'Output aliases a protected input or another output: {path}')


def fingerprint(config_path):
    path = Path(config_path)
    config = json.loads(read_text(path))
    required = {'candidate', 'tools'}
    if config.get('route') == 'patch':
        required |= {'source_pdf', 'old', 'vl', 'pp', 'decisions', 'raw_reports'}
    if not required <= config.get('inputs', {}).keys():
        raise ValueError('Missing input roles: ' + ', '.join(sorted(required - config.get('inputs', {}).keys())))
    inputs = {key: resource(spec, path.resolve().parent)
              for key, spec in sorted(config['inputs'].items())}
    body = {'config': config, 'inputs': inputs,
            'contract_sha256': digest(Path(__file__).read_bytes())}
    return body | {'sha256': digest(canonical(body))}


def verify_snapshot(config, manifest):
    current = fingerprint(config)
    if current != manifest:
        raise ValueError('STALE: candidate, OCR pages, decisions, policy, reports, or scripts changed; rerun affected gates.')


def json_lines(path):
    if path is None:
        return []
    return [json.loads(line) for line in read_text(path).splitlines() if line.strip()]


def bind_finding(row):
    required = {'book', 'page', 'page_kind', 'gate', 'kind', 'text', 'context', 'located'}
    if not required <= row.keys() or not row['context']:
        raise ValueError('Finding requires book/page/kind/gate/text, nonempty context, page_kind and located.')
    if not isinstance(row['located'], bool):
        raise ValueError('located must be boolean; a guessed line 1 is not a location.')
    context_hash = digest(row['context'])
    identity = {key: row[key] for key in ('book', 'page', 'page_kind', 'gate', 'kind', 'text')}
    identity['context_sha256'] = context_hash
    return row | {'id': digest(canonical(identity))[:24], 'context_sha256': context_hash}


def evidence_ok(items, base):
    if not isinstance(items, list) or not items:
        return False
    for item in items:
        if not isinstance(item, dict) or not all(item.get(key) for key in ('path', 'sha256', 'locator')):
            return False
        path = base / item['path']
        if not path.is_file() or digest(path.read_bytes()) != item['sha256']:
            return False
    return True


def assess(findings, reviews, manifest, base):
    rows = [bind_finding(row) for row in findings]
    if len({row['id'] for row in rows}) != len(rows):
        raise ValueError('Duplicate finding IDs; deduplicate identical raw hits before review.')
    if len({row['id'] for row in reviews}) != len(reviews):
        raise ValueError('Duplicate review IDs')
    decisions = {row['id']: row for row in reviews}
    unresolved, accepted, invalid = [], [], []
    excluded = set(manifest['config'].get('excluded_page_kinds', []))
    for row in rows:
        review = decisions.get(row['id'], {})
        status = review.get('status', 'pending')
        if status not in {'pending', 'deferred', 'unlocated', 'reviewed_keep', 'excluded_nonbody', 'fixed_verified'}:
            raise ValueError(f'Unknown review status: {status}')
        valid = (row['located'] and row['page_kind'] != 'unknown'
                 and review.get('context_sha256') == row['context_sha256']
                 and bool(review.get('reason', '').strip())
                 and evidence_ok(review.get('evidence'), base))
        if status == 'excluded_nonbody':
            valid = valid and row['page_kind'] in excluded
        if status == 'fixed_verified':
            # A live finding cannot be closed just by calling the edit fixed.
            valid = False
        if valid and status in {'reviewed_keep', 'excluded_nonbody'}:
            accepted.append(row | {'review': review})
        else:
            unresolved.append(row | {'review': review})
            if review and status not in {'pending', 'deferred', 'unlocated'}:
                invalid.append(row['id'])
    stale = sorted(set(decisions) - {row['id'] for row in rows})
    # This deliberately is not an installation PASS. Completeness and a final
    # full-scope gate run must be established separately.
    return {'review_state': 'NEEDS_REVIEW' if unresolved else 'READY_FOR_FINAL_CHECK',
            'raw': len(rows), 'reviewed': len(accepted), 'unresolved': len(unresolved),
            'invalid_reviews': invalid, 'inactive_review_ids': stale,
            'findings': rows, 'pending': unresolved, 'accepted': accepted}


def packets(rows, output, max_items=20, max_chars=24000):
    output = Path(output)
    if output.exists():
        raise ValueError('Use a fresh packet directory; do not leave obsolete batches behind.')
    if max_items < 1 or max_chars < 1:
        raise ValueError('Packet limits must be positive.')
    instructions = ('Review only these IDs against the supplied current/VL/PP text. Return JSONL: '
                    'id, context_sha256, proposed_old, proposed_new, evidence, reason, or status=needs_image. '
                    'Do not edit files, infer print from language plausibility, or normalize original misprints. '
                    'Missing/unclear evidence stays pending. Local file paths are not accessible to a remote worker.')

    def serialize(items):
        return json.dumps({'instructions': instructions, 'findings': items}, ensure_ascii=False, indent=2) + '\n'

    batches, batch = [], []
    for row in rows:
        if not row.get('context') or any(not row.get(key + '_context') and not row.get(key + '_unavailable_reason')
                                         for key in ('vl', 'pp')):
            raise ValueError('Self-contained packets require current/VL/PP text or explicit source-unavailable reasons; locators alone are not enough.')
        if len(serialize([row])) > max_chars:
            raise ValueError(f'Finding {row["id"]} exceeds packet cap; export a bounded region, not a chapter.')
        if batch and (len(batch) >= max_items or len(serialize(batch + [row])) > max_chars):
            batches.append(batch)
            batch = []
        batch.append(row)
    if batch:
        batches.append(batch)
    output.mkdir(parents=True)
    for index, items in enumerate(batches):
        atomic_write(output / f'batch-{index:03d}.json', serialize(items))
    return len(batches)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    snap = sub.add_parser('snapshot')
    snap.add_argument('config', type=Path)
    snap.add_argument('manifest', type=Path)
    check = sub.add_parser('assess')
    check.add_argument('config', type=Path)
    check.add_argument('manifest', type=Path)
    check.add_argument('findings', type=Path)
    check.add_argument('--reviews', type=Path)
    check.add_argument('--output', type=Path, required=True)
    pack = sub.add_parser('packets')
    pack.add_argument('assessment', type=Path)
    pack.add_argument('output', type=Path)
    pack.add_argument('--max-items', type=int, default=20)
    pack.add_argument('--max-chars', type=int, default=24000)
    args = parser.parse_args()
    if args.command == 'snapshot':
        if args.manifest.exists():
            raise ValueError('Manifest exists; create a new round, not a new baseline for old reports.')
        manifest = fingerprint(args.config)
        guard_outputs([args.manifest], [args.config, __file__] + [item['path'] for item in manifest['inputs'].values()])
        atomic_write(args.manifest, json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
        print(f'Bound current inputs: {args.manifest}')
    elif args.command == 'assess':
        manifest = json.loads(read_text(args.manifest))
        verify_snapshot(args.config, manifest)
        protected = [args.config, args.manifest, args.findings, __file__]
        if args.reviews:
            protected.append(args.reviews)
        guard_outputs([args.output], protected + [item['path'] for item in manifest['inputs'].values()])
        result = assess(json_lines(args.findings), json_lines(args.reviews), manifest,
                        args.reviews.resolve().parent if args.reviews else args.config.resolve().parent)
        atomic_write(args.output, json.dumps(result, ensure_ascii=False, indent=2) + '\n')
        print(canonical({key: value for key, value in result.items() if key not in {'findings', 'pending', 'accepted'}}))
    else:
        if args.max_items < 1 or args.max_chars < 1:
            raise ValueError('Packet limits must be positive.')
        result = json.loads(read_text(args.assessment))
        print(f'{packets(result["pending"], args.output, args.max_items, args.max_chars)} self-contained batches')


if __name__ == '__main__':
    main()
