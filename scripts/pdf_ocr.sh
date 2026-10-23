#!/usr/bin/env bash
# pdf_ocr.sh <book.pdf> <outdir> [--engine vl|pp] [--formula] [--render SCALE] [--config CONFIG.yaml]
#            [--device DEV] [--precision fp16|fp32] [--mem 7G] [--chunk 40]
# 扫描版 PDF → 逐页 Markdown。先把每页渲染成 PNG，再分批喂给引擎；可断点续跑（已有 res.json 的页跳过）。
#   --engine vl  PaddleOCR-VL（doc_parser v1.6，默认）：整页 VLM，版面不丢段、中英混排空格正确
#   --engine pp  PP-StructureV3：传统检测+识别，作交叉核对的第二引擎（crosscheck.py）或无 GPU 时兜底
# 输出：<outdir>/<书名>/pages/p0000/{p0000.md, p0000_res.json, imgs/}，每页一个子目录（图片文件名只含坐标，
#       平铺在一个目录里会互相覆盖）；渲染图留在 <outdir>/<书名>/render/ 供 crosscheck.py 切图。
# 设备分档配置见 configs/（preflight.sh 会推荐）
set -u
export PATH="$HOME/.local/bin:$PATH"
SKILL_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PYPKG="$HOME/.local/share/uv/tools/paddleocr/bin/python"
# NixOS：CUDA 驱动库不在默认搜索路径，不加这一行 paddle 会静默退回 CPU（或 import 失败）
[ -e /run/opengl-driver/lib/libcuda.so.1 ] && export LD_LIBRARY_PATH="/run/opengl-driver/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
# huggingface 不可达时（国内网络）从百度 BOS 拉模型
if [ -z "${PADDLE_PDX_MODEL_SOURCE:-}" ] && ! curl -sI --max-time 5 https://huggingface.co > /dev/null 2>&1; then
  export PADDLE_PDX_MODEL_SOURCE=bos
fi

PDF="$1"; OUT="$2"; shift 2
ENGINE="vl"; FORMULA="False"; RENDER="2.0"; CONFIG=""; DEVICE=""; PRECISION=""; MEM=""; CHUNK=40
while [ $# -gt 0 ]; do
  case "$1" in
    --engine)  ENGINE="$2"; shift ;;
    --formula) FORMULA="True" ;;
    --render)  RENDER="$2"; shift ;;
    --config)  CONFIG="$2"; shift ;;
    --device)  DEVICE="$2"; shift ;;
    --precision) PRECISION="$2"; shift ;;
    --mem)     MEM="$2"; shift ;;
    --chunk)   CHUNK="$2"; shift ;;
  esac; shift
done

NAME=$(basename "$PDF" .pdf)
WORK="$OUT/$NAME"
mkdir -p "$WORK/render" "$WORK/pages"

# ---- 1. 渲染（已渲染的页跳过）----
# SCALE 2.0 = 144 DPI，与 PaddleX 直接读 PDF 时一致。超宽页（>800pt）用更小的 SCALE，否则视觉模型耗时暴涨。
"$PYPKG" - "$PDF" "$RENDER" "$WORK/render" <<'PY' || exit 1
import os, sys, pypdfium2 as pdfium
pdf, scale, outdir = sys.argv[1], float(sys.argv[2]), sys.argv[3]
doc = pdfium.PdfDocument(pdf)
n, wide, done = len(doc), 0, 0
for i in range(n):
    f = f"{outdir}/p{i:04d}.png"
    if os.path.exists(f): continue
    page = doc[i]
    if page.get_size()[0] > 800: wide += 1
    page.render(scale=scale).to_pil().save(f); done += 1
open(f"{outdir}/.pages", "w").write(str(n))
print(f"[pdf_ocr] {n} pages, rendered {done} new (scale={scale})" + (f"; ⚠️ {wide} 页超宽 >800pt，考虑 --render 1.0" if wide else ""))
PY
NPAGES=$(cat "$WORK/render/.pages")

