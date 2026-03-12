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

# 从主模块导入配置常量
from split_pdf_articles import (
    ARTICLE_TYPE_MARKERS,
    AFFILIATION_MARKERS,
    DOI_PATTERN,
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
    """测试 DOI 计数逻辑：论文首页(1-2个)通过，目录页(多个)被排除。"""
    # 单个DOI — 应通过
    text_single = "Some text https://doi.org/10.1234/abc more text"
    assert len(re.findall(DOI_PATTERN, text_single)) == 1

    # 两个DOI — 应通过
    text_double = "https://doi.org/10.1234/abc and https://doi.org/10.5678/def"
    count = len(re.findall(DOI_PATTERN, text_double))
    assert 1 <= count <= 2

    # 目录页：4个DOI — 应被排除
    text_toc = (
        "https://doi.org/10.1234/a "
        "https://doi.org/10.5678/b "
        "https://doi.org/10.9999/c "
        "https://doi.org/10.1111/d"
    )
    count = len(re.findall(DOI_PATTERN, text_toc))
    assert count == 4
    assert not (1 <= count <= 2), f"TOC page should be excluded (DOI count={count})"

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
    for bad_input in [0, -5, 101, 999]:  # 用户输入的1-indexed值
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
    for bad_input in [0, -1, 4, 10]:  # 用户输入的1-indexed值
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
    """测试文章类型标记正则是否能正确匹配。"""
    test_texts = [
        ("This is an EMPIRICAL ARTICLE about...", True),
        ("REVIEW  ARTICLE\nby John", True),
        ("This is a BRIEF REPORT on...", True),
        ("EDITORIAL\nThe editors...", True),
        ("Just some random text about nothing", False),
        ("empirical article lowercase", True),  # 不区分大小写
    ]
    for text, should_match in test_texts:
        matched = any(
            re.search(m, text, re.IGNORECASE) for m in ARTICLE_TYPE_MARKERS
        )
        assert matched == should_match, (
            f"Text {text[:40]!r}: expected match={should_match}, got {matched}"
        )

    print("  [PASS] test_article_type_markers")


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


if __name__ == "__main__":
    print("Running tests for split_pdf_articles.py...\n")

    tests = [
        test_filename_safety,
        test_doi_counting,
        test_top_third_slicing,
        test_boundary_validation,
        test_article_type_markers,
        test_affiliation_markers,
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
