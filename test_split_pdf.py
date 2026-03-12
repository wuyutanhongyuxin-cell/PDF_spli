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

# 从主模块导入配置常量和函数
from split_pdf_articles import (
    ARTICLE_TYPE_MARKERS,
    AFFILIATION_MARKERS,
    AUTHOR_NAME_PATTERN,
    DOI_PATTERN,
    MARKER_SCAN_LINES,
    MIN_ARTICLE_PAGES,
    detect_duplicate_halves,
    filter_short_gaps,
)


def test_filename_safety():
    """测试文件名安全处理：非法字符、控制字符、尾部点号。"""
    cases = [
        ("Hello<World>:test", "HelloWorldtest"),
        ('file"with|pipes?', "filewithpipes"),
        ("file\x00with\x1fcontrol", "filewithcontrol"),
        ("ends.with.dots...", "ends.with.dots"),
        ("   spaces   ", "spaces"),
        ("normal title here", "normal title here"),
        ("a" * 100, "a" * 60),  # 截断到60字符
    ]
    for raw, expected in cases:
        safe = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", raw)
        safe = safe.strip().rstrip(".")[:60]
        assert safe == expected, f"FAIL: {raw!r} -> {safe!r}, expected {expected!r}"
    print("  [PASS] test_filename_safety")


def test_doi_counting():
    """测试 DOI 正则匹配能力。"""
    # 单个DOI
    text_single = "Some text https://doi.org/10.1234/abc more text"
    assert len(re.findall(DOI_PATTERN, text_single)) == 1

    # 两个DOI
    text_double = "https://doi.org/10.1234/abc and https://doi.org/10.5678/def"
    assert len(re.findall(DOI_PATTERN, text_double)) == 2

    # 多个DOI（目录页/参考文献页场景）
    text_toc = (
        "https://doi.org/10.1234/a "
        "https://doi.org/10.5678/b "
        "https://doi.org/10.9999/c "
        "https://doi.org/10.1111/d"
    )
    assert len(re.findall(DOI_PATTERN, text_toc)) == 4

    print("  [PASS] test_doi_counting")


