# One-time setup (new machine)

```bash
uv tool install --python 3.12 paddleocr --with paddlepaddle-gpu   # GPU 机; CPU/Mac 用 --with paddlepaddle
# Critical: the ocr extras required by pp_structurev3 are NOT in default deps; python-docx avoids a runtime error
uv pip install --python ~/.local/share/uv/tools/paddleocr/bin/python 'paddlex[ocr]' python-docx
```

`marker` (marker_single), `pandoc`, and `pdftotext`/`pdfimages`/`pdffonts` (poppler) must also be on PATH for the other routes.

Models download on first use to `~/.paddlex/official_models/` (pp_structurev3 ≈ 0.5GB, PaddleOCR-VL-1.6 ≈ 2GB). huggingface.co unreachable → `export PADDLE_PDX_MODEL_SOURCE=bos` (Baidu BOS; pdf_ocr.sh sets it automatically when HF is down).

**NixOS**: `export LD_LIBRARY_PATH=/run/opengl-driver/lib`, otherwise paddle fails with `libcuda.so.1: cannot open shared object file` (pdf_ocr.sh/preflight.sh set this). Verify:

```bash
LD_LIBRARY_PATH=/run/opengl-driver/lib ~/.local/share/uv/tools/paddleocr/bin/python -c "import paddle; paddle.utils.run_check()"
```
