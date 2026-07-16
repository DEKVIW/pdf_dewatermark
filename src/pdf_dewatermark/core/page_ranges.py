"""页码范围解析与「应用到…」目标页解析。

页码对用户为 1-based；内部列表为 0-based page_index。
"""

from __future__ import annotations

from enum import Enum
from typing import Iterable, List, Sequence, Set


class ApplyPageMode(str, Enum):
    ALL = "all"
    ODD = "odd"
    EVEN = "even"
    EVERY_OTHER_FROM = "every_other_from"
    CUSTOM = "custom"


def parse_page_spec(spec: str, page_count: int) -> List[int]:
    """
    解析自定义页码（1-based 输入）。

    支持：
      - 单页：1, 5, 9
      - 范围：2-20、2~20
      - 混合：1-3,8,12-15
    非法片段跳过；结果去重排序，落在 [0, page_count)。
    """
    if page_count <= 0:
        return []
    text = (spec or "").strip().replace("，", ",").replace("；", ",").replace(";", ",")
    if not text:
        return []

    found: Set[int] = set()
    for part in text.split(","):
        part = part.strip().replace(" ", "")
        if not part:
            continue
        if "-" in part or "~" in part:
            sep = "-" if "-" in part else "~"
            a, _, b = part.partition(sep)
            try:
                start = int(a.strip())
                end = int(b.strip())
            except ValueError:
                continue
            if start > end:
                start, end = end, start
            for p in range(start, end + 1):
                if 1 <= p <= page_count:
                    found.add(p - 1)
        else:
            try:
                p = int(part)
            except ValueError:
                continue
            if 1 <= p <= page_count:
                found.add(p - 1)
    return sorted(found)


def resolve_apply_pages(
    mode: ApplyPageMode | str,
    page_count: int,
    *,
    current_index: int = 0,
    custom_spec: str = "",
) -> List[int]:
    """
    解析「应用到…」的目标页（0-based，已排序去重）。

    - ALL: 全部
    - ODD / EVEN: 用户页码 1,3,5… / 2,4,6…
    - EVERY_OTHER_FROM: 从 current_index 起每隔一页
    - CUSTOM: 见 parse_page_spec
    """
    if page_count <= 0:
        return []
    m = mode.value if isinstance(mode, ApplyPageMode) else str(mode)

    if m == ApplyPageMode.ALL.value:
        return list(range(page_count))

    if m == ApplyPageMode.ODD.value:
        # 用户第 1、3、5… 页 → index 0,2,4…
        return list(range(0, page_count, 2))

    if m == ApplyPageMode.EVEN.value:
        return list(range(1, page_count, 2))

    if m == ApplyPageMode.EVERY_OTHER_FROM.value:
        cur = max(0, min(int(current_index), page_count - 1))
        return list(range(cur, page_count, 2))

    if m == ApplyPageMode.CUSTOM.value:
        return parse_page_spec(custom_spec, page_count)

    return []


def format_pages_preview(indices: Sequence[int], *, max_show: int = 10) -> str:
    """状态/对话框预览：第 2、4、6…24 页（共 12 页）。"""
    if not indices:
        return "（无匹配页）"
    pages_1 = [i + 1 for i in indices]
    n = len(pages_1)
    if n <= max_show:
        body = "、".join(str(p) for p in pages_1)
        return f"第 {body} 页（共 {n} 页）"
    head = "、".join(str(p) for p in pages_1[: max_show - 1])
    return f"第 {head}…{pages_1[-1]} 页（共 {n} 页）"


def apply_region_templates(
    regions: Sequence,
    source_page: int,
    target_pages: Iterable[int],
    *,
    replace: bool = True,
) -> List:
    """
    将 source_page 上的矩形模板应用到 target_pages。

    regions 元素需有 page_index / normalized() / color（RegionRect）。
    replace=True：先去掉目标页上已有区域再写入模板。
    """
    from ..models import RegionRect

    templates = [r for r in regions if r.page_index == source_page]
    if not templates:
        return list(regions)

    targets = sorted({int(p) for p in target_pages})
    if not targets:
        return list(regions)

    target_set = set(targets)
    if replace:
        out: List[RegionRect] = [r for r in regions if r.page_index not in target_set]
    else:
        out = list(regions)

    for p in targets:
        for t in templates:
            x0, y0, x1, y1 = t.normalized()
            color = getattr(t, "color", (255, 255, 255))
            out.append(
                RegionRect(
                    page_index=p,
                    x0=x0,
                    y0=y0,
                    x1=x1,
                    y1=y1,
                    color=color,
                )
            )
    return out
