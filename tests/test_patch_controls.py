#!/usr/bin/env python3
"""Regression tests for print/OCR patch incidents; no real books are edited."""
import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPTS))
import apply_exact
import join_split
import recheck_sheets
import review_contract as contract


class Fixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='b2m-tests-')
        self.root = Path(self.tmp.name)
        self.source = self.root / 'source.md'
        self.source.write_text('source text and page evidence。', encoding='utf-8')
        self.evidence = [{'path': str(self.source), 'sha256': contract.digest(self.source.read_bytes()),
                          'locator': 'p0031 complete paragraph and both boundaries'}]

    def tearDown(self):
        self.tmp.cleanup()

    def plan(self, name='book.md', text='左锚。原句内容。右锚。', old='原句内容。', new='原句完整内容。'):
        path = self.root / name
        path.write_text(text, encoding='utf-8')
        at = text.index(old)
        change = {'id': name, 'old': old, 'new': new, 'old_sha256': contract.digest(old),
                  'left': text[:at], 'right': text[at + len(old):],
                  'max_chars': max(len(old), len(new)), 'mode': 'reconstruct',
                  'block_type': 'paragraph', 'source_pages': ['p0031'], 'reason': 'confirmed source',
                  'evidence': copy.deepcopy(self.evidence)}
        return {'version': 1, 'books': [{'file': name, 'sha256': contract.digest(text), 'changes': [change]}]}

    def run_script(self, name, *args):
        return subprocess.run([sys.executable, str(SCRIPTS / name), *map(str, args)],
                              text=True, capture_output=True)


