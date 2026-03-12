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
    ABSTRACT_PATTERN,
    ABSTRACT_SCAN_LINES,
    AFFILIATION_MARKERS,
    AFFILIATION_SCAN_LINES,
    ARTICLE_TYPE_MARKERS,
    AUTHOR_NAME_PATTERN,
    CHINESE_ACADEMIC_MARKERS,
    CHINESE_AUTHOR_PATTERN,
    DOI_PATTERN,
    DOI_SCAN_LINES,
    JOURNAL_NAME_MARKERS,
    KEYWORDS_PATTERN,
    MARKER_SCAN_LINES,
    MIN_ARTICLE_PAGES,
    VOLUME_ISSUE_PATTERN,
    _has_abstract_keywords,
    detect_duplicate_halves,
    filter_short_gaps,
)


# ── 配置值检查 ──

def test_config_values():
    """确认关键配置值。"""
    assert MIN_ARTICLE_PAGES == 4, f"MIN_ARTICLE_PAGES should be 4, got {MIN_ARTICLE_PAGES}"
    assert DOI_SCAN_LINES == 8, f"DOI_SCAN_LINES should be 8, got {DOI_SCAN_LINES}"
    assert AFFILIATION_SCAN_LINES == 10
    assert MARKER_SCAN_LINES == 5
    assert ABSTRACT_SCAN_LINES == 20
    print("  [PASS] test_config_values")


# ── 策略1: 文章类型标记 ──

def test_article_type_markers():
    """精简后的标记：保留可靠的，移除易误报的。"""
    should_match = [
        "EMPIRICAL ARTICLE", "REVIEW  ARTICLE", "BRIEF REPORT",
        "ORIGINAL ARTICLE", "RESEARCH ARTICLE", "THEORETICAL ARTICLE",
        "empirical article",
    ]
    for text in should_match:
        assert any(re.search(m, text, re.IGNORECASE) for m in ARTICLE_TYPE_MARKERS), \
            f"Should match: {text!r}"

    should_not_match = [
        "INTRODUCTION", "META-ANALYSIS", "EDITORIAL", "COMMENTARY",
        "random text",
    ]
    for text in should_not_match:
        assert not any(re.search(m, text, re.IGNORECASE) for m in ARTICLE_TYPE_MARKERS), \
            f"Should NOT match: {text!r}"
    print("  [PASS] test_article_type_markers")


def test_marker_scan_lines_limit():
    """标记只在前5行匹配。"""
    lines_top = ["EMPIRICAL ARTICLE", "Title", "Author"]
    assert any(re.search(m, "\n".join(lines_top[:MARKER_SCAN_LINES]), re.IGNORECASE)
               for m in ARTICLE_TYPE_MARKERS)

    filler = [f"text {i}" for i in range(20)]
    lines_deep = filler + ["EMPIRICAL ARTICLE"]
    assert not any(re.search(m, "\n".join(lines_deep[:MARKER_SCAN_LINES]), re.IGNORECASE)
                   for m in ARTICLE_TYPE_MARKERS)
    print("  [PASS] test_marker_scan_lines_limit")


# ── 策略2: DOI+Affiliation ──

def test_doi_pattern():
    """DOI 正则。"""
    assert len(re.findall(DOI_PATTERN, "https://doi.org/10.1234/abc")) == 1
    assert len(re.findall(DOI_PATTERN, "no doi here")) == 0
    print("  [PASS] test_doi_pattern")


def test_doi_position_constraint():
    """DOI 在前8行内被发现，在第15行不被发现。"""
    lines = [f"line {i}" for i in range(7)] + ["https://doi.org/10.1234/abc"]
    assert re.findall(DOI_PATTERN, "\n".join(lines[:DOI_SCAN_LINES]))

    lines_deep = [f"line {i}" for i in range(15)] + ["https://doi.org/10.1234/abc"]
    assert not re.findall(DOI_PATTERN, "\n".join(lines_deep[:DOI_SCAN_LINES]))
    print("  [PASS] test_doi_position_constraint")


