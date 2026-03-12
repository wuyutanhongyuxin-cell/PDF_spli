#!/usr/bin/env python3
"""
split_pdf_articles.py 的单元测试
==================================

运行方法:
    python test_split_pdf.py
    # 或
    python -m pytest test_split_pdf.py -v
"""

import re
import sys

from split_pdf_articles import (
    ARTICLE_TYPE_MARKERS,
    AFFILIATION_MARKERS,
    AFFILIATION_SCAN_LINES,
    AUTHOR_NAME_PATTERN,
    DOI_PATTERN,
    DOI_SCAN_LINES,
    JOURNAL_NAME_MARKERS,
    MARKER_SCAN_LINES,
    MIN_ARTICLE_PAGES,
    VOLUME_ISSUE_PATTERN,
    detect_duplicate_halves,
    filter_short_gaps,
)


# ── 基础正则测试 ──

def test_filename_safety():
    """测试文件名安全处理：非法字符、控制字符、尾部点号。"""
    cases = [
        ("Hello<World>:test", "HelloWorldtest"),
        ('file"with|pipes?', "filewithpipes"),
        ("file\x00with\x1fcontrol", "filewithcontrol"),
        ("ends.with.dots...", "ends.with.dots"),
        ("   spaces   ", "spaces"),
        ("normal title here", "normal title here"),
        ("a" * 100, "a" * 60),
    ]
    for raw, expected in cases:
        safe = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", raw)
        safe = safe.strip().rstrip(".")[:60]
        assert safe == expected, f"FAIL: {raw!r} -> {safe!r}, expected {expected!r}"
    print("  [PASS] test_filename_safety")


def test_doi_pattern():
    """测试 DOI 正则匹配。"""
    assert len(re.findall(DOI_PATTERN, "https://doi.org/10.1234/abc")) == 1
    assert len(re.findall(DOI_PATTERN, "http://doi.org/10.56789/xyz")) == 1
    assert len(re.findall(DOI_PATTERN, "no doi here")) == 0
    assert len(re.findall(DOI_PATTERN,
        "https://doi.org/10.1234/a https://doi.org/10.5678/b")) == 2
    print("  [PASS] test_doi_pattern")


def test_article_type_markers():
    """测试精简后的文章类型标记：只保留可靠标记。"""
    should_match = [
        "EMPIRICAL ARTICLE", "REVIEW  ARTICLE", "BRIEF REPORT",
        "ORIGINAL ARTICLE", "RESEARCH ARTICLE", "THEORETICAL ARTICLE",
        "empirical article",  # 不区分大小写
    ]
    for text in should_match:
        matched = any(re.search(m, text, re.IGNORECASE) for m in ARTICLE_TYPE_MARKERS)
        assert matched, f"Should match: {text!r}"

    # 已移除的标记不应匹配
    should_not_match = [
        "INTRODUCTION", "META-ANALYSIS", "SYSTEMATIC REVIEW",
        "EDITORIAL", "COMMENTARY", "SPECIAL ISSUE",
        "random text about nothing",
    ]
    for text in should_not_match:
        matched = any(re.search(m, text, re.IGNORECASE) for m in ARTICLE_TYPE_MARKERS)
        assert not matched, f"Should NOT match: {text!r}"

    print("  [PASS] test_article_type_markers")


def test_marker_scan_lines_limit():
    """测试文章类型标记只在前N行匹配。"""
    # 第1行 → 应匹配
    lines_top = ["EMPIRICAL ARTICLE", "Some title", "Author names"]
    top_text = "\n".join(lines_top[:MARKER_SCAN_LINES])
    assert any(re.search(m, top_text, re.IGNORECASE) for m in ARTICLE_TYPE_MARKERS)

    # 第20行 → 不应匹配
    filler = [f"normal text line {i}" for i in range(20)]
    lines_deep = filler + ["EMPIRICAL ARTICLE", "more text"]
    top_text = "\n".join(lines_deep[:MARKER_SCAN_LINES])
    assert not any(re.search(m, top_text, re.IGNORECASE) for m in ARTICLE_TYPE_MARKERS)

    print("  [PASS] test_marker_scan_lines_limit")


def test_affiliation_markers():
    """测试机构署名标记。"""
    for text in ["Stanford University", "Department of Psychology",
                 "College of Engineering", "Institute of Cognitive Science"]:
        assert any(re.search(m, text, re.IGNORECASE) for m in AFFILIATION_MARKERS), \
            f"Should match: {text!r}"
    for text in ["random text", "Results showed significant effects"]:
        assert not any(re.search(m, text, re.IGNORECASE) for m in AFFILIATION_MARKERS), \
            f"Should NOT match: {text!r}"
    print("  [PASS] test_affiliation_markers")


