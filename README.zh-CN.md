# book-to-markdown

[English](README.md) | **简体中文**

将扫描版 PDF、带文字层的 PDF 和 EPUB 转成干净的单文件 Markdown，保留图片、标题层级和嵌套目录。

[TODO: comparison image]

## 为什么用它

- **扫描版 PDF：** 以 PaddleOCR-VL 为主引擎，用 pp_structurev3 交叉比对，将审图重点缩小到两者的分歧处。试点覆盖 3 本教材、29 页，审图后整段正文丢失率为 0%。这只是试点结果；两个引擎共同误读的地方仍需抽查。
- **带文字层的 PDF：** 使用 marker，保留标题、表格、公式和图片，避免不必要的 OCR。
- **EPUB：** 使用 pandoc 提取数字文本和图片，再进行轻量的标记清理。
- **断点续跑：** 扫描版 PDF 任务中断后会跳过已完成的页面；批量工作流支持处理整个书架。

## 快速开始

以下命令均在仓库根目录运行。

### 1. 安装依赖

使用 [uv](https://docs.astral.sh/uv/) 安装 OCR 环境；如果使用 NVIDIA GPU，将 `paddlepaddle` 替换为 `paddlepaddle-gpu`。

```bash
uv tool install --python 3.12 paddleocr --with paddlepaddle
uv pip install --python ~/.local/share/uv/tools/paddleocr/bin/python 'paddlex[ocr]' python-docx
```

通过包管理器安装 EPUB 路线所需的 pandoc 和 PDF 路线所需的 Poppler；转换带文字层的 PDF 还需安装 `marker-pdf`。环境配置详见 [setup.md](references/setup.md)。

### 2. 检查环境

```bash
./scripts/preflight.sh /absolute/path/to/books
```

预检脚本检查 OCR 环境，并按设备情况输出推荐配置和扫描版 PDF 的命令模板；它不会安装依赖。

### 3. 转换一本书

先从 EPUB 开始，输入文件使用绝对路径：

```bash
./scripts/epub2md.sh /absolute/path/to/book.epub "$PWD/out"
```

结果位于 `out/book/book.md`，提取的图片保存在旁边的目录中。转换后按 [EPUB 整理清单](references/postprocess-epub.md)完成清理。PDF 请先按[路线判断与 OCR 流程](SKILL_DEV.md#step-1-detect-the-route-pdfs-only)转换，再按 [PDF 整理清单](references/postprocess-pdf.md)处理。转换脚本生成初稿，复核与清理完成后才是成品。

## 完整文档

`references/` 中的指南保留原有语言，主要为中文：

- [setup.md](references/setup.md) — 首次安装与环境配置。
- [postprocess-pdf.md](references/postprocess-pdf.md) / [postprocess-epub.md](references/postprocess-epub.md) — 转换后的内容清理。
- [batch.md](references/batch.md) — 批量处理书架与断点续跑。
- [patch-control.md](references/patch-control.md) — 对已经整理过的书重新 OCR 并修补。

[SKILL_DEV.md](SKILL_DEV.md) 是供 Claude Code skill 使用的内部文档，包含双引擎流程、质量门禁和已知问题。

## 阅读转换结果

[Hortus](https://github.com/groundgrounder/Hortus) 可以将大型 Mermaid 图表分栏显示，让文字保持可读。它是一款采用 Rust 核心的原生 Mac 应用，不使用 WebView。

## 环境要求

- Python 3.12，通过 uv 管理，以及 Bash。
- 扫描版 PDF 需要 PaddleOCR、PaddlePaddle 和 `paddlex[ocr]` 扩展依赖。PaddleOCR-VL 推荐使用至少 6 GB 显存的 GPU；也可使用 pp_structurev3 的 CPU 路线，速度较慢。模型在首次使用时下载。
- 带文字层的 PDF 需要 `marker-pdf`（命令为 `marker_single`）。
- EPUB 转换需要 pandoc；PDF 检查需要 Poppler（`pdftotext`、`pdfimages`、`pdffonts`）。这些工具需单独安装，预检脚本不会代为安装。

## 许可证

[MIT](LICENSE)