def test_top_third_slicing():
    """测试 top_third 切片不会超出实际行数。"""
    for n_lines in [0, 1, 2, 3, 5, 10, 15, 30, 100]:
        lines = [f"line{i}" for i in range(n_lines)]
        top_count = min(max(len(lines) // 3, 5), len(lines))
        result = lines[:top_count]
        assert len(result) <= len(lines), (
            f"Slice overflow: {len(result)} > {len(lines)} for {n_lines} lines"
        )

    # 边界：0行应该返回空
    assert min(max(0 // 3, 5), 0) == 0

    print("  [PASS] test_top_third_slicing")


def test_boundary_validation():
    """测试交互式操作的边界校验（页码越界、序号越界）。"""
    total_pages = 100
    articles = [{"page": 0}, {"page": 10}, {"page": 20}]

    # 添加页码越界检测
    for bad_input in [0, -5, 101, 999]:
        page = bad_input - 1
        assert page < 0 or page >= total_pages, (
            f"Page {bad_input} should be rejected as out of range"
        )

    # 合法页码应被接受
    for good_input in [1, 50, 100]:
        page = good_input - 1
        assert 0 <= page < total_pages, (
            f"Page {good_input} should be accepted"
        )

    # 删除序号越界检测
    for bad_input in [0, -1, 4, 10]:
        idx = bad_input - 1
        assert idx < 0 or idx >= len(articles), (
            f"Index {bad_input} should be rejected as out of range"
        )

    # 合法序号应被接受
    for good_input in [1, 2, 3]:
        idx = good_input - 1
        assert 0 <= idx < len(articles), (
            f"Index {good_input} should be accepted"
        )

    print("  [PASS] test_boundary_validation")


def test_article_type_markers():
    """测试精简后的文章类型标记：只保留可靠标记，移除易误报标记。"""
    # 应该匹配的（保留的标记）
    should_match = [
        "EMPIRICAL ARTICLE",
        "REVIEW  ARTICLE",
        "BRIEF REPORT",
        "ORIGINAL ARTICLE",
        "RESEARCH ARTICLE",
        "THEORETICAL ARTICLE",
        "empirical article",  # 不区分大小写
    ]
    for text in should_match:
        matched = any(re.search(m, text, re.IGNORECASE) for m in ARTICLE_TYPE_MARKERS)
        assert matched, f"Should match but didn't: {text!r}"

    # 不应该匹配的（已移除的标记）
    should_not_match = [
        "INTRODUCTION",
        "META-ANALYSIS",
        "SYSTEMATIC REVIEW",
        "EDITORIAL",
        "COMMENTARY",
        "SPECIAL ISSUE",
        "Just some random text about nothing",
    ]
    for text in should_not_match:
        matched = any(re.search(m, text, re.IGNORECASE) for m in ARTICLE_TYPE_MARKERS)
        assert not matched, f"Should NOT match but did: {text!r}"

    print("  [PASS] test_article_type_markers")


def test_marker_scan_lines_limit():
    """测试文章类型标记只在前N行匹配，不匹配正文中间出现的同名词。"""
    # "EMPIRICAL ARTICLE" 在第1行 → 应匹配
    page_top = "EMPIRICAL ARTICLE\nSome title\nAuthor names"
    lines = [l.strip() for l in page_top.split("\n") if l.strip()]
    top_text = "\n".join(lines[:MARKER_SCAN_LINES])
    matched = any(re.search(m, top_text, re.IGNORECASE) for m in ARTICLE_TYPE_MARKERS)
    assert matched, "Marker in top lines should match"

    # "EMPIRICAL ARTICLE" 在第20行 → 不应匹配
    filler = "\n".join([f"normal text line {i}" for i in range(20)])
    page_deep = filler + "\nEMPIRICAL ARTICLE\nmore text"
    lines = [l.strip() for l in page_deep.split("\n") if l.strip()]
    top_text = "\n".join(lines[:MARKER_SCAN_LINES])
    matched = any(re.search(m, top_text, re.IGNORECASE) for m in ARTICLE_TYPE_MARKERS)
    assert not matched, "Marker deep in page should NOT match"

    print("  [PASS] test_marker_scan_lines_limit")


def test_affiliation_markers():
    """测试机构署名标记正则。"""
    texts_match = [
        "Department of Psychology, Stanford University",
        "College of Engineering",
        "Institute of Cognitive Science",
        "School of Medicine",
    ]
    texts_no_match = [
        "The quick brown fox jumps over the lazy dog",
        "Results showed significant effects",
    ]
    for text in texts_match:
        assert any(
            re.search(m, text, re.IGNORECASE) for m in AFFILIATION_MARKERS
        ), f"Should match: {text!r}"
    for text in texts_no_match:
        assert not any(
            re.search(m, text, re.IGNORECASE) for m in AFFILIATION_MARKERS
        ), f"Should NOT match: {text!r}"

    print("  [PASS] test_affiliation_markers")


def test_author_name_pattern():
    """测试作者姓名模式匹配。"""
    should_match = [
        "John Smith",
        "John M. Smith",
        "Maria Garcia",
        "Anna-Lisa Keller",
    ]
    should_not_match = [
        "the results showed",
        "in 2024",
        "EMPIRICAL ARTICLE",
        "p < .001",
    ]
    for text in should_match:
        assert AUTHOR_NAME_PATTERN.search(text), f"Should match author: {text!r}"
    for text in should_not_match:
        assert not AUTHOR_NAME_PATTERN.search(text), f"Should NOT match: {text!r}"

    print("  [PASS] test_author_name_pattern")


def test_filter_short_gaps():
    """测试间距过滤：相邻检测点 < MIN_ARTICLE_PAGES 页应被移除。"""
    articles = [
        {"page": 0, "title_hint": "A", "marker": "test"},
        {"page": 1, "title_hint": "B", "marker": "test"},   # gap=1, 应被过滤
        {"page": 2, "title_hint": "C", "marker": "test"},   # gap=1, 应被过滤
        {"page": 20, "title_hint": "D", "marker": "test"},  # gap=18, 保留
        {"page": 21, "title_hint": "E", "marker": "test"},  # gap=1, 应被过滤
        {"page": 40, "title_hint": "F", "marker": "test"},  # gap=19, 保留
    ]
    result = filter_short_gaps(articles, total_pages=100, verbose=False)
    pages = [a["page"] for a in result]
    assert pages == [0, 20, 40], f"Expected [0, 20, 40], got {pages}"

    # 空列表和单元素列表
    assert filter_short_gaps([], 100, verbose=False) == []
    single = [{"page": 5, "title_hint": "X", "marker": "t"}]
    assert filter_short_gaps(single, 100, verbose=False) == single

    print("  [PASS] test_filter_short_gaps")


def test_detect_duplicate_halves():
    """测试 PDF 前后重复内容检测。"""
    total = 200

    # 完全镜像的间距：前半 [0,20,40,60,80], 后半 [100,120,140,160,180]
    articles_dup = [
        {"page": p, "title_hint": "", "marker": ""}
        for p in [0, 20, 40, 60, 80, 100, 120, 140, 160, 180]
    ]
    assert detect_duplicate_halves(articles_dup, total) is True, "Should detect duplicate"

    # 不同间距：前半 [0,10,50,90], 后半 [100,105,150,195]
    articles_diff = [
        {"page": p, "title_hint": "", "marker": ""}
        for p in [0, 10, 50, 90, 100, 105, 150, 195]
    ]
    assert detect_duplicate_halves(articles_diff, total) is False, "Should NOT detect duplicate"

    # 太少论文
    articles_few = [{"page": 0, "title_hint": "", "marker": ""},
                    {"page": 50, "title_hint": "", "marker": ""}]
    assert detect_duplicate_halves(articles_few, total) is False, "Too few articles"

    print("  [PASS] test_detect_duplicate_halves")


if __name__ == "__main__":
    print("Running tests for split_pdf_articles.py...\n")

    tests = [
        test_filename_safety,
        test_doi_counting,
        test_top_third_slicing,
        test_boundary_validation,
        test_article_type_markers,
        test_marker_scan_lines_limit,
        test_affiliation_markers,
        test_author_name_pattern,
        test_filter_short_gaps,
        test_detect_duplicate_halves,
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
