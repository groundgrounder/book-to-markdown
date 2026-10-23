#!/usr/bin/env bash
# preflight.sh [书架目录] — 开工前设备与环境体检, 输出推荐配置
# 不改变任何文件, 只读检测 + 打印建议
set -u
SKILL_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PYPKG="${PYPKG:-$HOME/.local/share/uv/tools/paddleocr/bin/python}"
# NixOS：驱动库在 /run/opengl-driver/lib，不加则 paddle 报 libcuda.so.1 找不到、被误判为无 GPU
[ -e /run/opengl-driver/lib/libcuda.so.1 ] && export LD_LIBRARY_PATH="/run/opengl-driver/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
BOOKSHELF="${1:-}"

echo "================= book-to-markdown 开工前体检 ================="
TIER=""; NOTES=""

# ---- 1. 算力 ----
echo "── 算力 ──"
if [ ! -x "$PYPKG" ]; then
  echo "✗ paddleocr 未安装 (找不到 $PYPKG)"
  echo "  先运行: uv tool install --python 3.12 paddleocr --with paddlepaddle-gpu   # GPU 机"
  echo "        uv tool install --python 3.12 paddleocr --with paddlepaddle       # CPU/Mac"
  echo "        uv pip install --python ~/.local/share/uv/tools/paddleocr/bin/python 'paddlex[ocr]' python-docx"
  exit 1
fi
CUDA=$("$PYPKG" -c "import paddle; print(paddle.device.is_compiled_with_cuda())" 2>/dev/null || echo "错误")
echo "paddle CUDA 支持: $CUDA"

VRAM=0
if command -v nvidia-smi > /dev/null 2>&1; then
  VRAM=$(nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits 2>/dev/null | head -1 | tr -d ' ')
  GPU_NAME=$(nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null | head -1)
  echo "GPU: $GPU_NAME, 显存 ${VRAM}MB"
fi

# RAM (MB)
if [ "$(uname)" = "Darwin" ]; then
  RAM=$(( $(sysctl -n hw.memsize) / 1048576 ))
else
  RAM=$(awk '/MemTotal/{print int($2/1024)}' /proc/meminfo 2>/dev/null || echo 0)
fi
echo "RAM: ${RAM}MB"
[ "$RAM" -lt 16384 ] && NOTES="${NOTES}\n⚠️  RAM<16GB: 默认不要开 --formula (公式模型 warmup 需约 4GB 空闲)"

# 分档（PP 副引擎的配置；主引擎 PaddleOCR-VL 6GB 起可跑，<10GB 自动走 paddleocr_lowvram.py）
if [ "$CUDA" = "True" ]; then
  if [ "$VRAM" -ge 16000 ]; then TIER="full (GPU 大显存): configs/paddlex_full.yaml"
  elif [ "$VRAM" -ge 6000 ]; then TIER="balanced (GPU 中显存): configs/paddlex_balanced.yaml + --precision fp16"
  else TIER="lite (GPU 小显存): configs/paddlex_lite.yaml + --precision fp16"
    NOTES="${NOTES}\n⚠️  显存 <6GB: PaddleOCR-VL 放不下，只能走 PP lite（版面模型会整段漏正文，必须跑 orphan_check.py）"; fi
else
  TIER="full (CPU): configs/paddlex_full.yaml, fp32; 文字层 PDF 优先走 marker"
  NOTES="${NOTES}\nℹ️  CPU 路线约 10–30 秒/页, 建议配合批量模式断点续跑"
fi

# ---- 2. 存储 ----
echo "── 存储 ──"
TARGET="${BOOKSHELF:-$PWD}"
FREE_KB=$(df -k "$TARGET" 2>/dev/null | tail -1 | awk '{print $4}')
FREE_GB=$(( FREE_KB / 1048576 ))
echo "目标目录 $TARGET 可用空间: ${FREE_GB}GB"
if [ -n "$BOOKSHELF" ]; then
  PAGES_EST=$(find "$TARGET" -name "*.pdf" -not -name "._*" 2>/dev/null | wc -l | tr -d ' ')
  echo "PDF 数量: $PAGES_EST (按平均 400 页估中间产物: 每本约 0.5–2GB 调试图, 成品另计)"
  [ "$FREE_GB" -lt 30 ] && NOTES="${NOTES}\n⚠️  可用空间 <30GB: 建议逐本清理 work 目录(批量模式默认会做)"
