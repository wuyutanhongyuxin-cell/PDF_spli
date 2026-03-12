<p align="center">
  <img src="https://img.shields.io/badge/Python-3.9+-blue?logo=python&logoColor=white" alt="Python">
  <img src="https://img.shields.io/badge/License-MIT-green" alt="License">
  <img src="https://img.shields.io/badge/Platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey" alt="Platform">
</p>

# PDF Article Splitter

> **一键将学术论文合集 PDF 拆分为独立的单篇 PDF 文件**

许多学术期刊会将一期的所有论文合并成一个 PDF 文件发布。当你只需要其中几篇时，手动拆分既繁琐又容易出错。本工具通过 **五重智能检测策略** 自动识别每篇论文的起始位置，支持中英文论文，交互式确认后完成拆分。

---

## 功能特性

- **五重智能检测** — 文章类型标记、DOI+机构、期刊名+卷期号、Abstract+DOI/期刊、Abstract+作者名 五种策略层层递进
- **中文论文支持** — 自动识别中文作者名、摘要、关键词、中图分类号等学术标记
- **交互式确认** — 拆分前展示检测结果与统计信息，支持手动添加/删除/查看，避免误切
- **智能去重** — 自动检测 PDF 前后重复内容（扫描件常见），避免重复拆分
- **安全可靠** — 只读处理原始 PDF，不会修改源文件
- **跨平台** — 支持 Windows / macOS / Linux

---

## 快速开始

### 1. 安装依赖

```bash
pip install pypdf pdfplumber
```

### 2. 运行

```bash
python split_pdf_articles.py "你的论文合集.pdf"
```

### 3. 查看结果

拆分后的文件默认保存在 `你的论文合集_split/` 目录下：

```
你的论文合集_split/
├── 01_The Role of Working Memory in Language Comprehension.pdf
├── 02_Bilingual Advantages in Executive Function.pdf
├── 03_Neural Correlates of Semantic Processing.pdf
└── ...
```

---

## 使用详解

### 基本用法

```bash
python split_pdf_articles.py <PDF文件路径> [输出目录]
```

| 参数 | 说明 | 必填 |
|------|------|------|
| `<PDF文件路径>` | 要拆分的 PDF 文件 | 是 |
| `[输出目录]` | 拆分后文件的保存目录 | 否（默认: `文件名_split/`）|

### 示例

```bash
# 使用默认输出目录
python split_pdf_articles.py "Language-and-Cognition.pdf"

# 指定输出目录
python split_pdf_articles.py "Language-and-Cognition.pdf" "./output"
```

### 交互式操作

检测完成后，工具会显示结果预览并等待确认：

```
============================================================
📋 检测结果预览（你可以手动修正）
============================================================
  [01] p.  1- 18 (18页) | The Role of Working Memory in Language
  [02] p. 19- 35 (17页) | Bilingual Advantages in Executive Function
  [03] p. 36- 52 (17页) | Neural Correlates of Semantic Processing

  共 3 篇 | 平均 17.3 页/篇 | 最短 17 页 | 最长 18 页

------------------------------------------------------------
选项:
  回车  → 确认并开始切分
  a     → 手动添加一个起始页  (格式: a 页码)
  d     → 删除一个检测结果    (格式: d 序号)
  l     → 重新显示列表
  q     → 退出不切分
------------------------------------------------------------
```

| 命令 | 说明 | 示例 |
|------|------|------|
| `回车` 或 `y` | 确认并开始拆分 | |
| `a 页码` | 手动添加一个论文起始页 | `a 42` → 将第 42 页标记为新论文起始 |
| `d 序号` | 删除一条检测结果 | `d 3` → 删除第 3 条 |
| `l` | 重新显示当前列表 | |
| `q` | 退出，不执行拆分 | |

---

## 工作原理

