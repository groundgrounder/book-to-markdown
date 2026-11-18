#!/usr/bin/env bash
# epub2md.sh <book.epub> <outdir>
set -eu
EPUB="$1"; OUT="$2"
NAME=$(basename "$EPUB" .epub)
mkdir -p "$OUT/$NAME"
cd "$OUT/$NAME"

pandoc "$EPUB" -t gfm --wrap=none --extract-media=media -o "$NAME.md"

python3 - "$NAME.md" <<'PY'
import re, sys
p = sys.argv[1]
t = open(p, encoding="utf-8").read()
t = re.sub(r"<svg[^>]*>.*?</svg>", "", t, flags=re.S)                       # SVG cover blocks
t = re.sub(r'^(#{1,6}\s*)<a [^>]*>(.*?)</a>\s*$', r"\1\2", t, flags=re.M)  # unwrap <a> in headings
noise = re.compile(r'^\s*(<span id="[^"]*"></span>|</?div[^>]*>|</?image[^>]*>|</?image>|</?a>|</?p[^>]*>)\s*$')
t = "\n".join(l for l in t.split("\n") if not noise.match(l))              # noise-only lines
t = re.sub(r'<span class="math-super">(.*?)</span>', r"<sup>\1</sup>", t)
t = re.sub(r"<a [^>]*>([^<]*)</a>", r"\1", t)                              # inline <a> -> plain text
t = re.sub(r"\\\n(?=\S)", "", t)                                           # trailing-\ hard breaks
t = re.sub(r"\n{3,}", "\n\n", t)
open(p, "w", encoding="utf-8").write(t.strip() + "\n")
print("cleaned:", p)
PY
echo "done: $OUT/$NAME/$NAME.md"