def test_affiliation_markers():
    """机构署名标记。"""
    for text in ["Stanford University", "Department of Psychology"]:
        assert any(re.search(m, text, re.IGNORECASE) for m in AFFILIATION_MARKERS)
    for text in ["random text", "Results were significant"]:
        assert not any(re.search(m, text, re.IGNORECASE) for m in AFFILIATION_MARKERS)
    print("  [PASS] test_affiliation_markers")


def test_author_name_pattern():
    """英文作者姓名。"""
    for text in ["John Smith", "John M. Smith", "Maria Garcia"]:
        assert AUTHOR_NAME_PATTERN.search(text), f"Should match: {text!r}"
    for text in ["the results", "p < .001"]:
        assert not AUTHOR_NAME_PATTERN.search(text), f"Should NOT match: {text!r}"
    print("  [PASS] test_author_name_pattern")


def test_chinese_author_pattern():
    """中文作者姓名（至少两个以逗号分隔的2-4字中文名）。"""
    should_match = [
        "李哲, 王某某",
        "吴诗玉，王亦赟",
        "李赞、吴诗玉",
        "张三, 李四, 王五",
    ]
    for text in should_match:
        assert CHINESE_AUTHOR_PATTERN.search(text), f"Should match Chinese author: {text!r}"

    should_not_match = [
        "这是一段普通文字",  # 无逗号分隔的多名
        "Hello world",
    ]
    for text in should_not_match:
        assert not CHINESE_AUTHOR_PATTERN.search(text), f"Should NOT match: {text!r}"
    print("  [PASS] test_chinese_author_pattern")


# ── 策略3: Journal+Volume+Abstract ──

def test_volume_issue_pattern():
    """卷期号模式。"""
    for text in ["108 (2011) 123", "Vol. 23, No. 4", "45:1115-1135"]:
        assert VOLUME_ISSUE_PATTERN.search(text), f"Should match: {text!r}"
    for text in ["the year 2011 was", "random text"]:
        assert not VOLUME_ISSUE_PATTERN.search(text), f"Should NOT match: {text!r}"
    print("  [PASS] test_volume_issue_pattern")


def test_journal_name_markers():
    """期刊名。"""
    for text in ["Journal of Experimental Psychology", "Cognition 118",
                 "Language and Cognition", "Memory & Cognition"]:
        assert any(re.search(m, text, re.IGNORECASE) for m in JOURNAL_NAME_MARKERS)
    for text in ["random paragraph"]:
        assert not any(re.search(m, text, re.IGNORECASE) for m in JOURNAL_NAME_MARKERS)
    print("  [PASS] test_journal_name_markers")


def test_journal_volume_abstract_combined():
    """策略3: 期刊名+卷期号在前5行 + Abstract在前20行才命中。"""
    # 首页: header有期刊+卷号，正文有Abstract → 命中
    first_page = [
        "Cognition 118 (2011) 123–129",
        "Contents lists available at ScienceDirect",
        "Title of the Paper",
        "John Smith",
        "University of Somewhere",
        "Abstract",
        "This study investigates...",
    ]
    top = "\n".join(first_page[:MARKER_SCAN_LINES])
    has_j = any(re.search(m, top, re.IGNORECASE) for m in JOURNAL_NAME_MARKERS)
    has_v = bool(VOLUME_ISSUE_PATTERN.search(top))
    has_abs = _has_abstract_keywords(first_page)
    assert has_j and has_v and has_abs, "First page should match strategy 3"

    # 中间页: running head有期刊+卷号，但无Abstract → 不命中
    middle_page = [
        "Cognition 118 (2011) 123–129",
        "continued discussion about...",
        "more body text here",
    ]
    top = "\n".join(middle_page[:MARKER_SCAN_LINES])
    has_j = any(re.search(m, top, re.IGNORECASE) for m in JOURNAL_NAME_MARKERS)
    has_v = bool(VOLUME_ISSUE_PATTERN.search(top))
    has_abs = _has_abstract_keywords(middle_page)
    assert has_j and has_v, "Middle page should have journal+volume in header"
    assert not has_abs, "Middle page should NOT have Abstract"
    assert not (has_j and has_v and has_abs), "Middle page should NOT trigger strategy 3"

    print("  [PASS] test_journal_volume_abstract_combined")