class BoundedPatchTests(Fixture):
    def test_wrong_end_anchor_does_not_eat_later_body(self):
        plan = self.plan(text='左锚。原句内容。右锚。后文仍然必须保存。')
        plan['books'][0]['changes'][0]['right'] = '后文'
        with self.assertRaisesRegex(ValueError, 'Boundary'):
            apply_exact.prepare(self.root, plan, self.root)
        self.assertEqual((self.root / 'book.md').read_text(), '左锚。原句内容。右锚。后文仍然必须保存。')

    def test_region_cap_rejects_overrun(self):
        plan = self.plan()
        plan['books'][0]['changes'][0]['max_chars'] = 2
        with self.assertRaisesRegex(ValueError, 'cap'):
            apply_exact.prepare(self.root, plan, self.root)

    def test_bad_later_book_prevents_any_write(self):
        first = self.plan('first.md')
        later = self.plan('later.md', text='左锚。原句内容。原句内容。右锚。')
        first['books'].extend(later['books'])
        with self.assertRaisesRegex(ValueError, 'Nonunique'):
            apply_exact.prepare(self.root, first, self.root)
        self.assertEqual((self.root / 'first.md').read_text(), '左锚。原句内容。右锚。')

    def test_format_changes_cannot_drop_sentence_punctuation(self):
        plan = self.plan(new='原句内容')
        plan['books'][0]['changes'][0]['mode'] = 'format'
        with self.assertRaisesRegex(ValueError, 'Format-only'):
            apply_exact.prepare(self.root, plan, self.root)

    def test_format_preserves_asset_reference(self):
        old = '<img src="assets/formula-A.png">'
        plan = self.plan(text='左锚。' + old + '右锚。', old=old,
                         new='<img src="assets/formula-B.png">')
        plan['books'][0]['changes'][0]['mode'] = 'format'
        with self.assertRaisesRegex(ValueError, 'assets'):
            apply_exact.prepare(self.root, plan, self.root)

    def test_format_cannot_swap_html_image_order(self):
        old = '<img src="a.png"><img src="b.png">'
        plan = self.plan(text='左锚。' + old + '右锚。', old=old,
                         new='<img src="b.png"><img src="a.png">')
        plan['books'][0]['changes'][0]['mode'] = 'format'
        with self.assertRaisesRegex(ValueError, 'assets'):
            apply_exact.prepare(self.root, plan, self.root)

    def test_deletion_requires_exact_span_not_patch_id(self):
        plan = self.plan(new='原句。')
        change = plan['books'][0]['changes'][0]
        change['deletion_reviews'] = [{'id': change['id'], 'reason': 'whole patch accepted'}]
        _, records = apply_exact.prepare(self.root, plan, self.root)
        self.assertTrue(records)
        self.assertTrue(any(not row['approved'] for row in records))
        change['deletion_reviews'] = [row | {'reason': 'exact source span checked', 'evidence': self.evidence}
                                      for row in records]
        _, reviewed = apply_exact.prepare(self.root, plan, self.root)
        self.assertTrue(all(row['approved'] for row in reviewed))

    def test_stale_full_source_and_stale_evidence_reject(self):
        plan = self.plan()
        self.source.write_text('changed evidence')
        with self.assertRaisesRegex(ValueError, 'evidence'):
            apply_exact.prepare(self.root, plan, self.root)
        (self.root / 'book.md').write_text('outside edit')
        with self.assertRaisesRegex(ValueError, 'Snapshot'):
            apply_exact.prepare(self.root, plan, self.root)

    def test_path_escape_and_overlapping_regions_reject(self):
        plan = self.plan()
        plan['books'][0]['file'] = '../book.md'
        with self.assertRaisesRegex(ValueError, 'direct'):
            apply_exact.prepare(self.root, plan, self.root)
        plan = self.plan()
        extra = copy.deepcopy(plan['books'][0]['changes'][0])
        extra['id'] = 'different-id'
        plan['books'][0]['changes'].append(extra)
        with self.assertRaisesRegex(ValueError, 'Overlapping'):
            apply_exact.prepare(self.root, plan, self.root)

    def test_commit_rolls_back_previous_file_if_later_replace_fails(self):
        first, later = self.root / 'a.md', self.root / 'b.md'
        first.write_text('old-a'); later.write_text('old-b')
        real_replace = apply_exact.os.replace
        failed = False

        def replace(source, target):
            nonlocal failed
            if Path(target) == later and not failed:
                failed = True
                raise OSError('simulated second-file failure')
            return real_replace(source, target)

        with mock.patch.object(apply_exact.os, 'replace', side_effect=replace):
            with self.assertRaisesRegex(OSError, 'second-file'):
                apply_exact.commit({first: ('old-a', 'new-a'), later: ('old-b', 'new-b')}, self.root / 'backup')
        self.assertEqual(first.read_text(), 'old-a')
        self.assertEqual(later.read_text(), 'old-b')
        self.assertEqual((self.root / 'backup/a.md').read_text(), 'old-a')

    def test_same_note_elsewhere_does_not_waive_local_deletion(self):
        note = '①同一作者的完整引文。'
        plan = self.plan(text='左锚。原句内容。' + note + '右锚。' + note,
                         old='原句内容。' + note, new='原句内容。')
        _, records = apply_exact.prepare(self.root, plan, self.root)
        self.assertTrue(records)
        self.assertTrue(all(not row['approved'] for row in records))

    def test_cli_preview_cannot_overwrite_book_or_evidence(self):
        plan = self.plan()
        path = self.root / 'plan.json'; path.write_text(json.dumps(plan))
        for output in (self.root / 'book.md', self.source, path):
            before = output.read_bytes()
            result = self.run_script('apply_exact.py', path, '--books-dir', self.root,
                                     '--diff', output, '--deletions', self.root / 'removed.json')
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(output.read_bytes(), before)

    def test_output_guard_rejects_symlinks_hardlinks_and_duplicate_reports(self):
        link = self.root / 'link'; link.symlink_to(self.source)
        hardlink = self.root / 'hardlink'; hardlink.hardlink_to(self.source)
        for output in (link, hardlink):
            with self.subTest(output=output), self.assertRaisesRegex(ValueError, 'aliases'):
                contract.guard_outputs([output], [self.source])
        with self.assertRaisesRegex(ValueError, 'aliases'):
            contract.guard_outputs([self.root / 'report', self.root / 'report'], [])

    def test_only_selected_changes_apply_and_unknown_ids_reject(self):
        first = self.plan('first.md')
        later = self.plan('later.md')
        first['books'].extend(later['books'])
        with self.assertRaisesRegex(ValueError, 'Unknown'):
            apply_exact.prepare(self.root, first, self.root, {'unknown'})
        prepared, records = apply_exact.prepare(self.root, first, self.root, {'later.md'})
        self.assertEqual(set(prepared), {self.root / 'later.md'})
        self.assertFalse(records)
        apply_exact.commit(prepared, self.root / 'selected-backup')
        self.assertEqual((self.root / 'first.md').read_text(), '左锚。原句内容。右锚。')
        self.assertEqual((self.root / 'later.md').read_text(), '左锚。原句完整内容。右锚。')