fi

# ---- 3. 网络 ----
echo "── 网络 ──"
if curl -sI --max-time 5 https://huggingface.co > /dev/null 2>&1; then
  echo "huggingface.co 可达 ✓"
else
  echo "huggingface.co 不可达 → marker 用 export HF_ENDPOINT=https://hf-mirror.com；"
  echo "  PaddleOCR 模型用 export PADDLE_PDX_MODEL_SOURCE=bos（pdf_ocr.sh 会自动设）"
  curl -sI --max-time 5 https://hf-mirror.com > /dev/null 2>&1 && echo "hf-mirror.com 可达 ✓" || echo "hf-mirror.com 也不可达 ✗"
fi
command -v systemd-run > /dev/null 2>&1 && systemd-run --user --scope -q true 2>/dev/null \
  && echo "systemd-run 可用 ✓（pdf_ocr.sh 会把 OCR 关进内存限额 scope，OOM 不会波及桌面）"

# ---- 4. 电源 ----
echo "── 电源 ──"
if [ "$(uname)" = "Darwin" ]; then
  pmset -g batt 2>/dev/null | head -2 | tail -1
  pmset -g batt 2>/dev/null | grep -q "Battery Power" && NOTES="${NOTES}\n⚠️  正在用电池: 长任务请接电源并 caffeinate -dims; 合盖不睡仅在外接电源时有效"
fi

# ---- 5. 书架预检 ----
if [ -n "$BOOKSHELF" ]; then
  echo "── 书架预检 ──"
  [ -d "$BOOKSHELF/.stfolder" ] && NOTES="${NOTES}\n⚠️  检测到 Syncthing 同步目录: 删除原文件会传播到所有设备, 成品/删除也会同步(可用于双机协作)"
  # 同名冲突(Python 按 NFC 归一比较, 避免 macOS NFD 误报)
  COLLIDE=$("$PYPKG" - "$TARGET" <<'PY'
import sys, os, unicodedata
from collections import defaultdict
m = defaultdict(set)
for dirpath, _, files in os.walk(sys.argv[1]):
    if "/.st" in dirpath: continue
    for fn in files:
        if fn.startswith("._"): continue
        b, e = os.path.splitext(fn)
        if e.lower() in (".pdf", ".epub"):
            m[unicodedata.normalize("NFC", os.path.join(dirpath, b))].add(e.lower())
print(sum(1 for v in m.values() if len(v) > 1))
PY
)
  [ "$COLLIDE" -gt 0 ] && NOTES="${NOTES}\n⚠️  ${COLLIDE} 组同名 PDF+EPUB: 交付时会互相覆盖, 需在计划中指定优先级(建议 EPUB 路线为准)"
  # 超宽页抽查(前 5 本)
  "$PYPKG" - "$TARGET" <<'PY' 2>/dev/null
import sys, os, glob
import pypdfium2 as pdfium
n = 0
for p in glob.glob(os.path.join(sys.argv[1], "**/*.pdf"), recursive=True)[:60]:
    try:
        d = pdfium.PdfDocument(p); w, h = d[0].get_size(); d.close()
        if w > 800: n += 1
    except Exception: pass
if n: print(f"超宽页(>800pt)样例检出: {n} 本 → 这些书需要 --render")
else: print("超宽页抽查: 未发现(>800pt)")
PY
fi

# ---- 结论 ----
echo "================= 推荐 ================="
echo "PP 配置档位: $TIER"
CFG=$(echo "$TIER" | grep -o 'configs/[a-z_]*\.yaml' | head -1)
PREC=$(echo "$TIER" | grep -q fp16 && echo " --precision fp16")
DEV=$([ "$CUDA" = "True" ] && echo " --device gpu" || echo " --device cpu")
echo "命令模板（扫描版，双引擎）:"
echo "  $SKILL_DIR/scripts/pdf_ocr.sh <book.pdf> <work>/vl --engine vl$DEV"
echo "  $SKILL_DIR/scripts/pdf_ocr.sh <book.pdf> <work>/pp --engine pp --config $SKILL_DIR/$CFG$DEV$PREC"
echo "  $SKILL_DIR/scripts/crosscheck.py <work>/vl/<书名> <work>/pp/<书名> <work>/review --pdf <book.pdf>"
[ -n "$NOTES" ] && echo "── 注意事项 ──$(echo -e "$NOTES")"
echo "=============================================="
