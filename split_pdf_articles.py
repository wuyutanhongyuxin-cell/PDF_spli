#!/usr/bin/env python3
"""
PDF论文切分工具 — 将合集PDF中的每篇论文拆分为单独的PDF文件
=============================================================

使用方法:
    pip install pypdf pdfplumber
    python split_pdf_articles.py "Textbook-Language-and-cognition (1).pdf"

原理:
    扫描每一页的文本，通过关键词模式（如 "EMPIRICAL ARTICLE"、"REVIEW"、DOI模式等）
    检测每篇论文的起始页，然后按检测到的边界切分PDF。

作者: Claude (for Desheng @ SJTU)
日期: 2026-03
"""

import re
import os
import sys
from pathlib import Path

try:
    from pypdf import PdfReader, PdfWriter
except ImportError:
    print("❌ 缺少依赖，请先运行: pip install pypdf")
    sys.exit(1)

try:
    import pdfplumber
except ImportError:
    print("❌ 缺少依赖，请先运行: pip install pdfplumber")
    sys.exit(1)


# ============================================================
# 配置区 — 根据你的PDF实际情况调整
# ============================================================

# 论文起始页的关键标志词（不区分大小写）
# 仅在页面前5行中匹配，避免正文/参考文献中的同名小节标题误报
ARTICLE_TYPE_MARKERS = [
    r"EMPIRICAL\s+ARTICLE",
    r"REVIEW\s+ARTICLE",
    r"THEORETICAL\s+ARTICLE",
    r"BRIEF\s+REPORT",
    r"ORIGINAL\s+ARTICLE",
    r"RESEARCH\s+ARTICLE",
]

# 页面前几行用于匹配文章类型标记的行数
MARKER_SCAN_LINES = 5

# 相邻检测点之间的最小页数，低于此值视为可疑误检
MIN_ARTICLE_PAGES = 4

# DOI模式 — 论文首页通常会有DOI
DOI_PATTERN = r"https?://doi\.org/10\.\d{4,}"

# DOI 必须出现在页面前几行内才视为首页特征
# 有些论文的DOI在标题/作者之后的第7-8行
DOI_SCAN_LINES = 8

# 机构署名必须出现在页面前几行内
AFFILIATION_SCAN_LINES = 10

# 机构署名关键词
AFFILIATION_MARKERS = [
    r"University",
    r"Department\s+of",
    r"College\s+of",
    r"Institute\s+of",
    r"School\s+of",
]

# 作者署名行模式 — 匹配 "Firstname M. Lastname" 等常见格式
AUTHOR_NAME_PATTERN = re.compile(
    r"[A-Z][a-z]+\s+(?:[A-Z]\.\s*)?[A-Z][a-z]{2,}"  # e.g., "John M. Smith"
)

# 中文作者署名模式 — 匹配 "李哲" "吴诗玉" "王亦赟" 等2-4字中文姓名
# 或 "李哲, 王某某" 等逗号分隔的多作者格式
CHINESE_AUTHOR_PATTERN = re.compile(
    r"[\u4e00-\u9fff]{2,4}(?:\s*[,，、]\s*[\u4e00-\u9fff]{2,4})+"  # 至少两个中文名
)

# ── 策略3: 期刊名+卷期号模式 ──
# 卷期号模式: "108 (2011) 123" 或 "45:1115" 或 "Vol. 23, No. 4"
VOLUME_ISSUE_PATTERN = re.compile(
    r"(?:"
    r"\d{1,4}\s*\(\d{4}\)\s*\d+"         # 108 (2011) 123
    r"|Vol\.?\s*\d+,?\s*No\.?\s*\d+"      # Vol. 23, No. 4
    r"|\d{1,4}\s*:\s*\d{1,5}\s*[-–]\s*\d" # 45:1115-1135
    r")"
)

# ── 首页强信号: Abstract/Keywords ──
# 论文首页几乎都有 Abstract 或 Keywords，而中间页不会有
# 匹配独立成行的 Abstract/ABSTRACT/Keywords/关键词等
ABSTRACT_PATTERN = re.compile(
    r"^(?:abstract|摘\s*要|summary)$", re.IGNORECASE | re.MULTILINE
)
KEYWORDS_PATTERN = re.compile(
    r"^(?:keywords?|关\s*键\s*词|key\s+words?)\s*[:：]?\s*", re.IGNORECASE | re.MULTILINE
)

# Abstract 检测的扫描行数
ABSTRACT_SCAN_LINES = 20

