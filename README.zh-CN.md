# book-to-markdown

[English](README.md) | **简体中文**

将扫描版 PDF、带文字层的 PDF 和 EPUB 转成干净的单文件 Markdown，保留图片、标题层级和嵌套目录。

供 **Claude Code、Codex 和 pi** 使用的 agent skill。把原书和输出目录交给 agent，它会自动完成环境检查、路线选择、转换、内容整理和最终校验。

## 工作方式

| 输入格式 | 转换路线 | 工作流处理方式 |
| --- | --- | --- |
| 扫描版 PDF | PaddleOCR-VL + pp_structurev3 | 交叉比对两个 OCR 引擎，并对照原页审看分歧。 |
| 带文字层的 PDF | marker | 使用内嵌文字，保留标题、表格、公式和图片，避免不必要的 OCR。 |
| EPUB | pandoc | 提取数字文本和图片，再清理标记。 |

此外还支持可断点续跑的书架批量处理、用审图后的 OCR 修补现有 Markdown，以及 Markdown → EPUB 导出。

**实战与试点：** 批量工作流已在 277 本 / 8.7 万页实际书库中跑通；逐页对照原图定金标准的试点（3 本扫描教材、29 页）中，双引擎审图后整段正文丢失率从单引擎旧版面模型的 9.2% 降至 0%。两引擎共同误读和原书错印仍需对照原书抽查。

## 安装

```bash
npx skills add groundgrounder/book-to-markdown -g
```

或者直接告诉你的 agent：

```text
安装 https://github.com/groundgrounder/book-to-markdown 这个 skill
```

<details>
<summary>手动安装或临时单次使用</summary>

- **手动安装：** 将本仓库克隆到 `~/.claude/skills/book-to-markdown/`（Claude Code）、`~/.codex/skills/book-to-markdown/`（Codex）或 `~/.agents/skills/book-to-markdown/`（pi），然后开启新会话（pi 可执行 `/reload`）。
- **免安装单次使用：** 让具备本地文件和终端访问权限的 agent 阅读 `/path/to/book-to-markdown/SKILL.md`，并遵循其中的工作流。

</details>

## 使用方式

> 开始付费转换前，如果 agent 宿主或 API 服务商支持，请先设置硬性的用量或费用上限；付费或多书任务还应约定总预算，避免重试和审图消耗过多 token。

直接向 agent 发指令（或显式以 `/book-to-markdown`、`$book-to-markdown`、`/skill:book-to-markdown` 开头）：

- **转换一本书**（PDF 或 EPUB 均可；扫描版需选用能看图的模型）：
  ```text
  把 /path/to/book.pdf 转成 Markdown，输出到 /path/to/output
  ```
- **批量转换整个书架**（可断点续跑）：
  ```text
  用 book-to-markdown 批量转换 /path/to/books 中的电子书，建立可断点续跑计划
  ```
- **对已整理书稿重新 OCR 修补**（保留原有结构）：
  ```text
  用 book-to-markdown 对 /path/to/book.pdf 重新 OCR，修补 /path/to/cleaned.md
  ```

agent 会自动执行预检和所需工具配置。如果想提前手动体检硬件与磁盘空间（只读，不安装依赖）：

```bash
bash /path/to/book-to-markdown/scripts/preflight.sh /path/to/books
```

## 运行环境

- agent 需要能访问原书、执行 macOS 或 Linux 终端命令（Windows 需通过 WSL），并写入输出目录；扫描版审图还需要能查看图片。
- Bash 和 Python。**只有扫描版 PDF 需要通过 `uv` 配置 Python 3.12、PaddleOCR 和 PaddlePaddle**；只转 EPUB（`pandoc`）或带文字层的 PDF（`marker-pdf` + Poppler）无需安装这套依赖或 GPU。
- `marker` 与 OCR 模型会在首次使用时下载。
- PaddleOCR-VL 推荐使用至少 6 GB 显存的 GPU；也可在 CPU 上跑 `pp_structurev3`（约 10–30 秒/页，更适合小册子或少量页面）。

模型调用权限与 API 费用取决于你选择的宿主和服务商。

## 文档

[SKILL.md](SKILL.md) 是 agent 入口，包含路线判断、核心命令和质量门禁。各路线详细指引按需放在 `references/` 中（保留原有语言，主要为中文）：

- [setup.md](references/setup.md) — 首次环境配置。
- [ocr-pipeline.md](references/ocr-pipeline.md) — 扫描版双引擎流程、低显存/CPU 分档、看门狗与审图工作流。
- [postprocess-pdf.md](references/postprocess-pdf.md) / [postprocess-epub.md](references/postprocess-epub.md) — 内容整理和复核清单。
- [batch.md](references/batch.md) — 可断点续跑的书架批量处理。
- [patch-control.md](references/patch-control.md) — 用审图后的 OCR 修补现有 Markdown。

## 阅读转换结果

如果你想在 macOS 上阅读转换后的长篇 Markdown 书籍，[Hortus](https://github.com/groundgrounder/Hortus) 是一款原生 Mac Markdown 阅读器（Rust 核心、无 WebView），在笔记或书籍包含大型 Mermaid 图表时也能分栏渲染以保持周围文字可读。

## 许可证

[MIT](LICENSE)
