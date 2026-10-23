# book-to-markdown

[English](README.md) | **简体中文**

供 **Claude Code、Codex 和 pi** 使用的 agent skill，将扫描版 PDF、带文字层的 PDF 和 EPUB 转成干净的 Markdown，保留图片、标题层级和嵌套目录。

把书的位置和输出要求告诉 agent，skill 会指导它完成环境检查、路线判断、转换、OCR 审图、内容整理和最终校验。

[TODO: comparison image]

## 安装 skill

先将本仓库下载或克隆到本地，再把下面这段话发给你的 agent：

```text
将 /absolute/path/to/book-to-markdown 中的 book-to-markdown skill
安装到你的个人 skills 目录。保留 SKILL.md、SKILL_DEV.md、scripts/、
references/、configs/ 和 LICENSE，并保持它们的相对路径。
完成后告诉我 skill 是否已可用，以及如何调用。
```

不同 agent 使用的安装位置和调用方式如下：

| Agent | 个人 skill 目录 | 请求开头使用 |
| --- | --- | --- |
| Claude Code | `~/.claude/skills/book-to-markdown/` | `/book-to-markdown` |
| Codex | `~/.codex/skills/book-to-markdown/` | `$book-to-markdown` |
| pi | `~/.agents/skills/book-to-markdown/` | `/skill:book-to-markdown` |

安装后开启一个新会话；pi 也可以执行 `/reload`。之后 agent 可根据 skill 描述在转书任务中自动选用它，你也可以用表中的命令显式调用。各宿主的说明见 [Claude Code](https://code.claude.com/docs/en/skills)、[Codex](https://developers.openai.com/codex/skills/) 和 [pi](https://github.com/badlogic/pi-mono/blob/main/packages/coding-agent/docs/skills.md) 文档。

如果只想临时使用一次，无需安装，也可以对具有本地文件和终端访问能力的 agent 说：

```text
阅读 /absolute/path/to/book-to-markdown/SKILL.md，
按照其中的工作流完成下面的转书请求。
```

## 让 agent 转换一本书

加载 skill 后，可以直接发出下面这样的请求。将路径换成你自己的，EPUB 也适用：

```text
把 /absolute/path/to/book.pdf 转成单文件 Markdown，
放到 /absolute/path/to/output，图片放在旁边的目录中。
先检查环境，配置这本书所需的依赖，再判断转换路线。
保留标题、表格、公式和图片，保留原书文件。
完成内容整理和最终校验，并告诉我还有哪些地方需要复核。
```

具体命令由 agent 执行。处理扫描版时，请使用能查看页面图片的 agent／模型：工作流会交叉比对两个 OCR 引擎，并对照原页裁决分歧。

处理整个书架时，可以这样说：

```text
使用 book-to-markdown 转换 /absolute/path/to/books 中的 PDF 和 EPUB。
先建立可断点续跑的批量计划。付费调用前先约定总预算，
保留原书文件，并逐本报告完成情况和待复核项。
```

已经整理过的书，可以这样重新 OCR：

```text
使用 book-to-markdown 对 /absolute/path/to/book.pdf 重新 OCR，
修补 /absolute/path/to/cleaned.md，保留已有结构和排版。
使用审图确认后的 OCR 结果，备份原文件，并校验每个改动区域。
```

## 为什么用它

- **扫描版 PDF：** 以 PaddleOCR-VL 为主引擎，用 pp_structurev3 交叉比对，将审图重点缩小到分歧处。试点覆盖 3 本教材、29 页，审图后整段正文丢失率为 0%。这只是试点结果；两个引擎共同误读的地方仍需抽查。
- **带文字层的 PDF：** 使用 marker，保留标题、表格、公式和图片，避免不必要的 OCR。
- **EPUB：** 使用 pandoc 提取数字文本和图片，再清理标记。
- **断点续跑：** 扫描版 PDF 任务中断后会跳过已完成的页面；批量计划跟踪整个书架的进度。

## 运行环境

agent 需要能访问原书、执行终端命令，并写入输出目录。它会按随附的安装指南检查并安装所选路线需要的工具：

| 路线 | 转换工具 |
| --- | --- |
| EPUB | pandoc |
| 带文字层的 PDF | marker-pdf（`marker_single`）、Poppler |
| 扫描版 PDF | PaddleOCR、PaddlePaddle、`paddlex[ocr]`；PaddleOCR-VL 推荐使用至少 6 GB 显存的 GPU。也可使用速度较慢的 pp_structurev3 CPU 路线。 |

脚本使用 Bash 和 Python；OCR 环境通过 uv 配置 Python 3.12，模型在首次使用时下载。agent 的使用权限以及模型／API 费用取决于你选择的宿主和服务商。预检脚本负责检查环境和输出建议，不会自行安装依赖。

## 工作流与文档

[SKILL.md](SKILL.md) 是 agent 入口，[SKILL_DEV.md](SKILL_DEV.md) 包含完整的共用流程与质量门禁。`references/` 中的指南保留原有语言，主要为中文：

- [setup.md](references/setup.md) — 首次环境配置。
- [postprocess-pdf.md](references/postprocess-pdf.md) / [postprocess-epub.md](references/postprocess-epub.md) — 内容整理和复核清单。
- [batch.md](references/batch.md) — 可断点续跑的书架批量处理。
- [patch-control.md](references/patch-control.md) — 用新 OCR 修补已经整理过的书。

## 阅读转换结果

[Hortus](https://github.com/groundgrounder/Hortus) 可以将大型 Mermaid 图表分栏显示，让文字保持可读。它是一款采用 Rust 核心的原生 Mac 应用，不使用 WebView。

## 许可证

[MIT](LICENSE)