class ReviewTests(Fixture):
    def finding(self, **kwargs):
        row = {'book': 'book', 'page': 'p0031', 'page_kind': 'body', 'gate': 'align', 'kind': 'missing',
               'text': '原文差异', 'context': '当前完整段落。', 'located': True}
        return contract.bind_finding(row | kwargs)

    def review(self, row, **kwargs):
        return {'id': row['id'], 'context_sha256': row['context_sha256'], 'status': 'reviewed_keep',
                'reason': 'full source and owning passage checked', 'evidence': self.evidence} | kwargs

    def assess(self, row, review):
        manifest = {'config': {'excluded_page_kinds': ['index', 'bibliography']}}
        return contract.assess([row], [review], manifest, self.root)

    def test_line_shift_keeps_id_context_change_invalidates_review(self):
        row = self.finding(line=10)
        shifted = self.finding(line=999)
        self.assertEqual(row['id'], shifted['id'])
        self.assertEqual(self.assess(shifted, self.review(row))['unresolved'], 0)
        changed = self.finding(context='新段落。')
        self.assertEqual(self.assess(changed, self.review(row))['unresolved'], 1)

    def test_deferred_unlocated_unknown_and_live_fixed_stay_blocking(self):
        for row, status in [(self.finding(), 'deferred'), (self.finding(located=False), 'reviewed_keep'),
                            (self.finding(page_kind='unknown'), 'reviewed_keep'), (self.finding(), 'fixed_verified')]:
            with self.subTest(status=status, row=row):
                self.assertEqual(self.assess(row, self.review(row, status=status))['unresolved'], 1)

    def test_body_table_is_not_nonbody_exemption(self):
        row = self.finding(context='<table><tr><td>missing</td></tr></table>')
        self.assertEqual(self.assess(row, self.review(row, status='excluded_nonbody'))['unresolved'], 1)
        index = self.finding(page_kind='index')
        self.assertEqual(self.assess(index, self.review(index, status='excluded_nonbody'))['unresolved'], 0)

    def test_changed_ocr_decision_and_script_each_invalidate_manifest(self):
        files = {}
        for role in ('candidate', 'tools', 'source_pdf', 'vl', 'pp', 'decisions', 'old', 'raw_reports'):
            path = self.root / (role + '.txt'); path.write_text('original ' + role)
            files[role] = path.name
        config = self.root / 'run.json'
        config.write_text(json.dumps({'route': 'patch', 'inputs': files}))
        snapshot = contract.fingerprint(config)
        for role in files:
            path = self.root / files[role]; before = path.read_text(); path.write_text('changed')
            with self.subTest(role=role), self.assertRaisesRegex(ValueError, 'STALE'):
                contract.verify_snapshot(config, snapshot)
            path.write_text(before)

    def test_patch_snapshot_requires_source_pdf(self):
        config = self.root / 'run.json'
        roles = ('candidate', 'tools', 'vl', 'pp', 'decisions', 'old', 'raw_reports')
        config.write_text(json.dumps({'route': 'patch', 'inputs': dict.fromkeys(roles, self.source.name)}))
        with self.assertRaisesRegex(ValueError, 'source_pdf'):
            contract.fingerprint(config)

    def test_footnote_suffix_match_is_not_an_acceptance_rule(self):
        row = self.finding(kind='fnote', context='①不同卷页但同一书名的引文。', suffix_match=True)
        result = self.assess(row, self.review(row, evidence=[]))
        self.assertEqual(result['unresolved'], 1)
        self.assertEqual(result['review_state'], 'NEEDS_REVIEW')

    def test_packets_reject_oversized_context_without_truncation(self):
        row = self.finding(vl_context='x' * 1000, pp_context='完整原文')
        with self.assertRaisesRegex(ValueError, 'cap'):
            contract.packets([row], self.root / 'too-large', max_chars=100)

    def test_review_packets_are_bounded_and_keep_local_sources(self):
        rows = [self.finding(text=str(i), vl_context='VL完整原文', pp_context='PP完整原文') for i in range(5)]
        folder = self.root / 'packets'
        self.assertEqual(contract.packets(rows, folder, max_items=2), 3)
        for path in folder.glob('*.json'):
            payload = json.loads(path.read_text())
            self.assertLessEqual(len(payload['findings']), 2)
            self.assertTrue(all('vl_context' in row and 'pp_context' in row for row in payload['findings']))

    def test_packet_limit_counts_prompt_and_serialized_whitespace(self):
        rows = [self.finding(text=str(i), vl_context='V' * 100, pp_context='P' * 100) for i in range(3)]
        output = self.root / 'capped'
        contract.packets(rows, output, max_chars=1800)
        self.assertTrue(list(output.glob('*.json')))
        self.assertTrue(all(len(path.read_text()) <= 1800 for path in output.glob('*.json')))

    def test_remote_packet_cannot_contain_only_local_paths(self):
        with self.assertRaisesRegex(ValueError, 'Self-contained'):
            contract.packets([self.finding(vl_path='local.md', pp_path='local.json')], self.root / 'bad-packet')
        self.assertFalse((self.root / 'bad-packet').exists())