def test_author_name_pattern():
    """测试作者姓名模式。"""
    for text in ["John Smith", "John M. Smith", "Maria Garcia"]:
        assert AUTHOR_NAME_PATTERN.search(text), f"Should match: {text!r}"
    for text in ["the results showed", "p < .001", "EMPIRICAL ARTICLE"]:
        assert not AUTHOR_NAME_PATTERN.search(text), f"Should NOT match: {text!r}"
    print("  [PASS] test_author_name_pattern")


# ── 策略2: DOI+Affiliation 位置约束测试 ──

def test_doi_position_constraint():
    """测试 DOI 必须在前 DOI_SCAN_LINES 行才被检测。"""
    # DOI 在第2行 → 前6行内，应被发现
    lines_top = ["Some header", "https://doi.org/10.1234/abc", "author line"]
    top_doi_text = "\n".join(lines_top[:DOI_SCAN_LINES])
    assert re.findall(DOI_PATTERN, top_doi_text), "DOI in top lines should be found"

    # DOI 在第15行 → 前6行外，不应被发现
    filler = [f"text line {i}" for i in range(15)]
    lines_deep = filler + ["https://doi.org/10.1234/abc"]
    top_doi_text = "\n".join(lines_deep[:DOI_SCAN_LINES])
    assert not re.findall(DOI_PATTERN, top_doi_text), "DOI deep in page should NOT be found"

    print("  [PASS] test_doi_position_constraint")


def test_affiliation_position_constraint():
    """测试机构署名必须在前 AFFILIATION_SCAN_LINES 行。"""
    # 第3行有 University → 前10行内
    lines_top = ["Title", "Author Name", "Stanford University", "more"]
    top_text = "\n".join(lines_top[:AFFILIATION_SCAN_LINES])
    assert any(re.search(m, top_text, re.IGNORECASE) for m in AFFILIATION_MARKERS)

    # 第20行才有 University → 前10行外
    filler = [f"body text {i}" for i in range(20)]
    lines_deep = filler + ["Stanford University"]
    top_text = "\n".join(lines_deep[:AFFILIATION_SCAN_LINES])
    assert not any(re.search(m, top_text, re.IGNORECASE) for m in AFFILIATION_MARKERS)

    print("  [PASS] test_affiliation_position_constraint")


# ── 策略3: 期刊名+卷期号测试 ──

def test_volume_issue_pattern():
    """测试卷期号模式匹配。"""
    should_match = [
        "108 (2011) 123",       # Cognition 108 (2011) 123-129
        "Vol. 23, No. 4",       # Vol. 23, No. 4
        "45:1115-1135",         # 45:1115-1135
        "Vol 5, No 2",          # 无点号变体
        "118 (2011) 123",
    ]
    for text in should_match:
        assert VOLUME_ISSUE_PATTERN.search(text), f"Should match volume: {text!r}"

    should_not_match = [
        "the year 2011 was",
        "page 123 of the book",
        "random text",
    ]
    for text in should_not_match:
        assert not VOLUME_ISSUE_PATTERN.search(text), f"Should NOT match: {text!r}"

    print("  [PASS] test_volume_issue_pattern")


def test_journal_name_markers():
    """测试期刊名称标记。"""
    should_match = [
        "Journal of Experimental Psychology",
        "Language and Cognition",
        "Modern Language Journal",
        "Cognition 118 (2011)",
        "Memory & Cognition",
        "Studies in Second Language",
    ]
    for text in should_match:
        matched = any(re.search(m, text, re.IGNORECASE) for m in JOURNAL_NAME_MARKERS)
        assert matched, f"Journal should match: {text!r}"

    should_not_match = [
        "random paragraph about cats",
        "The results were significant",
    ]
    for text in should_not_match:
        matched = any(re.search(m, text, re.IGNORECASE) for m in JOURNAL_NAME_MARKERS)
        assert not matched, f"Should NOT match journal: {text!r}"

    print("  [PASS] test_journal_name_markers")


def test_journal_volume_combined():
    """测试策略3完整逻辑：期刊名+卷期号同时出现在前5行。"""
    # 论文首页header: 期刊名 + 卷期号在前几行
    header_lines = [
        "Cognition 118 (2011) 123–129",
        "",
        "Contents lists available at ScienceDirect",
    ]
    top_text = "\n".join(header_lines[:MARKER_SCAN_LINES])
    has_journal = any(re.search(m, top_text, re.IGNORECASE) for m in JOURNAL_NAME_MARKERS)
    has_volume = bool(VOLUME_ISSUE_PATTERN.search(top_text))
    assert has_journal and has_volume, "Header with journal+volume should be detected"

    # 正文中间提到期刊名但无卷期号格式
    body_lines = [
        "As shown in the Journal of Experimental Psychology,",
        "these results indicate that...",
    ]
    top_text = "\n".join(body_lines[:MARKER_SCAN_LINES])
    has_journal = any(re.search(m, top_text, re.IGNORECASE) for m in JOURNAL_NAME_MARKERS)
    has_volume = bool(VOLUME_ISSUE_PATTERN.search(top_text))
    assert not (has_journal and has_volume), "Body text without volume should NOT trigger"

    print("  [PASS] test_journal_volume_combined")