# 中文学术标记 — 用于策略5检测中文论文首页
CHINESE_ACADEMIC_MARKERS = re.compile(
    r"(?:基金项目|收稿日期|作者简介|通讯作者|通信作者|中图分类号|文献标[识志]码)", re.IGNORECASE
)

# 期刊名候选（前5行匹配，不区分大小写）
# 这些是学术论文首页header中常见的期刊名称模式
JOURNAL_NAME_MARKERS = [
    r"journal\s+of",
    r"language\s+and\s+cognition",
    r"modern\s+language\s+journal",
    r"applied\s+linguistics",
    r"cognition",
    r"psychological\s+science",
    r"psycholinguist",
    r"second\s+language",
    r"bilingualism",
    r"studies\s+in\s+second\s+language",
    r"annual\s+review",
    r"frontiers\s+in",
    r"plos\s+one",
    r"nature",
    r"science",
    r"proceedings\s+of",
    r"memory\s+(?:&|and)\s+cognition",
]


def _extract_title_hint(lines: list[str]) -> str:
    """从页面前15行中提取最可能的论文标题。"""
    for line in lines[:15]:
        # 跳过期刊名、版权声明等
        if any(skip in line.lower() for skip in [
            "journal of", "\u00a9", "copyright", "issn", "vol.",
            "association", "doi.org", "sarmac", "published by",
            "elsevier", "springer", "wiley", "taylor & francis",
        ]):
            continue
        # 跳过文章类型标记本身
        if any(re.search(m, line, re.IGNORECASE) for m in ARTICLE_TYPE_MARKERS):
            continue
        # 跳过卷期号行
        if VOLUME_ISSUE_PATTERN.search(line):
            continue
        # 跳过 Abstract / Keywords 行
        if ABSTRACT_PATTERN.match(line) or KEYWORDS_PATTERN.match(line):
            continue
        # 标题通常是较长的行
        if len(line) > 20:
            return line[:80]
    return ""


def _has_abstract_keywords(lines: list[str], scan_lines: int = ABSTRACT_SCAN_LINES) -> bool:
    """检查页面前 scan_lines 行中是否包含 Abstract 或 Keywords。"""
    text = "\n".join(lines[:scan_lines])
    return bool(ABSTRACT_PATTERN.search(text) or KEYWORDS_PATTERN.search(text))