class JoinAndFormatTests(Fixture):
    def sources(self, page_text):
        root = self.root / 'vl'
        page = root / 'pages/p0021/p0021.md'
        page.parent.mkdir(parents=True); page.write_text(page_text)
        return root

    def test_gu_yuan_join_preserves_full_outside_body(self):
        first = '一个商业组织可以解雇一个无能的雇'
        last = '员，或者相反，雇员也可辞职并永久性地切断与该组织的联系，而家庭成员的关系并非如此。'
        source = self.sources(first + last)
        md, old = self.root / 'book.md', self.root / 'old.md'
        md.write_text('左边正文。\n\n' + first + '\n\n' + last + '\n\n右边正文。')
        old.write_text(md.read_text())
        plan = join_split.build_plan(md, old, [source], [21, 21])
        changes = plan['books'][0]['changes']
        self.assertEqual(len(changes), 1)
        prepared, deletions = apply_exact.prepare(self.root, plan, self.root, {changes[0]['id']})
        self.assertFalse(deletions)
        self.assertEqual(prepared[md][1], '左边正文。\n\n' + first + last + '\n\n右边正文。')

    def test_standalone_punctuation_joins_even_if_mark_exists_elsewhere_in_old(self):
        first = '这是一段被补丁错误断开的完整正文'
        source = self.sources(first + '。')
        md, old = self.root / 'book.md', self.root / 'old.md'
        md.write_text(first + '\n\n。'); old.write_text(first + '。')
        plan = join_split.build_plan(md, old, [source], [21, 21])
        self.assertEqual(len(plan['books'][0]['changes']), 1)
        prepared, deleted = apply_exact.prepare(self.root, plan, self.root)
        self.assertFalse(deleted)
        self.assertEqual(prepared[md][1], first + '。')

    def join_fixture(self):
        first = '这是第一段需要连接的正文前半部分'
        last = '以及后半部分，测试必须保留所有句子，不能侵入左右相邻正文，也不能遗漏任何一个字。'
        source = self.sources(first + last)
        md, old = self.root / 'book.md', self.root / 'old.md'
        md.write_text('左文。\n\n' + first + '\n\n' + last + '\n\n右文。')
        old.write_text(md.read_text())
        plan_path = self.root / 'joins.json'
        result = self.run_script('join_split.py', md, old, source, '--pages', 'p0021-p0021', '--plan', plan_path)
        self.assertEqual(result.returncode, 0, result.stderr)
        plan = json.loads(plan_path.read_text())
        return md, old, source, plan_path, plan['books'][0]['changes'][0]['id']

    def test_join_cli_applies_approved_plan_and_backs_up(self):
        md, old, source, plan_path, identity = self.join_fixture()
        before = md.read_text()
        result = self.run_script('join_split.py', md, old, source, '--pages', 'p0021-p0021',
                                 '--apply-plan', plan_path, '--approve', identity, '--apply',
                                 '--backup-dir', self.root / 'join-backup')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.root / 'join-backup/book.md').read_text(), before)
        self.assertNotEqual(md.read_text(), before)
        self.assertTrue(md.read_text().startswith('左文。\n\n'))
        self.assertTrue(md.read_text().endswith('\n\n右文。'))

    def test_stale_join_source_prevents_write(self):
        md, old, source, plan_path, identity = self.join_fixture()
        before = md.read_bytes()
        (source / 'pages/p0021/p0021.md').write_text('OCR已变更。')
        result = self.run_script('join_split.py', md, old, source, '--pages', 'p0021-p0021',
                                 '--apply-plan', plan_path, '--approve', identity, '--apply',
                                 '--backup-dir', self.root / 'join-backup')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(md.read_bytes(), before)
        self.assertFalse((self.root / 'join-backup').exists())

    def test_join_preview_cannot_overwrite_book(self):
        md, old, source, _, _ = self.join_fixture()
        before = md.read_bytes()
        result = self.run_script('join_split.py', md, old, source, '--pages', 'p0021-p0021', '--plan', md)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(md.read_bytes(), before)

    def test_translator_note_and_index_are_not_joins(self):
        text = '*m.表示结婚。——译者注\n\n圆处。两年前他们收养女儿。\n\nSystems,12系统\n\nSubsystems,13子系统'
        source = self.sources(text.replace('\n\n', ''))
        md, old = self.root / 'book.md', self.root / 'old.md'
        md.write_text(text); old.write_text(text)
        self.assertEqual(join_split.build_plan(md, old, [source], [21, 21])['books'][0]['changes'], [])

    def test_bare_apply_rejected(self):
        md, old = self.root / 'book.md', self.root / 'old.md'
        md.write_text('原文。'); old.write_text('原文。')
        result = self.run_script('join_split.py', md, old, self.root, '--apply')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(md.read_text(), '原文。')

    def format_jobs(self):
        md = self.root / 'book.md'
        md.write_text('外部正文。\n\n<!-- 补 p0021 -->\n框内第一句。第二句！\n<!-- /补 -->\n\n后续正文。')
        work = self.root / 'format'
        result = self.run_script('format_inserts.py', 'extract', md, work)
        self.assertEqual(result.returncode, 0, result.stderr)
        return md, work

    def test_missing_format_job_fails_without_removing_markers(self):
        md, work = self.format_jobs(); before = md.read_bytes()
        result = self.run_script('format_inserts.py', 'apply', md, work)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(md.read_bytes(), before)

    def test_format_job_cannot_remove_or_move_sentence_punctuation(self):
        md, work = self.format_jobs(); before = md.read_bytes()
        (work / 'jobs/000.out.txt').write_text('> 框内第一句第二句。！')
        result = self.run_script('format_inserts.py', 'apply', md, work)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(md.read_bytes(), before)

    def test_valid_format_changes_only_job_and_preserves_outside(self):
        md, work = self.format_jobs()
        (work / 'jobs/000.out.txt').write_text('> 框内第一句。\n> 第二句！')
        result = self.run_script('format_inserts.py', 'apply', md, work)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(md.read_text(), '外部正文。\n\n> 框内第一句。\n> 第二句！\n\n后续正文。')

    def test_crop_absent_context_never_defaults_to_page_start(self):
        row = {'context': '这个目标不在页中【i】但错误裁图不可蒙混', 'primary': 'i', 'secondary': ''}
        boxes, state = recheck_sheets.locate_checked(row, '页面开头碰巧有另一个英文名字', [('英文名字', [0, 0, 20, 20])])
        self.assertEqual(boxes, [])
        self.assertTrue(state.startswith('unlocated'))

    def test_wrong_nearby_crop_rejected_even_if_page_target_found(self):
        row = {'context': '先前正确上下文【i】正确后文必须可见', 'primary': 'i', 'secondary': ''}
        boxes, state = recheck_sheets.locate_checked(row, '先前正确上下文i正确后文必须可见', [('不相干的邻近句', [0, 0, 20, 20])])
        self.assertEqual(boxes, [])
        self.assertTrue(state.startswith('unlocated'))