```
 ┌─────────────────────────────────────────┐
 │            输入: 论文合集 PDF            │
 └──────────────────┬──────────────────────┘
                    ▼
 ┌─────────────────────────────────────────┐
 │     Step 1: 逐页提取文本 (pdfplumber)    │
 └──────────────────┬──────────────────────┘
                    ▼
 ┌─────────────────────────────────────────┐
 │     Step 2: 五策略检测论文起始页         │
 │                                         │
 │  策略1: 前5行文章类型标记(最可靠)        │
 │    "EMPIRICAL ARTICLE"                  │
 │    "RESEARCH ARTICLE" ...               │
 │                                         │
 │  策略2: DOI(前8行)+机构(前10行)+作者     │
 │    排除目录页, 支持中英文作者名         │
 │                                         │
 │  策略3: 前5行期刊名+卷期号+Abstract     │
 │    二次确认: 需同时有Abstract/Keywords   │
 │                                         │
 │  策略4: Abstract + (DOI 或 期刊名)       │
 │    前15行有Abstract, 前10行有DOI         │
 │    或前5行有期刊名                       │
 │                                         │
 │  策略5: Abstract/摘要 + 作者名(最宽松)   │
 │    覆盖中文论文: 摘要+中文作者/学术标记  │
 │    覆盖英文论文: Abstract+Author+Affil   │
 └──────────────────┬──────────────────────┘
                    ▼
 ┌─────────────────────────────────────────┐
 │     Step 3: 后处理过滤                   │
 │                                         │
 │  · 合并间距 <4页 的可疑误检(保留组首)   │
 │  · 强信号(Abstract/Keywords)绕过过滤    │
 │  · 检测前后重复内容并提示               │
 └──────────────────┬──────────────────────┘
                    ▼
 ┌─────────────────────────────────────────┐
 │     Step 4: 交互式确认与修正            │
 │     (显示统计: 总数/平均/最短/最长)      │
 └──────────────────┬──────────────────────┘
                    ▼
 ┌─────────────────────────────────────────┐
 │     Step 5: 按边界切分并保存 (pypdf)     │
 └──────────────────┬──────────────────────┘
                    ▼
 ┌─────────────────────────────────────────┐
 │        输出: 独立的单篇 PDF 文件         │
 └─────────────────────────────────────────┘
```

---

## 自定义配置

如果默认的检测规则无法匹配你的 PDF，可以编辑脚本顶部的配置区：

### 文章类型标记

```python
ARTICLE_TYPE_MARKERS = [
    r"EMPIRICAL\s+ARTICLE",
    r"REVIEW\s+ARTICLE",
    r"BRIEF\s+REPORT",
    # 添加你的 PDF 中使用的标记 ↓
    r"YOUR\s+CUSTOM\s+MARKER",
]
```

### 机构署名关键词

```python
AFFILIATION_MARKERS = [
    r"University",
    r"Department\s+of",
    # 添加更多机构类型 ↓
    r"Laboratory\s+of",
]
```

### 期刊名称（策略3）

```python
JOURNAL_NAME_MARKERS = [
    r"journal\s+of",
    r"cognition",
    r"modern\s+language\s+journal",
    # 添加你的 PDF 中包含的期刊 ↓
    r"your\s+journal\s+name",
]
```

### 检测参数调优

```python
MARKER_SCAN_LINES = 5        # 策略1/3: 扫描前几行
DOI_SCAN_LINES = 8           # 策略2: DOI 必须在前几行
AFFILIATION_SCAN_LINES = 10  # 策略2: 机构必须在前几行
ABSTRACT_SCAN_LINES = 20     # 策略4/5: Abstract 检测扫描行数
MIN_ARTICLE_PAGES = 4        # 相邻检测点最小间距
```

---

## 常见问题

<details>
<summary><b>Q: 未检测到任何论文边界？</b></summary>

可能的原因：
1. **扫描版 PDF**（纯图片）— 需要先用 OCR 工具转换为可搜索的 PDF
2. **论文格式不含预设关键词** — 编辑 `ARTICLE_TYPE_MARKERS` 添加你的 PDF 使用的标记
3. **PDF 有加密/权限限制** — 需要先解除限制
</details>

<details>
<summary><b>Q: 检测结果不准确怎么办？</b></summary>

工具提供了交互式修正功能：
- 用 `a 页码` 手动添加遗漏的论文起始页
- 用 `d 序号` 删除误检的结果
- 用 `l` 随时查看修改后的列表
</details>

<details>
<summary><b>Q: 支持中文论文吗？</b></summary>

原生支持！工具内置了中文学术论文检测能力：
- 识别 **摘要** / **关键词** 标记
- 识别中文作者名（如 "李哲, 王某某"）
- 识别 **中图分类号**、**基金项目**、**收稿日期** 等学术标记

只要 PDF 中的文本可被提取（非扫描版），工具就能自动检测中文论文边界。
</details>

<details>
<summary><b>Q: PDF 前后内容重复怎么办？</b></summary>

工具会自动检测 PDF 前后半部分是否包含重复内容（扫描件或合并错误常见）。
检测到重复时会提示你选择只处理前半部分或处理全部。
</details>

---

## 技术栈

| 库 | 用途 |
|----|------|
| [pypdf](https://github.com/py-pdf/pypdf) | PDF 页面读取与写入 |
| [pdfplumber](https://github.com/jsvine/pdfplumber) | 精确的 PDF 文本提取 |

---

## License

MIT License - 自由使用、修改和分发。
