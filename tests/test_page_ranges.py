"""页码范围与区域应用逻辑。"""

from __future__ import annotations

from pdf_dewatermark.core.page_ranges import (
    ApplyPageMode,
    apply_region_templates,
    format_pages_preview,
    parse_page_spec,
    resolve_apply_pages,
)
from pdf_dewatermark.models import RegionRect


def test_parse_page_spec_mixed():
    assert parse_page_spec("1,5,9", 20) == [0, 4, 8]
    assert parse_page_spec("2-4", 20) == [1, 2, 3]
    assert parse_page_spec("1-3,8,12-13", 20) == [0, 1, 2, 7, 11, 12]
    assert parse_page_spec("1，3，5", 10) == [0, 2, 4]
    assert parse_page_spec("99", 10) == []
    assert parse_page_spec("3-1", 5) == [0, 1, 2]  # swapped


def test_resolve_odd_even_all():
    assert resolve_apply_pages(ApplyPageMode.ALL, 5) == [0, 1, 2, 3, 4]
    assert resolve_apply_pages(ApplyPageMode.ODD, 5) == [0, 2, 4]
    assert resolve_apply_pages(ApplyPageMode.EVEN, 5) == [1, 3]
    assert resolve_apply_pages(ApplyPageMode.EVERY_OTHER_FROM, 6, current_index=1) == [1, 3, 5]
    assert resolve_apply_pages(ApplyPageMode.EVERY_OTHER_FROM, 6, current_index=0) == [0, 2, 4]
    assert resolve_apply_pages(ApplyPageMode.CUSTOM, 10, custom_spec="2,4") == [1, 3]


def test_apply_templates_replace():
    regions = [
        RegionRect(0, 10, 10, 50, 50),
        RegionRect(1, 0, 0, 5, 5),  # other page junk
        RegionRect(2, 1, 1, 2, 2),
    ]
    # template on page 0
    out = apply_region_templates(regions, 0, [0, 2, 4], replace=True)
    pages = sorted({r.page_index for r in out})
    assert pages == [0, 1, 2, 4]  # page1 junk kept; 2 replaced; 4 added
    assert sum(1 for r in out if r.page_index == 2) == 1
    r2 = next(r for r in out if r.page_index == 2)
    assert r2.normalized() == (10, 10, 50, 50)


def test_apply_templates_append():
    regions = [RegionRect(0, 10, 10, 20, 20), RegionRect(1, 0, 0, 1, 1)]
    out = apply_region_templates(regions, 0, [1], replace=False)
    assert sum(1 for r in out if r.page_index == 1) == 2


def test_format_preview():
    s = format_pages_preview([0, 2, 4])
    assert "1" in s and "3" in s and "共 3 页" in s