def detect_article_starts(
    pdf_path: str, verbose: bool = True
) -> tuple[list[dict], int]:
    """
    扫描PDF每一页，使用五种策略检测论文起始页。

    策略1: 页面前5行中的文章类型标记（最可靠）
    策略2: 页面前8行有DOI + 前10行有机构署名 + 作者姓名格式
    策略3: 页面前5行有期刊名+卷期号 + 前20行有Abstract/Keywords（二次确认）
    策略4: 前15行有Abstract + (前10行有DOI 或 前5行有期刊名)
    策略5: 前15行有Abstract/摘要 + 作者名+机构(英文) 或 中文作者/学术标记

    注意：检测阶段不做间距过滤，所有候选均记录，
    由后续 filter_short_gaps 做合并组处理。

    返回: ([{"page": ..., "title_hint": ..., "marker": ..., "strong": bool}, ...], 总页数)
    """
    articles = []

    if verbose:
        print(f"📖 正在扫描: {pdf_path}")

    with pdfplumber.open(pdf_path) as pdf:
        total_pages = len(pdf.pages)
        if verbose:
            print(f"   总页数: {total_pages}")

        for i, page in enumerate(pdf.pages):
            text = page.extract_text() or ""

            # 跳过空白页或极短页
            if len(text.strip()) < 50:
                continue

            is_article_start = False
            marker_found = ""
            lines = [l.strip() for l in text.split("\n") if l.strip()]

            # ── 策略1: 文章类型标记（仅前5行，最可靠）──
            top_marker_text = "\n".join(lines[:MARKER_SCAN_LINES])
            for marker in ARTICLE_TYPE_MARKERS:
                if re.search(marker, top_marker_text, re.IGNORECASE):
                    is_article_start = True
                    marker_found = marker
                    break

            # ── 策略2: DOI(前8行) + 机构(前10行) + 作者姓名 ──
            if not is_article_start:
                top_doi_text = "\n".join(lines[:DOI_SCAN_LINES])
                doi_in_top = re.findall(DOI_PATTERN, top_doi_text)

                if len(doi_in_top) >= 1:
                    top_affil_text = "\n".join(lines[:AFFILIATION_SCAN_LINES])
                    has_affiliation = any(
                        re.search(m, top_affil_text, re.IGNORECASE)
                        for m in AFFILIATION_MARKERS
                    )
                    # 支持英文和中文作者名
                    has_author = bool(
                        AUTHOR_NAME_PATTERN.search(top_affil_text)
                        or CHINESE_AUTHOR_PATTERN.search(top_affil_text)
                    )

                    if has_affiliation and has_author:
                        # 排除目录页
                        top_count = min(max(len(lines) // 3, 5), len(lines))
                        top_third = "\n".join(lines[:top_count])
                        toc_count = len(
                            re.findall(r"\.\s*\d{1,3}\s*$", top_third, re.MULTILINE)
                        )
                        if toc_count < 3:
                            is_article_start = True
                            marker_found = "DOI+Affiliation"

            # ── 策略3: 期刊名(前5行) + 卷期号(前5行) + Abstract/Keywords二次确认 ──
            if not is_article_start:
                top_journal_text = "\n".join(lines[:MARKER_SCAN_LINES])
                has_journal = any(
                    re.search(m, top_journal_text, re.IGNORECASE)
                    for m in JOURNAL_NAME_MARKERS
                )
                has_volume = bool(VOLUME_ISSUE_PATTERN.search(top_journal_text))

                if has_journal and has_volume and _has_abstract_keywords(lines):
                    is_article_start = True
                    marker_found = "Journal+Volume+Abstract"

            # ── 策略4: Abstract/Keywords + (DOI在前10行 或 期刊名在前5行) ──
            if not is_article_start:
                if _has_abstract_keywords(lines, scan_lines=15):
                    top_doi_text = "\n".join(lines[:DOI_SCAN_LINES + 2])
                    has_doi = bool(re.search(DOI_PATTERN, top_doi_text))
                    top_journal_text = "\n".join(lines[:MARKER_SCAN_LINES])
                    has_journal = any(
                        re.search(m, top_journal_text, re.IGNORECASE)
                        for m in JOURNAL_NAME_MARKERS
                    )
                    if has_doi or has_journal:
                        is_article_start = True
                        marker_found = "Abstract+DOI/Journal"

            # ── 策略5: Abstract/摘要 + 作者名（最宽松，覆盖中文论文等） ──
            # 用于捕获无DOI、无英文期刊名的论文（如中文论文、手稿格式）
            if not is_article_start:
                if _has_abstract_keywords(lines, scan_lines=15):
                    top_author_text = "\n".join(lines[:AFFILIATION_SCAN_LINES])
                    has_en_author = bool(AUTHOR_NAME_PATTERN.search(top_author_text))
                    has_cn_author = bool(CHINESE_AUTHOR_PATTERN.search(top_author_text))
                    has_cn_academic = bool(CHINESE_ACADEMIC_MARKERS.search(
                        "\n".join(lines[:ABSTRACT_SCAN_LINES])
                    ))
                    # 英文论文：Abstract + 英文作者名 + 机构
                    # 中文论文：摘要 + 中文作者名 或 中文学术标记
                    if has_en_author and any(
                        re.search(m, top_author_text, re.IGNORECASE)
                        for m in AFFILIATION_MARKERS
                    ):
                        is_article_start = True
                        marker_found = "Abstract+Author+Affil"
                    elif has_cn_author or has_cn_academic:
                        is_article_start = True
                        marker_found = "摘要+中文作者"

            if is_article_start:
                # 判断是否为强信号（有Abstract/Keywords）
                strong = _has_abstract_keywords(lines)

                title_hint = _extract_title_hint(lines)
                articles.append({
                    "page": i,
                    "title_hint": title_hint,
                    "marker": marker_found,
                    "strong": strong,
                })

                if verbose:
                    flag = " [强]" if strong else ""
                    print(f"   📄 第{i+1}页 [{marker_found}]{flag}: {title_hint[:55]}...")

    if verbose:
        print(f"\n✅ 共检测到 {len(articles)} 篇候选论文")

    return articles, total_pages


def filter_short_gaps(articles: list[dict], total_pages: int, verbose: bool = True) -> list[dict]:
    """
    合并间距过小（< MIN_ARTICLE_PAGES 页）的连续检测点。

    逻辑：
    - 间距 >= MIN_ARTICLE_PAGES 的检测点直接保留
    - 间距 < MIN_ARTICLE_PAGES 的连续检测点合并为一组，保留组内第一个
    - 例外：有 Abstract/Keywords 的强信号页面始终保留并开启新组
    """
    if len(articles) <= 1:
        return articles

    filtered = [articles[0]]
    removed_count = 0

    for idx in range(1, len(articles)):
        gap = articles[idx]["page"] - filtered[-1]["page"]
        is_strong = articles[idx].get("strong", False)

        if gap >= MIN_ARTICLE_PAGES or is_strong:
            # 间距足够 或 强信号 → 保留，开启新组
            filtered.append(articles[idx])
        else:
            # 间距过小且非强信号 → 并入上一组（丢弃）
            removed_count += 1
            if verbose:
                print(
                    f"   ⚠️  合并: 第{articles[idx]['page']+1}页 "
                    f"(距上一篇仅{gap}页，并入上一组)"
                )

    if removed_count and verbose:
        print(f"   已合并 {removed_count} 个间距过小的检测点")

    return filtered


def detect_duplicate_halves(articles: list[dict], total_pages: int) -> bool:
    """
    检测 PDF 前半部分和后半部分是否包含重复内容。

    通过比较前后两半的论文间距模式判断：
    如果 80% 以上的间距差 <= 1 页，则认为后半部分是重复内容。
    """
    if len(articles) < 4:
        return False

    mid_page = total_pages // 2

    # 按页面位置分成前半和后半
    first_half = [a for a in articles if a["page"] < mid_page]
    second_half = [a for a in articles if a["page"] >= mid_page]

    if len(first_half) < 2 or len(second_half) < 2:
        return False

    # 如果前后论文数量差距太大，不太可能是重复
    if abs(len(first_half) - len(second_half)) > max(len(first_half), len(second_half)) * 0.3:
        return False

    # 计算各自的间距序列
    gaps_first = [first_half[i+1]["page"] - first_half[i]["page"] for i in range(len(first_half) - 1)]
    gaps_second = [second_half[i+1]["page"] - second_half[i]["page"] for i in range(len(second_half) - 1)]

    # 比较间距序列：取较短的长度进行比较
    compare_len = min(len(gaps_first), len(gaps_second))
    if compare_len < 2:
        return False

    match_count = sum(
        1 for i in range(compare_len) if abs(gaps_first[i] - gaps_second[i]) <= 1
    )

    return match_count / compare_len >= 0.8


def split_pdf(pdf_path: str, articles: list[dict], output_dir: str = None):
    """
    根据检测到的论文起始页，将PDF切分为多个独立文件。
    """
    reader = PdfReader(pdf_path)
    total_pages = len(reader.pages)

    out = Path(output_dir) if output_dir else Path(pdf_path).with_name(Path(pdf_path).stem + "_split")
    out.mkdir(parents=True, exist_ok=True)

    print(f"\n✂️  开始切分，输出目录: {out}/")

    for idx, article in enumerate(articles):
        start_page = article["page"]

        # 结束页 = 下一篇论文的起始页 - 1，最后一篇到文档末尾
        if idx + 1 < len(articles):
            end_page = articles[idx + 1]["page"] - 1
        else:
            end_page = total_pages - 1

        # 生成文件名
        # 清理标题中的非法文件名字符（包括控制字符）
        safe_title = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '', article["title_hint"])
        safe_title = safe_title.strip().rstrip('.')[:60]  # 去除尾部点号，截断过长标题

        if safe_title:
            filename = f"{idx+1:02d}_{safe_title}.pdf"
        else:
            filename = f"{idx+1:02d}_article_page{start_page+1}-{end_page+1}.pdf"

        # 写入新PDF
        writer = PdfWriter()
        for page_num in range(start_page, end_page + 1):
            writer.add_page(reader.pages[page_num])

        output_path = out / filename
        with open(output_path, "wb") as f:
            writer.write(f)

        page_count = end_page - start_page + 1
        print(f"   ✅ [{idx+1:02d}] p.{start_page+1}-{end_page+1} ({page_count}页) → {filename}")

    print(f"\n🎉 完成！共切分 {len(articles)} 个文件 → {out}/")


def _print_article_list(articles: list[dict], total_pages: int):
    """打印当前论文检测列表及统计信息。"""
    print("\n" + "=" * 60)
    print("📋 检测结果预览（你可以手动修正）")
    print("=" * 60)

    page_counts = []
    for idx, a in enumerate(articles):
        start = a["page"] + 1
        if idx + 1 < len(articles):
            end = articles[idx + 1]["page"]
        else:
            end = total_pages
        pages = end - a["page"]
        page_counts.append(pages)
        print(f"  [{idx+1:02d}] p.{start:>3d}-{end:>3d} ({pages:>2d}页) | {a['title_hint'][:55]}")

    # 统计信息
    if page_counts:
        avg_pages = sum(page_counts) / len(page_counts)
        print(f"\n  共 {len(articles)} 篇 | 平均 {avg_pages:.1f} 页/篇 "
              f"| 最短 {min(page_counts)} 页 | 最长 {max(page_counts)} 页")

    print("\n" + "-" * 60)
    print("选项:")
    print("  回车  → 确认并开始切分")
    print("  a     → 手动添加一个起始页  (格式: a 页码)")
    print("  d     → 删除一个检测结果    (格式: d 序号)")
    print("  l     → 重新显示列表")
    print("  q     → 退出不切分")
    print("-" * 60)


def interactive_review(articles: list[dict], total_pages: int) -> list[dict]:
    """
    交互式确认：让用户检查并修正检测结果。
    """
    _print_article_list(articles, total_pages)

    while True:
        cmd = input("\n> ").strip().lower()

        if cmd == "" or cmd == "y":
            return articles
        elif cmd == "q":
            print("已取消。")
            sys.exit(0)
        elif cmd == "l":
            _print_article_list(articles, total_pages)
        elif cmd.startswith("a "):
            try:
                page = int(cmd.split()[1]) - 1  # 用户输入的是1-indexed
                if page < 0 or page >= total_pages:
                    print(f"  ⚠️  页码超出范围，有效范围: 1-{total_pages}")
                    continue
                articles.append({"page": page, "title_hint": "(手动添加)", "marker": "manual"})
                articles.sort(key=lambda x: x["page"])
                print(f"  ✅ 已添加第{page+1}页作为论文起始页")
                _print_article_list(articles, total_pages)
            except (ValueError, IndexError):
                print("  ⚠️  格式错误，请输入: a 页码（如 a 42）")
        elif cmd.startswith("d "):
            try:
                idx = int(cmd.split()[1]) - 1  # 用户输入的是1-indexed
                if idx < 0 or idx >= len(articles):
                    print(f"  ⚠️  序号超出范围，有效范围: 1-{len(articles)}")
                    continue
                removed = articles.pop(idx)
                print(f"  ✅ 已删除第{removed['page']+1}页的检测结果")
                _print_article_list(articles, total_pages)
            except (ValueError, IndexError):
                print("  ⚠️  格式错误，请输入: d 序号（如 d 3）")
        else:
            print("  ⚠️  未识别的命令")


# ============================================================
# 主程序
# ============================================================

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python split_pdf_articles.py <PDF文件路径> [输出目录]")
        print("示例: python split_pdf_articles.py 'Textbook-Language-and-cognition (1).pdf'")
        sys.exit(1)

    pdf_path = sys.argv[1]
    output_dir = sys.argv[2] if len(sys.argv) > 2 else None

    if not os.path.exists(pdf_path):
        print(f"❌ 文件不存在: {pdf_path}")
        sys.exit(1)

    # Step 1: 检测论文边界（三策略并行）
    articles, total_pages = detect_article_starts(pdf_path)

    if not articles:
        print("\n⚠️  未检测到论文边界！可能原因:")
        print("  1. PDF是扫描版（纯图片），无法提取文字 → 需要先OCR")
        print("  2. 论文格式不含预设的关键词标记 → 需修改脚本中的配置区")
        print("  3. PDF有加密/权限限制")
        sys.exit(1)

    # Step 2: 过滤间距过小的可疑误检（间距检查已在检测阶段内联，此处为双重保障）
    articles = filter_short_gaps(articles, total_pages)

    # Step 3: 检测前后重复内容
    if detect_duplicate_halves(articles, total_pages):
        mid_page = total_pages // 2
        first_half_articles = [a for a in articles if a["page"] < mid_page]
        print(f"\n⚠️  检测到 PDF 后半部分 (p.{mid_page+1}-{total_pages}) 可能是重复内容！")
        print(f"   前半部分: {len(first_half_articles)} 篇论文")
        print(f"   后半部分: {len(articles) - len(first_half_articles)} 篇论文")
        print(f"   间距模式高度相似，默认只处理前半部分。")
        answer = input("\n   按回车确认只处理前半部分，输入 'all' 处理全部: ").strip().lower()
        if answer != "all":
            articles = first_half_articles
            print(f"   ✅ 已移除后半部分，保留 {len(articles)} 篇论文")

    # Step 4: 交互式确认
    articles = interactive_review(articles, total_pages)

    # Step 5: 切分
    split_pdf(pdf_path, articles, output_dir)