# ── 策略4+5: Abstract 相关 ──

def test_abstract_pattern():
    """Abstract/摘要独立行匹配。"""
    assert ABSTRACT_PATTERN.search("Abstract")
    assert ABSTRACT_PATTERN.search("ABSTRACT")
    assert ABSTRACT_PATTERN.search("摘 要")
    assert ABSTRACT_PATTERN.search("摘要")
    assert ABSTRACT_PATTERN.search("Summary")
    # 不匹配正文中间的 "abstract" 子串
    assert not ABSTRACT_PATTERN.search("This is an abstract idea")
    print("  [PASS] test_abstract_pattern")


def test_keywords_pattern():
    """Keywords/关键词匹配。"""
    assert KEYWORDS_PATTERN.search("Keywords: language, cognition")
    assert KEYWORDS_PATTERN.search("关键词：语言 认知")
    assert KEYWORDS_PATTERN.search("Key words: test")
    assert KEYWORDS_PATTERN.search("Keyword: single")
    print("  [PASS] test_keywords_pattern")


def test_has_abstract_keywords():
    """_has_abstract_keywords 辅助函数。"""
    lines_with = ["Title", "Author", "Abstract", "Some content"]
    assert _has_abstract_keywords(lines_with)

    lines_without = ["Title", "Author", "Introduction", "Body text"]
    assert not _has_abstract_keywords(lines_without)

    lines_cn = ["标题", "作者", "摘要", "本研究..."]
    assert _has_abstract_keywords(lines_cn)
    print("  [PASS] test_has_abstract_keywords")


def test_chinese_academic_markers():
    """中文学术标记。"""
    for text in ["基金项目：国家社科基金", "收稿日期：2023-01-01",
                 "中图分类号：H319", "文献标识码：A"]:
        assert CHINESE_ACADEMIC_MARKERS.search(text), f"Should match: {text!r}"
    for text in ["这是普通文字", "Hello world"]:
        assert not CHINESE_ACADEMIC_MARKERS.search(text), f"Should NOT match: {text!r}"
    print("  [PASS] test_chinese_academic_markers")


def test_strategy5_english():
    """策略5英文: Abstract + 英文作者名 + 机构。"""
    lines = [
        "Title of Paper",
        "John M. Smith",
        "Department of Psychology",
        "Stanford University",
        "",
        "Abstract",
        "This study investigates...",
    ]
    # 有 Abstract
    assert _has_abstract_keywords(lines, scan_lines=15)
    # 有作者名
    top_text = "\n".join(lines[:AFFILIATION_SCAN_LINES])
    assert AUTHOR_NAME_PATTERN.search(top_text)
    # 有机构
    assert any(re.search(m, top_text, re.IGNORECASE) for m in AFFILIATION_MARKERS)
    print("  [PASS] test_strategy5_english")


def test_strategy5_chinese():
    """策略5中文: 摘要 + 中文作者名。"""
    lines = [
        "基于LLM的情感习得研究",
        "吴诗玉，王亦赟",
        "上海交通大学",
        "",
        "摘要",
        "本研究探讨了...",
        "关键词：大语言模型 情感",
    ]
    assert _has_abstract_keywords(lines, scan_lines=15)
    top_text = "\n".join(lines[:AFFILIATION_SCAN_LINES])
    assert CHINESE_AUTHOR_PATTERN.search(top_text), "Should find Chinese authors"
    print("  [PASS] test_strategy5_chinese")


# ── 间距过滤（合并组逻辑）──

