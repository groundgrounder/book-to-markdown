#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""merge_pages.py <out.md> <page-results-dir> [more dirs...] [--pages N]
Merge per-page OCR output (pp_structurev3 / PaddleOCR-VL) into a single Markdown file:
- sorts pages by the number in the filename (book_12.md / p0012.md)
- inserts invisible page anchors <!-- 第N页 --> for traceability
- collects imgs/ from all dirs and validates <img> references
- pdf_ocr.sh layout (<dir>/pages/p0000/p0000.md + imgs/): images are renamed p0000_<name>
  — crop filenames only encode box coordinates, so two pages can produce the same name
- page count is checked against --pages N or <dir>/render/.pages (written by pdf_ocr.sh):
  an OOM crash makes paddleocr skip the remaining pages silently, and a gap at the END
  of the book is invisible to a min..max range check
"""
import os, re, shutil, sys

def collect(dirs):
    pages = {}  # page number -> (md path, imgs dir, image prefix)
    for d in dirs:
        sub = os.path.join(d, "pages")
        if os.path.isdir(sub):  # pdf_ocr.sh: one subdir per page
            for p in os.listdir(sub):
                m = re.fullmatch(r"p(\d+)", p)
                md = os.path.join(sub, p, p + ".md")
                if m and os.path.exists(md):
                    pages.setdefault(int(m.group(1)), (md, os.path.join(sub, p, "imgs"), p + "_"))
            continue
        for fn in os.listdir(d):  # flat layout (older runs)
            m = re.search(r"(\d+)\.md$", fn)
            if m and not fn.startswith("."):
                pages.setdefault(int(m.group(1)), (os.path.join(d, fn), os.path.join(d, "imgs"), ""))
    return pages

def expected_pages(dirs, argv):
    if "--pages" in argv:
        return int(argv[argv.index("--pages") + 1])
    for d in dirs:
        f = os.path.join(d, "render", ".pages")
        if os.path.exists(f):
            return int(open(f).read())
    return None

def main():
    argv = sys.argv[1:]
    if "--pages" in argv:
        i = argv.index("--pages"); args = argv[:i] + argv[i + 2:]
    else:
        args = argv
    out_md, dirs = os.path.abspath(args[0]), args[1:]
    title = os.path.splitext(os.path.basename(out_md))[0]
    pages = collect(dirs)
    if not pages:
        sys.exit("no per-page md files found")

    outdir = os.path.dirname(out_md)
    imgs_out = os.path.join(outdir, "imgs")
    os.makedirs(imgs_out, exist_ok=True)

    parts = [f"# {title}\n"]
    copied = set()
    for n in sorted(pages):
        md, imgs, prefix = pages[n]
        body = open(md, encoding="utf-8").read().strip()
        if prefix:
            body = re.sub(r'(src="|\]\()imgs/', rf"\1imgs/{prefix}", body)
        if os.path.isdir(imgs) and imgs not in copied:
            for img in os.listdir(imgs):
                shutil.copy2(os.path.join(imgs, img), os.path.join(imgs_out, prefix + img))
            copied.add(imgs)
        parts.append(f"\n\n<!-- 第{n + 1}页 -->\n\n{body}")
    text = "\n".join(parts) + "\n"
    open(out_md, "w", encoding="utf-8").write(text)

    refs = re.findall(r'(?:src="|\]\()imgs/([^")]+)', text)
    missing = [r for r in refs if not os.path.exists(os.path.join(imgs_out, r))]
    dd = text.count("$$")
    total = expected_pages(dirs, argv)
    last = (total - 1) if total else max(pages)
    gaps = [n + 1 for n in range(0, last + 1) if n not in pages]
    print(f"merged {len(pages)} pages -> {out_md}")
    print(f"image refs {len(refs)}, missing {len(missing)}" + (f" WARNING {missing[:3]}" if missing else " OK"))
    print(f"$$ delimiters {'balanced OK' if dd % 2 == 0 else 'ODD, needs fixing'}")
    print(f"pages {len(pages)}/{total if total else '?'}" + (f", MISSING {gaps[:20]}" if gaps else ", none missing"))
    if gaps:
        sys.exit(1)

if __name__ == "__main__":
    main()
