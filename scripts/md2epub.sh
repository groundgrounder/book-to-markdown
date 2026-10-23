#!/bin/bash
# md2epub.sh <book.md> — 由 markdown 生成同名 epub (图片内嵌, 按 H2 分章)
# 阅读器固定 -f gfm: 本 skill 的 md 均为 gfm 产出, 默认 markdown 阅读器会静默吞掉部分 <img>(无警告)
# 数学书(书名含数学/代数/几何/分析)自动走 MathJax, 避免 texmath 在大公式量上卡死
set -eu
MD="$1"
BASE="${MD%.md}"
EPUB="$BASE.epub"
DIR=$(dirname "$BASE"); NAME=$(basename "$BASE")
[ -f "$MD" ] || { echo "no such file: $MD"; exit 1; }

LANG="zh-CN"
python3 -c "import re,sys; sys.exit(0 if re.search(r'[一-鿿]', open('$MD',encoding='utf-8').read(20000)) else 1)" 2>/dev/null || LANG="en"

MATHFLAG=""
case "$NAME" in
  *数学*|*代数*|*几何*|*分析*|*微积*|*概率*|*方程*|*物理*) MATHFLAG="--mathjax" ;;
esac

COVERFLAG=""
[ -f "$DIR/cover.jpg" ] && COVERFLAG="--epub-cover-image=$DIR/cover.jpg"

pandoc "$MD" -f gfm -o "$EPUB.tmp.epub" \
  --resource-path="$DIR" --metadata title="$NAME" --metadata lang="$LANG" \
  --split-level=2 $MATHFLAG $COVERFLAG
EP_SIZE=$(stat -c%s "$EPUB.tmp.epub" 2>/dev/null || stat -f%z "$EPUB.tmp.epub")
if [ "$EP_SIZE" -lt 3000 ]; then echo "epub too small, abort"; rm -f "$EPUB.tmp.epub"; exit 1; fi

# 三重图片核验: md引用数 = epub media数 = 正文<img>数 (pandoc 吞图无警告, 只有对数能抓到)
python3 - "$MD" "$EPUB.tmp.epub" <<'EOF'
import re, sys, zipfile
from urllib.parse import unquote
t = re.sub(r"```.*?```", "", open(sys.argv[1], encoding="utf-8").read(), flags=re.S)
refs = {unquote(m) for m in re.findall(r'<img[^>]*src="([^"]+)"', t)} | \
       {unquote(m) for m in re.findall(r'!\[[^\]]*\]\(([^)\s]+)', t)}
refs = {x for x in refs if not x.startswith(("http://", "https://", "data:"))}
z = zipfile.ZipFile(sys.argv[2])
media = [n for n in z.namelist() if re.search(r'/media/', n)]
himgs = sum(len(re.findall(r'<img', z.read(n).decode("utf-8", "replace")))
            for n in z.namelist() if n.endswith((".xhtml", ".html")))
if not (len(refs) == len(media) == himgs):
    print(f"IMAGE MISMATCH: md引用={len(refs)} media={len(media)} html_img={himgs}", file=sys.stderr)
    sys.exit(1)
print(f"images: {len(refs)}/{len(media)}/{himgs}")
EOF

mv "$EPUB.tmp.epub" "$EPUB"
echo "OK: $EPUB (${EP_SIZE}B)${MATHFLAG:+ [mathjax]}${COVERFLAG:+ [cover]}"