@unittest.skipUnless(importlib.util.find_spec('PIL'), 'Run with the paddleocr Python for image-export tests')
class RecheckImageTests(Fixture):
    def test_full_export_labels_located_and_unlocated_and_records_evidence(self):
        from PIL import Image, ImageDraw
        vl, pp, review = (self.root / name for name in ('vl', 'pp', 'review'))
        for path in (vl / 'pages/p0021', vl / 'render', pp / 'pages/p0021', review):
            path.mkdir(parents=True)
        line = 'BEFOREcontextiAFTERcontext'
        (vl / 'pages/p0021/p0021.md').write_text(line)
        ocr = {'overall_ocr_res': {'rec_texts': [line], 'rec_boxes': [[30, 60, 500, 100]]}}
        (pp / 'pages/p0021/p0021_res.json').write_text(json.dumps(ocr))
        image = Image.new('RGB', (600, 800), 'white')
        ImageDraw.Draw(image).text((30, 70), line, fill='black')
        image.save(vl / 'render/p0021.png')
        (review / 'sites.tsv').write_text('n\tpage\tcontext\tprimary\tsecondary\n'
                                         '1\tp0021\tBEFOREcontext【i】AFTERcontext\ti\ti\n'
                                         '2\tp0021\tABSENTcontext【x】NOWHEREcontext\tx\tx\n')
        result = self.run_script('recheck_sheets.py', review, vl, pp, '1', '2')
        self.assertEqual(result.returncode, 0, result.stderr)
        records = contract.json_lines(review / 'recheck_manifest.jsonl')
        self.assertEqual(len(records), 2)
        self.assertTrue(records[0]['state'].startswith('candidate'))
        self.assertTrue(records[0]['boxes'])
        self.assertTrue(records[1]['state'].startswith('unlocated'))
        self.assertEqual(records[1]['boxes'], [])
        for row in records:
            self.assertFalse(row['reviewer_verified'])
            self.assertEqual(row['pdf_page'], 22)
            self.assertEqual(len(row['inputs']), 4)
            with Image.open(review / row['sheet']) as sheet:
                self.assertEqual(sheet.width, 1400)
                self.assertGreater(sheet.height, 800)
                self.assertLess(sheet.convert('L').getextrema()[0], 255)


if __name__ == '__main__':
    unittest.main()