# ---- 2. 引擎命令 ----
if [ "$ENGINE" = "vl" ]; then
  RUNNER=(paddleocr)
  # <10GB 显存：原版加载 PaddleOCR-VL 会 OOM，换低显存包装（权重先进内存 + 视觉编码器 bf16，见脚本注释）
  VRAM=$(nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits 2>/dev/null | head -1 | tr -d ' ')
  [ -n "$VRAM" ] && [ "$VRAM" -lt 10000 ] && RUNNER=("$PYPKG" "$SKILL_DIR/scripts/paddleocr_lowvram.py")
  # CUDA_LAUNCH_BLOCKING=1：本地后端在个别页上会卡死在 GPU kernel 里（异步竞态，单核 100%、GPU 0%、永不返回）。
  # 同一页实测：不加 1/5 成功，加了 3/3 成功、耗时不变。
  # 页眉/页脚/页码丢弃；脚注、旁注保留（v1.6 默认连 footnote/aside_text 也丢）
  CMD=(env CUDA_LAUNCH_BLOCKING=1 "${RUNNER[@]}" doc_parser --pipeline_version v1.6
       --markdown_ignore_labels number header header_image footer footer_image)
  [ -n "$DEVICE" ] && CMD+=(--device "$DEVICE")
else
  CMD=(paddleocr pp_structurev3 --use_formula_recognition "$FORMULA"
       --text_det_limit_type max --text_det_limit_side_len 2400)   # 不限尺寸时 300DPI 页的检测会爆显存
  [ -n "$CONFIG" ] && CMD+=(--paddlex_config "$CONFIG" --use_doc_orientation_classify False --use_doc_unwarping False)
  [ -n "$DEVICE" ] && CMD+=(--device "$DEVICE")
  [ -n "$PRECISION" ] && CMD+=(--precision "$PRECISION")
fi

# 长任务关进 systemd scope：OOM 只杀这一个进程，不会连带杀掉终端/桌面程序（曾因此丢过整个会话）
SCOPE=()
if command -v systemd-run > /dev/null 2>&1 && systemd-run --user --scope -q true 2>/dev/null; then
  [ -z "$MEM" ] && MEM="$(( $(awk '/MemTotal/{print int($2/1048576)}' /proc/meminfo) / 2 ))G"
  SCOPE=(systemd-run --user --scope -q -p MemoryMax="$MEM" -p MemorySwapMax=1G --)
fi