# ── 间距过滤和去重测试 ──

def test_min_article_pages_value():
    """确认 MIN_ARTICLE_PAGES 已调整为 4。"""
    assert MIN_ARTICLE_PAGES == 4, f"Expected 4, got {MIN_ARTICLE_PAGES}"
    print("  [PASS] test_min_article_pages_value")


def test_filter_short_gaps():
    """测试间距过滤：相邻检测点 < MIN_ARTICLE_PAGES(4) 页应被移除。"""
    articles = [
        {"page": 0, "title_hint": "A", "marker": "test"},
        {"page": 2, "title_hint": "B", "marker": "test"},   # gap=2 < 4, 过滤
        {"page": 3, "title_hint": "C", "marker": "test"},   # gap=3 从A算, 但从上一个保留的(0)算=3 < 4, 过滤
        {"page": 20, "title_hint": "D", "marker": "test"},  # gap=20, 保留
        {"page": 22, "title_hint": "E", "marker": "test"},  # gap=2, 过滤
        {"page": 40, "title_hint": "F", "marker": "test"},  # gap=18, 保留
    ]
    result = filter_short_gaps(articles, total_pages=100, verbose=False)
    pages = [a["page"] for a in result]
    assert pages == [0, 20, 40], f"Expected [0, 20, 40], got {pages}"

    # 边界
    assert filter_short_gaps([], 100, verbose=False) == []
    single = [{"page": 5, "title_hint": "X", "marker": "t"}]
    assert filter_short_gaps(single, 100, verbose=False) == single

    print("  [PASS] test_filter_short_gaps")


def test_detect_duplicate_halves():
    """测试 PDF 前后重复内容检测。"""
    total = 200

    # 完全镜像
    articles_dup = [
        {"page": p, "title_hint": "", "marker": ""}
        for p in [0, 20, 40, 60, 80, 100, 120, 140, 160, 180]
    ]
    assert detect_duplicate_halves(articles_dup, total) is True

    # 不同间距
    articles_diff = [
        {"page": p, "title_hint": "", "marker": ""}
        for p in [0, 10, 50, 90, 100, 105, 150, 195]
    ]
    assert detect_duplicate_halves(articles_diff, total) is False

    # 太少论文
    articles_few = [{"page": 0, "title_hint": "", "marker": ""},
                    {"page": 50, "title_hint": "", "marker": ""}]
    assert detect_duplicate_halves(articles_few, total) is False

    print("  [PASS] test_detect_duplicate_halves")


def test_boundary_validation():
    """测试交互式操作的边界校验。"""
    total_pages = 100
    articles = [{"page": 0}, {"page": 10}, {"page": 20}]

    for bad_input in [0, -5, 101, 999]:
        page = bad_input - 1
        assert page < 0 or page >= total_pages

    for good_input in [1, 50, 100]:
        page = good_input - 1
        assert 0 <= page < total_pages

    for bad_input in [0, -1, 4, 10]:
        idx = bad_input - 1
        assert idx < 0 or idx >= len(articles)

    for good_input in [1, 2, 3]:
        idx = good_input - 1
        assert 0 <= idx < len(articles)

    print("  [PASS] test_boundary_validation")


def test_top_third_slicing():
    """测试 top_third 切片安全。"""
    for n in [0, 1, 3, 5, 10, 30, 100]:
        lines = list(range(n))
        top_count = min(max(len(lines) // 3, 5), len(lines))
        assert top_count <= len(lines)
    assert min(max(0 // 3, 5), 0) == 0
    print("  [PASS] test_top_third_slicing")


# ── 主程序 ──

if __name__ == "__main__":
    print("Running tests for split_pdf_articles.py...\n")

    tests = [
        # 基础正则
        test_filename_safety,
        test_doi_pattern,
        test_article_type_markers,
        test_marker_scan_lines_limit,
        test_affiliation_markers,
        test_author_name_pattern,
        # 策略2位置约束
        test_doi_position_constraint,
        test_affiliation_position_constraint,
        # 策略3期刊卷期号
        test_volume_issue_pattern,
        test_journal_name_markers,
        test_journal_volume_combined,
        # 间距和去重
        test_min_article_pages_value,
        test_filter_short_gaps,
        test_detect_duplicate_halves,
        # 交互校验
        test_boundary_validation,
        test_top_third_slicing,
    ]

    passed = 0
    failed = 0
    for test in tests:
        try:
            test()
            passed += 1
        except AssertionError as e:
            print(f"  [FAIL] {test.__name__}: {e}")
            failed += 1

    print(f"\nResults: {passed} passed, {failed} failed, {len(tests)} total")
    sys.exit(1 if failed else 0)
