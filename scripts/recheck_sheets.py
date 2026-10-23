#!/usr/bin/env python3
"""recheck_sheets.py REVIEW VL PP IDs...|@recheck.txt

Exports labelled crops and recheck_manifest.jsonl. Uncertain location uses a
full-page fallback, never the page-start text as a substitute target.
Candidate crops still require a reviewer to see the target and neighbors.
"""
import csv
import json
from pathlib import Path
import re
import sys

from crosscheck import locate, norm, ocr_lines
from review_contract import atomic_write, digest, read_text


def locate_checked(row, primary, lines):
    context = row['context'].replace('⏎', '\n').replace('\\n', '\n')
    if '【' not in context or '】' not in context:
        return [], 'unlocated: no bounded target context'
    left, rest = context.split('【', 1)
    middle, right = rest.split('】', 1)
    left, right = norm(left)[-30:], norm(right)[:30]
    if len(left) < 6 or len(right) < 6:
        return [], 'unlocated: insufficient outside context'
    choices = {norm(middle), norm(row.get('primary', '')), norm(row.get('secondary', '')),
               norm(row.get('insert', ''))}
    decision = row.get('decision', '')
    if decision.startswith('='):
        choices.add(norm(decision[1:]))
    found = set()
    current = norm(primary)
    for value in choices:
        probe = left + value + right
        at = current.find(probe)
        if at >= 0 and current.find(probe, at + 1) < 0:
            found.add((at, value))
    if len(found) != 1:
        return [], 'unlocated: current page context absent or ambiguous'
    _, value = found.pop()
    mid = norm(row.get('secondary', '')) or value
    boxes = locate(lines, (left, mid, right))
    selected = [norm(text) for text, box in lines if any(list(box) == list(candidate) for candidate in boxes)]
    joined = ''.join(selected)
    # Long enough exact local anchors must be inside the actual selected lines.
    # A plausible best-scoring line alone is insufficient.
    if not boxes or left[-6:] not in joined or right[:6] not in joined or (mid and mid not in joined):
        return [], 'unlocated: selected OCR lines do not contain target and both neighbors'
    return boxes, 'candidate: reviewer must confirm target visibility'


def main():
    from PIL import Image, ImageDraw, ImageFont
    review, primary, secondary = map(Path, sys.argv[1:4])
    ids = []
    for value in sys.argv[4:]:
        if value.startswith('@'):
            ids.extend(match.group(1) for match in re.finditer(r'#(\d+)\(([^;)]*)[;)]', read_text(value[1:]))
                       if match.group(2) != '未答')
        else:
            ids.append(value)
    ids = list(dict.fromkeys(ids))
    with (review / 'sites.tsv').open(encoding='utf-8', newline='') as stream:
        rows = {row['n']: row for row in csv.DictReader(stream, delimiter='\t')}
    font = ImageFont.load_default()
    crops, metadata = [], []
    for identity in ids:
        row = rows[identity]
        page = row['page']
        if not re.fullmatch(r'p\d{4}', page):
            raise ValueError('Invalid source-page ID')
        text_path = primary / 'pages' / page / (page + '.md')
        ocr_path = secondary / 'pages' / page / (page + '_res.json')
        image_path = primary / 'render' / (page + '.png')
        lines = ocr_lines(json.loads(read_text(ocr_path)))
        boxes, state = locate_checked(row, read_text(text_path), lines)
        with Image.open(image_path) as opened:
            image = opened.convert('RGB')
        if boxes:
            parts = [image.crop((max(0, int(box[0]) - 20), max(0, int(box[1]) - 10),
                                 min(image.width, int(box[2]) + 20), min(image.height, int(box[3]) + 10)))
                     for box in boxes]
        else:
            parts = [image]
        width, height = max(part.width for part in parts), sum(part.height for part in parts)
        crop = Image.new('RGB', (width, height), 'white')
        y = 0
        for part in parts:
            crop.paste(part, (0, y))
            y += part.height
        crop.thumbnail((1300, 1500))
        crops.append((row, state, crop))
        metadata.append({'site': identity, 'page': page, 'pdf_page': int(page[1:]) + 1,
                         'state': state, 'boxes': [list(map(float, box)) for box in boxes],
                         'target_context': row['context'], 'reviewer_verified': False,
                         'inputs': {str(path.resolve()): digest(path.read_bytes())
                                    for path in (text_path, ocr_path, image_path, review / 'sites.tsv')}})
    listing, index, sheet = [], 0, 0
    while index < len(crops):
        batch, height = [], 0
        while index < len(crops) and len(batch) < 12:
            row, state, crop = crops[index]
            if batch and height + crop.height + 48 > 1800:
                break
            batch.append((row, state, crop))
            height += crop.height + 48
            index += 1
        canvas = Image.new('RGB', (1400, height + 8), 'white')
        draw, y = ImageDraw.Draw(canvas), 4
        for row, state, crop in batch:
            label = f'#{row["n"]} {row["page"]} / PDF page {int(row["page"][1:]) + 1} / {state}'
            draw.text((5, y), label, fill='red' if state.startswith('unlocated') else 'black', font=font)
            canvas.paste(crop, (80, y + 24))
            listing.append(f'recheck_{sheet:02d} {label}\n')
            record = next(item for item in metadata if item['site'] == row['n'])
            record.update(sheet=f'recheck_{sheet:02d}.png', sheet_y=y)
            y += crop.height + 48
        canvas.save(review / f'recheck_{sheet:02d}.png')
        sheet += 1
    atomic_write(review / 'recheck_list.txt', ''.join(listing))
    atomic_write(review / 'recheck_manifest.jsonl', ''.join(json.dumps(item, ensure_ascii=False) + '\n' for item in metadata))
    print(f'{len(crops)} sites, {sheet} sheets; unlocated fallbacks: {sum(not item["boxes"] for item in metadata)}')


if __name__ == '__main__':
    main()
