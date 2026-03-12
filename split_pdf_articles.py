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
# 当一页的文本中包含以下任意一个模式时，视为一篇新论文的起始
ARTICLE_TYPE_MARKERS = [
    r"EMPIRICAL\s+ARTICLE",
    r"REVIEW\s+ARTICLE",
    r"THEORETICAL\s+ARTICLE",
    r"BRIEF\s+REPORT",
    r"EDITORIAL",
    r"COMMENTARY",
    r"ORIGINAL\s+ARTICLE",
    r"RESEARCH\s+ARTICLE",
    r"META-ANALYSIS",
    r"SYSTEMATIC\s+REVIEW",
    r"SPECIAL\s+ISSUE",
    r"INTRODUCTION",            # 有些合集的导言也是独立文章
]

# DOI模式 — 论文首页通常会有DOI
DOI_PATTERN = r"https?://doi\.org/10\.\d{4,}"

# 额外的启发式规则：如果一页同时满足以下条件，也视为论文起始页
# 1. 包含DOI链接
# 2. 包含作者署名行（通常有"University"或"Department"等）
AFFILIATION_MARKERS = [
    r"University",
    r"Department\s+of",
    r"College\s+of",
    r"Institute\s+of",
    r"School\s+of",
]


def detect_article_starts(pdf_path: str, verbose: bool = True) -> tuple[list[dict], int]:
    """
    扫描PDF每一页，检测论文起始页。

    返回: ([{"page": 0-indexed页码, "title_hint": 识别到的标题线索}, ...], 总页数)
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
            
            # 跳过空白页或极短页（如封面、目录页可能文字很少）
            if len(text.strip()) < 50:
                continue
            
            is_article_start = False
            marker_found = ""
            
            # 检测方式1: 文章类型标记（最可靠）
            for marker in ARTICLE_TYPE_MARKERS:
                if re.search(marker, text, re.IGNORECASE):
                    is_article_start = True
                    marker_found = marker
                    break
            
            # 检测方式2: DOI + 机构署名（次可靠）
            if not is_article_start:
                doi_matches = re.findall(DOI_PATTERN, text)
                has_affiliation = any(
                    re.search(m, text, re.IGNORECASE) for m in AFFILIATION_MARKERS
                )
                # 论文首页通常只有1-2个DOI；目录页/参考文献页往往有多个
                if 1 <= len(doi_matches) <= 2 and has_affiliation:
                    lines = text.split("\n")
                    top_count = min(max(len(lines) // 3, 5), len(lines))
                    top_third = "\n".join(lines[:top_count])
                    # 排除目录页（目录页通常有大量页码如 "... 123"）
                    page_number_count = len(re.findall(r"\.\s*\d{1,3}\s*$", top_third, re.MULTILINE))
                    if page_number_count < 3:
                        is_article_start = True
                        marker_found = "DOI+Affiliation"
            
            if is_article_start:
                # 尝试提取标题（通常是页面顶部区域最长的非空行之一）
                lines = [l.strip() for l in text.split("\n") if l.strip()]
                title_hint = ""
                for line in lines[:15]:  # 在前15行中找标题
                    # 跳过期刊名、版权声明等
                    if any(skip in line.lower() for skip in [
                        "journal of", "©", "copyright", "issn", "vol.", 
                        "association", "doi.org", "sarmac"
                    ]):
                        continue
                    # 跳过文章类型标记本身
                    if any(re.search(m, line, re.IGNORECASE) for m in ARTICLE_TYPE_MARKERS):
                        continue
                    # 标题通常是较长的行
                    if len(line) > 20:
                        title_hint = line
                        break
                
                articles.append({
                    "page": i,
                    "title_hint": title_hint[:80],
                    "marker": marker_found,
                })
                
                if verbose:
                    print(f"   📄 第{i+1}页 [{marker_found}]: {title_hint[:60]}...")
    
    if verbose:
        print(f"\n✅ 共检测到 {len(articles)} 篇论文")

    return articles, total_pages


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
    """打印当前论文检测列表。"""
    print("\n" + "=" * 60)
    print("📋 检测结果预览（你可以手动修正）")
    print("=" * 60)

    for idx, a in enumerate(articles):
        start = a["page"] + 1
        if idx + 1 < len(articles):
            end = articles[idx + 1]["page"]
        else:
            end = total_pages
        pages = end - a["page"]
        print(f"  [{idx+1:02d}] p.{start:>3d}-{end:>3d} ({pages:>2d}页) | {a['title_hint'][:55]}")

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
    
    # Step 1: 检测论文边界
    articles, total_pages = detect_article_starts(pdf_path)

    if not articles:
        print("\n⚠️  未检测到论文边界！可能原因:")
        print("  1. PDF是扫描版（纯图片），无法提取文字 → 需要先OCR")
        print("  2. 论文格式不含预设的关键词标记 → 需修改脚本中的ARTICLE_TYPE_MARKERS")
        print("  3. PDF有加密/权限限制")
        sys.exit(1)

    # Step 2: 交互式确认
    articles = interactive_review(articles, total_pages)
    
    # Step 3: 切分
    split_pdf(pdf_path, articles, output_dir)