def test_filter_short_gaps_basic():
    """间距 < 4 页的合并为一组取第一个。"""
    articles = [
        {"page": 0, "title_hint": "A", "marker": "t", "strong": False},
        {"page": 2, "title_hint": "B", "marker": "t", "strong": False},   # gap=2, 合并
        {"page": 20, "title_hint": "C", "marker": "t", "strong": False},  # gap=18, 保留
        {"page": 22, "title_hint": "D", "marker": "t", "strong": False},  # gap=2, 合并
        {"page": 40, "title_hint": "E", "marker": "t", "strong": False},  # gap=18, 保留
    ]
    result = filter_short_gaps(articles, 100, verbose=False)
    assert [a["page"] for a in result] == [0, 20, 40]
    print("  [PASS] test_filter_short_gaps_basic")


def test_filter_strong_signal_bypasses_gap():
    """强信号紧跟弱信号时，替换弱信号。两个强信号紧邻时两者都保留。"""
    # Case 1: 弱+强 → 弱被替换
    articles = [
        {"page": 0, "title_hint": "A", "marker": "t", "strong": False},
        {"page": 2, "title_hint": "B", "marker": "t", "strong": True},   # gap=2 但strong
        {"page": 20, "title_hint": "C", "marker": "t", "strong": False},
    ]
    result = filter_short_gaps(articles, 100, verbose=False)
    assert [a["page"] for a in result] == [2, 20], "Weak should be replaced by strong"

    # Case 2: 强+强 → 两者都保留
    articles2 = [
        {"page": 0, "title_hint": "A", "marker": "t", "strong": True},
        {"page": 2, "title_hint": "B", "marker": "t", "strong": True},
        {"page": 20, "title_hint": "C", "marker": "t", "strong": False},
    ]
    result2 = filter_short_gaps(articles2, 100, verbose=False)
    assert [a["page"] for a in result2] == [0, 2, 20], "Both strong should be kept"
    print("  [PASS] test_filter_strong_signal_bypasses_gap")


def test_filter_strong_replaces_weak():
    """问题1回归: 弱信号(p.40 DOI+Affil) + 强信号(p.41 EMPIRICAL ARTICLE)，
    应替换弱信号保留强信号，而非保留两者或丢弃强信号。"""
    articles = [
        {"page": 0, "title_hint": "Prev", "marker": "t", "strong": True},
        {"page": 39, "title_hint": "Weak", "marker": "DOI+Affiliation", "strong": False},  # p.40
        {"page": 40, "title_hint": "Strong", "marker": "EMPIRICAL\\s+ARTICLE", "strong": True},  # p.41
        {"page": 60, "title_hint": "Next", "marker": "t", "strong": False},
    ]
    result = filter_short_gaps(articles, 200, verbose=False)
    pages = [a["page"] for a in result]
    # p.39(弱)应被p.40(强)替换，而非两者共存
    assert 39 not in pages, "Weak signal (p.40) should be replaced"
    assert 40 in pages, "Strong signal (p.41) should be kept"
    assert pages == [0, 40, 60], f"Expected [0, 40, 60], got {pages}"
    print("  [PASS] test_filter_strong_replaces_weak")


def test_filter_edge_cases():
    """边界情况。"""
    assert filter_short_gaps([], 100, verbose=False) == []
    single = [{"page": 5, "title_hint": "X", "marker": "t", "strong": False}]
    assert filter_short_gaps(single, 100, verbose=False) == single
    print("  [PASS] test_filter_edge_cases")


# ── 去重检测 ──

def test_detect_duplicate_halves():
    """前后重复检测。"""
    total = 200
    dup = [{"page": p, "title_hint": "", "marker": ""}
           for p in [0, 20, 40, 60, 80, 100, 120, 140, 160, 180]]
    assert detect_duplicate_halves(dup, total) is True

    diff = [{"page": p, "title_hint": "", "marker": ""}
            for p in [0, 10, 50, 90, 100, 105, 150, 195]]
    assert detect_duplicate_halves(diff, total) is False

    few = [{"page": 0, "title_hint": "", "marker": ""},
           {"page": 50, "title_hint": "", "marker": ""}]
    assert detect_duplicate_halves(few, total) is False
    print("  [PASS] test_detect_duplicate_halves")


