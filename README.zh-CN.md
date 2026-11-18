# book-to-markdown

[English](README.md) | **简体中文**

将扫描版 PDF、带文字层的 PDF 和 EPUB 转成干净的单文件 Markdown，保留图片、标题层级和嵌套目录。

供 **Claude Code、Codex 和 pi** 使用的 agent skill。把原书和输出位置交给 agent，它会完成环境检查、路线选择、转换、内容整理和最终校验。

## 工作方式

| 输入格式 | 转换路线 | 工作流处理方式 |
| --- | --- | --- |
| 扫描版 PDF | PaddleOCR-VL + pp_structurev3 | 交叉比对两个 OCR 引擎，并对照原页审看分歧。 |
| 带文字层的 PDF | marker | 使用内嵌文字，保留标题、表格、公式和图片，避免不必要的 OCR。 |
| EPUB | pandoc | 提取数字文本和图片，再清理标记。 |

此外还支持可断点续跑的书架批量处理、用审图后的 OCR 修补现有 Markdown，以及 Markdown → EPUB 导出。

**实战与试点：** 批量工作流已在 277 本 / 8.7 万页实际书库中跑通；逐页对照原图定金标准的试点（3 本扫描教材、29 页）中，双引擎审图后整段正文丢失率从单引擎旧版面模型的 9.2% 降至 0%。两引擎共同误读和原书错印仍需对照原书抽查。

## 快速开始

### 1. 克隆并安装

```bash
git clone https://github.com/groundgrounder/book-to-markdown.git
```

然后把下面这段话发给你的 agent：

```text
将 /absolute/path/to/book-to-markdown 中的 book-to-markdown skill
安装到你的个人 skills 目录。保留 SKILL.md、scripts/、references/、
configs/ 和 LICENSE，并保持它们的相对路径。
完成后告诉我 skill 是否已可用，以及如何调用。
```

| Agent | 个人 skill 目录 | 请求开头使用 |
| --- | --- | --- |
| Claude Code | `~/.claude/skills/book-to-markdown/` | `/book-to-markdown` |
| Codex | `~/.codex/skills/book-to-markdown/` | `$book-to-markdown` |
| pi | `~/.agents/skills/book-to-markdown/` | `/skill:book-to-markdown` |

安装后开启一个新会话；pi 也可以执行 `/reload`。之后 agent 可在转书任务中自动选用该 skill，你也可以用表中的命令显式调用。各宿主的说明见 [Claude Code](https://code.claude.com/docs/en/skills)、[Codex](https://developers.openai.com/codex/skills/) 和 [pi](https://github.com/badlogic/pi-mono/blob/main/packages/coding-agent/docs/skills.md) 文档。

如果只想临时使用一次，无需安装，可让具有本地文件和终端访问能力的 agent 阅读 `/absolute/path/to/book-to-markdown/SKILL.md`，并遵循其中的工作流。

### 2. 检查运行环境

```bash
bash /absolute/path/to/book-to-markdown/scripts/preflight.sh /absolute/path/to/books
```

预检不会修改文件，只报告硬件、可用工具、磁盘空间和建议的 OCR 配置（未装 OCR 环境时会提示，不会阻塞 EPUB 或文字层 PDF 路线），不会安装依赖。首次在新机器上使用时，按[安装指南](references/setup.md)配置所选路线需要的工具。

### 3. 转换第一本书

> 开始付费转换前，如果 agent 宿主或 API 服务商支持，请先设置硬性的用量或费用上限。付费或多书任务还应约定总预算：重试和审图可能消耗大量 token。

将路径换成你自己的，然后向 agent 发送：

```text
把 /absolute/path/to/book.pdf 转成单文件 Markdown，
放到 /absolute/path/to/output，图片放在旁边的目录中。
先检查环境，配置这本书所需的依赖，再判断转换路线。
保留标题、表格、公式和图片，保留原书文件。
完成内容整理和最终校验，并告诉我还有哪些地方需要复核。
```

EPUB 也可以使用同样的请求。具体命令由 agent 执行。处理扫描版时，请使用能查看页面图片的 agent 或模型，以便对照原页审看 OCR 分歧。

## 更多用法

用可断点续跑的计划转换整个书架：

```text
使用 book-to-markdown 转换 /absolute/path/to/books 中的 PDF 和 EPUB。
先建立可断点续跑的批量计划。付费调用前先约定总预算，
保留原书文件，并逐本报告完成情况和待复核项。
```

重新 OCR 一本书，同时保留已有结构：

```text
使用 book-to-markdown 对 /absolute/path/to/book.pdf 重新 OCR，
修补 /absolute/path/to/cleaned.md，保留已有结构和排版。
使用审图确认后的 OCR 结果，备份原文件，并校验每个改动区域。
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