# ---- 3. 分批跑未完成的页 ----
# 看门狗：PaddleOCR-VL 本地后端偶发卡死（单核 100%、GPU 0%、永不返回；曾一页卡 8 小时）。
# CUDA_LAUNCH_BLOCKING=1 已消除已知的卡死，看门狗留作兜底。
# 判卡死看心跳（生成步是否还在走），不看出结果的间隔：VL 每 8 页才落一次盘，密集索引页一组要 5 分钟以上，
# 只看结果文件会误杀（家庭治疗概论索引 9 页被误杀 10 次）。
# 一批里连续 STALL 秒没有新页出结果 → 发 USR1 抓栈（写进 ocr.log）再杀。卡住的那页单独重跑一次，
# 还卡就记进 bad_pages 跳过，不让一页拖死整本书；最后按缺页报告。
STALL="${STALL:-300}"
echo "[pdf_ocr] OCR start: $NAME engine=$ENGINE config=${CONFIG:-default} mem=${MEM:-unlimited}"
BAD="$WORK/bad_pages"; touch "$BAD"
pending() { for f in "$WORK"/render/p*.png; do p=$(basename "$f" .png); [ -s "$WORK/pages/$p/${p}_res.json" ] || grep -qx "$p" "$BAD" || echo "$p"; done; }
SIZE=$CHUNK
BATCH=""
trap '[ -n "$BATCH" ] && rm -rf "$BATCH"' EXIT   # 被杀时也清掉 /tmp 里的批次目录
while :; do
  TODO=($(pending)); [ ${#TODO[@]} -eq 0 ] && break
  BATCH=$(mktemp -d /tmp/ocr_batch.XXXXXX)
  for p in "${TODO[@]:0:$SIZE}"; do ln -s "$(realpath "$WORK/render/$p.png")" "$BATCH/$p.png"; done
  echo "[pdf_ocr] $(date +%T) batch: ${TODO[0]}… x$(ls "$BATCH" | wc -l) (${#TODO[@]} pending)"
  HB="$BATCH/.heartbeat"   # paddleocr_lowvram.py 每个生成步刷新它；没有心跳文件时只看结果文件
  B2M_HEARTBEAT="$HB" "${SCOPE[@]}" "${CMD[@]}" -i "$BATCH" --save_path "$BATCH/out" >> "$WORK/ocr.log" 2>&1 &
  RUN=$!; SEEN=0; T0=$(date +%s)
  while kill -0 $RUN 2>/dev/null; do
    sleep 10
    N=$(ls "$BATCH"/out/*_res.json 2>/dev/null | wc -l)
    if [ "$N" -gt "$SEEN" ]; then SEEN=$N; T0=$(date +%s); continue; fi
    # 还在生成（心跳新鲜）就不算卡：密集的索引页一组 8 页能超过 5 分钟
    [ -e "$HB" ] && [ $(( $(date +%s) - $(stat -c %Y "$HB") )) -lt "$STALL" ] && continue
    if [ $(( $(date +%s) - T0 )) -gt "$STALL" ]; then
      PID=$(pgrep -f -- "-i $BATCH --save_path" | head -1)
      echo "[pdf_ocr]   ✗ ${STALL}s 无进展，判定卡死，抓栈后终止 (pid ${PID:-?})"
      echo "===== stall dump $(date +%T) =====" >> "$WORK/ocr.log"
      [ -n "$PID" ] && { kill -USR1 "$PID" 2>/dev/null; sleep 3; kill "$PID" 2>/dev/null; sleep 5; kill -9 "$PID" 2>/dev/null; }
      break
    fi
  done
  wait $RUN 2>/dev/null
  echo "[pdf_ocr]   batch end, $SEEN 页出结果"
  # 每页挪进自己的子目录
  for j in "$BATCH"/out/*_res.json; do
    [ -e "$j" ] || continue
    p=$(basename "$j" _res.json); d="$WORK/pages/$p"; mkdir -p "$d/imgs"
    mv "$BATCH/out/$p.md" "$d/" 2>/dev/null
    for img in $(grep -o 'imgs/[^")]*' "$d/$p.md" 2>/dev/null); do mv "$BATCH/out/$img" "$d/imgs/" 2>/dev/null; done
    mv "$j" "$d/"
  done
  rm -rf "$BATCH"
  # 一页都没出：先把这一批缩成单页找出是哪页卡；单页还不出 → 记坏页。
  # 连续 3 个坏页 = 多半是环境问题（模型加载 OOM、驱动），不是页面问题 → 停下，别把整本书都标坏
  if [ "$SEEN" -eq 0 ]; then
    if [ "$SIZE" -gt 1 ]; then SIZE=1
    else
      echo "${TODO[0]}" >> "$BAD"; echo "[pdf_ocr]   ✗ ${TODO[0]} 单独重跑仍无结果，记入 bad_pages 跳过"
      SIZE=$CHUNK; STREAK=$(( ${STREAK:-0} + 1 ))
      [ "$STREAK" -ge 3 ] && { echo "[pdf_ocr] ✗ 连续 3 页失败，疑似环境问题，停止（看 $WORK/ocr.log 末尾）"; break; }
    fi
  else
    SIZE=$CHUNK; STREAK=0
  fi
done

# ---- 4. 完整性：每一页都必须有结果（OOM 崩溃时 paddleocr 会静默跳过剩余页）----
MISSING=($(for f in "$WORK"/render/p*.png; do p=$(basename "$f" .png); [ -s "$WORK/pages/$p/${p}_res.json" ] || echo "$p"; done))
if [ ${#MISSING[@]} -gt 0 ]; then
  echo "[pdf_ocr] ✗ ${#MISSING[@]}/$NPAGES 页没有结果: ${MISSING[*]:0:10}"
  [ -s "$BAD" ] && echo "  其中坏页（引擎卡死）: $(tr '\n' ' ' < "$BAD")→ 用另一引擎的同页结果补（复制 pages/pNNNN/ 目录），或删 bad_pages 重试"
  echo "  其余缺页重跑同一命令即可续跑"
  exit 1
fi
echo "[pdf_ocr] done: $NPAGES/$NPAGES pages -> $WORK/pages"