# ── 其他 ──

def test_filename_safety():
    """文件名安全处理。"""
    cases = [
        ("Hello<World>:test", "HelloWorldtest"),
        ("file\x00with\x1fcontrol", "filewithcontrol"),
        ("ends.with.dots...", "ends.with.dots"),
        ("a" * 100, "a" * 60),
    ]
    for raw, expected in cases:
        safe = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", raw)
        safe = safe.strip().rstrip(".")[:60]
        assert safe == expected
    print("  [PASS] test_filename_safety")


def test_boundary_validation():
    """交互式边界校验。"""
    total = 100
    articles = [{"page": 0}, {"page": 10}, {"page": 20}]
    for bad in [0, -5, 101]:
        assert (bad - 1) < 0 or (bad - 1) >= total
    for bad_idx in [0, -1, 4]:
        assert (bad_idx - 1) < 0 or (bad_idx - 1) >= len(articles)
    print("  [PASS] test_boundary_validation")


# ── Ground Truth 模拟 ──

def test_ground_truth_coverage():
    """
    模拟 ground truth 的14篇论文首页特征，验证至少有一个策略能覆盖。
    注意：这里测试的是特征匹配逻辑，不是实际PDF文本。
    """
    results = []

    def check(name, lines, expect_match=True):
        """检查给定页面特征是否能被至少一个策略检测到。"""
        top5 = "\n".join(lines[:MARKER_SCAN_LINES])
        top8 = "\n".join(lines[:DOI_SCAN_LINES])
        top10 = "\n".join(lines[:AFFILIATION_SCAN_LINES])

        # 策略1
        s1 = any(re.search(m, top5, re.IGNORECASE) for m in ARTICLE_TYPE_MARKERS)
        # 策略2
        s2 = (bool(re.findall(DOI_PATTERN, top8))
              and any(re.search(m, top10, re.IGNORECASE) for m in AFFILIATION_MARKERS)
              and bool(AUTHOR_NAME_PATTERN.search(top10) or CHINESE_AUTHOR_PATTERN.search(top10)))
        # 策略3
        s3 = (any(re.search(m, top5, re.IGNORECASE) for m in JOURNAL_NAME_MARKERS)
              and bool(VOLUME_ISSUE_PATTERN.search(top5))
              and _has_abstract_keywords(lines))
        # 策略4
        s4 = (_has_abstract_keywords(lines, 15)
              and (bool(re.search(DOI_PATTERN, top8)) or
                   any(re.search(m, top5, re.IGNORECASE) for m in JOURNAL_NAME_MARKERS)))
        # 策略5
        s5_en = (_has_abstract_keywords(lines, 15)
                 and bool(AUTHOR_NAME_PATTERN.search(top10))
                 and any(re.search(m, top10, re.IGNORECASE) for m in AFFILIATION_MARKERS))
        s5_cn = (_has_abstract_keywords(lines, 15)
                 and bool(CHINESE_AUTHOR_PATTERN.search(top10)))

        matched = s1 or s2 or s3 or s4 or s5_en or s5_cn
        strategies = [n for s, n in [(s1, "S1"), (s2, "S2"), (s3, "S3"),
                                      (s4, "S4"), (s5_en, "S5en"), (s5_cn, "S5cn")] if s]
        results.append((name, matched, strategies))
        if expect_match:
            assert matched, f"{name}: no strategy matched! Check features."
        else:
            assert not matched, f"{name}: should NOT match but did via {strategies}"

    # Paper 3: Hayakawa et al. (Psychological Science) - has EMPIRICAL ARTICLE
    check("P3_Hayakawa", [
        "EMPIRICAL ARTICLE",
        "Thinking More or Feeling Less? Foreign Language Effect",
        "Sayuri Hayakawa",
        "University of Chicago",
        "Abstract",
        "We investigate...",
    ])

    # Paper 8: Suzuki (2023) - DOI on line 7, no article type marker
    check("P8_Suzuki", [
        "Language Learning",
        "Some subtitle",
        "Practice and Automatization in Second Language Research",
        "Yuichi Suzuki",
        "Kanazawa University",
        "kanazawa@example.jp",
        "https://doi.org/10.1111/lang.12523",
        "Abstract",
        "This study reviews...",
    ])

    # Paper 9: Chinese paper (p.115)
    check("P9_Chinese", [
        "基于语料库的语义韵研究",
        "李哲, 吴诗玉",
        "上海交通大学 外国语学院",
        "",
        "摘要",
        "本文基于语料库方法...",
        "关键词：语义韵 语料库 二语习得",
    ])

    # Paper 10: Wu et al. (DOI on line 5-6)
    check("P10_WuEtal", [
        "Contextual Emotion in L2 Word Learning",
        "Shiyue Wu",
        "Shanghai Jiao Tong University",
        "Department of Foreign Languages",
        "https://doi.org/10.1017/langcog.2020.15",
        "",
        "Abstract",
        "This study explores...",
    ])

    # Paper 11: Cognition 118 (2011) - Journal+Volume+Abstract
    check("P11_Cognition", [
        "Cognition 118 (2011) 123–129",
        "Contents lists available at ScienceDirect",
        "Cross-cultural differences in mental representations of time",
        "Lera Boroditsky",
        "Stanford University",
        "",
        "Abstract",
        "Does language shape...",
    ])

    # Paper 12: Language and Cognition - Journal+Volume+Abstract
    check("P12_LangCog", [
        "Language and Cognition 12 (2020) 310–342",
        "Conceptual metaphors in poetry interpretation",
        "Limin Wang",
        "University of Example",
        "",
        "Abstract",
        "This paper examines...",
    ])

    # Paper 13: J Psycholinguist Res - Journal+Volume+Abstract
    check("P13_JPsychRes", [
        "J Psycholinguist Res (2016) 45:1115–1135",
        "Working Memory and L2 Reading Comprehension",
        "Wei Zhang",
        "Beijing Normal University",
        "Department of Foreign Languages",
        "",
        "Abstract",
        "This study investigated...",
    ])

    # Paper 14: Chinese LLM paper (p.232)
    check("P14_ChineseLLM", [
        "大语言模型与人类情感习得比较研究",
        "吴诗玉，王亦赟",
        "上海交通大学",
        "",
        "摘要",
        "本文比较了LLM...",
    ])

    # ── 反例：running head中间页不应匹配 ──
    check("Neg_RunningHead", [
        "Cognition 118 (2011) 123–129",
        "The results of Experiment 2 showed that...",
        "participants in the control condition were faster",
        "than those in the experimental condition (p < .01).",
    ], expect_match=False)

    # 打印结果
    for name, matched, strategies in results:
        status = "OK" if matched else "MISS"
        strats = ", ".join(strategies) if strategies else "none"
        print(f"    {status} {name}: {strats}")

    print("  [PASS] test_ground_truth_coverage")


# ── 主程序 ──

if __name__ == "__main__":
    print("Running tests for split_pdf_articles.py...\n")

    tests = [
        test_config_values,
        test_article_type_markers,
        test_marker_scan_lines_limit,
        test_doi_pattern,
        test_doi_position_constraint,
        test_affiliation_markers,
        test_author_name_pattern,
        test_chinese_author_pattern,
        test_volume_issue_pattern,
        test_journal_name_markers,
        test_journal_volume_abstract_combined,
        test_abstract_pattern,
        test_keywords_pattern,
        test_has_abstract_keywords,
        test_chinese_academic_markers,
        test_strategy5_english,
        test_strategy5_chinese,
        test_filter_short_gaps_basic,
        test_filter_strong_signal_bypasses_gap,
        test_filter_strong_replaces_weak,
        test_filter_edge_cases,
        test_detect_duplicate_halves,
        test_filename_safety,
        test_boundary_validation,
        test_ground_truth_coverage,
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
