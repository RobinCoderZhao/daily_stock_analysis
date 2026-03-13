# -*- coding: utf-8 -*-
"""
Structure detection tools — algorithmic price structure analysis.

Tools:
- detect_structure: Detect pivot points, support/resistance boxes,
  and optional Chan Theory segments/hubs from historical price data.
"""

import logging
from typing import List, Tuple

from src.agent.tools.registry import ToolParameter, ToolDefinition

logger = logging.getLogger(__name__)


def _get_fetcher_manager():
    """Lazy import to avoid circular deps."""
    from data_provider import DataFetcherManager
    return DataFetcherManager()


# ============================================================
# Pivot point detection (fractal-based)
# ============================================================

def _find_pivots(
    highs: List[float],
    lows: List[float],
    closes: List[float],
    window: int = 5,
) -> Tuple[List[dict], List[dict]]:
    """Detect local pivot highs and pivot lows using a fractal window.

    A pivot high at index i means highs[i] is the maximum in
    highs[i-window : i+window+1].  Similarly for pivot lows.

    Returns:
        (pivot_highs, pivot_lows) — each a list of
        {"index": int, "price": float}.
    """
    n = len(highs)
    pivot_highs: List[dict] = []
    pivot_lows: List[dict] = []

    for i in range(window, n - window):
        # Pivot high
        if highs[i] == max(highs[i - window: i + window + 1]):
            pivot_highs.append({"index": i, "price": highs[i]})
        # Pivot low
        if lows[i] == min(lows[i - window: i + window + 1]):
            pivot_lows.append({"index": i, "price": lows[i]})

    return pivot_highs, pivot_lows


# ============================================================
# Box detection (range-bound consolidation)
# ============================================================

def _detect_box(
    highs: List[float],
    lows: List[float],
    closes: List[float],
    pivot_highs: List[dict],
    pivot_lows: List[dict],
    tolerance_pct: float = 2.0,
) -> dict:
    """Detect if the recent price action forms a consolidation box.

    Algorithm:
    1. Cluster pivot highs that are within tolerance_pct of each other → box top.
    2. Cluster pivot lows similarly → box bottom.
    3. A valid box requires >= 2 touches on both top and bottom.
    """
    if len(pivot_highs) < 2 or len(pivot_lows) < 2:
        return {"box_detected": False, "reason": "Insufficient pivot points"}

    # Take the most recent pivots (last 10 of each)
    recent_highs = pivot_highs[-10:]
    recent_lows = pivot_lows[-10:]

    # Cluster pivot highs
    high_prices = [p["price"] for p in recent_highs]
    high_clusters = _cluster_prices(high_prices, tolerance_pct)

    # Cluster pivot lows
    low_prices = [p["price"] for p in recent_lows]
    low_clusters = _cluster_prices(low_prices, tolerance_pct)

    if not high_clusters or not low_clusters:
        return {"box_detected": False, "reason": "No clear price clusters"}

    # Find the best box: largest cluster on each side
    best_top_cluster = max(high_clusters, key=lambda c: c["count"])
    best_bot_cluster = max(low_clusters, key=lambda c: c["count"])

    box_top = best_top_cluster["center"]
    box_bottom = best_bot_cluster["center"]

    if box_top <= box_bottom:
        return {"box_detected": False, "reason": "Top <= bottom, invalid box"}

    box_width_pct = round((box_top - box_bottom) / box_bottom * 100, 2)

    # Validate: box should be within a reasonable range (2-20%)
    if box_width_pct < 2:
        return {"box_detected": False, "reason": f"Box too narrow ({box_width_pct}%)"}
    if box_width_pct > 25:
        return {"box_detected": False, "reason": f"Box too wide ({box_width_pct}%)"}

    current_price = closes[-1]
    dist_to_top = round((box_top - current_price) / current_price * 100, 2)
    dist_to_bottom = round((current_price - box_bottom) / current_price * 100, 2)

    # Determine current zone
    mid = (box_top + box_bottom) / 2
    if current_price > box_top * 1.01:
        zone = "突破箱顶"
    elif current_price < box_bottom * 0.99:
        zone = "跌破箱底"
    elif current_price >= mid:
        zone = "箱顶区域"
    else:
        zone = "箱底区域"

    return {
        "box_detected": True,
        "box_top": round(box_top, 2),
        "box_bottom": round(box_bottom, 2),
        "box_width_pct": box_width_pct,
        "touch_count_top": best_top_cluster["count"],
        "touch_count_bottom": best_bot_cluster["count"],
        "current_price": round(current_price, 2),
        "current_zone": zone,
        "distance_to_top_pct": dist_to_top,
        "distance_to_bottom_pct": dist_to_bottom,
        "box_valid": best_top_cluster["count"] >= 2 and best_bot_cluster["count"] >= 2,
    }


def _cluster_prices(prices: List[float], tolerance_pct: float) -> List[dict]:
    """Cluster prices within tolerance_pct of each other.

    Returns list of {"center": float, "count": int, "prices": List[float]}.
    """
    if not prices:
        return []

    sorted_prices = sorted(prices)
    clusters: List[dict] = []
    current_cluster = [sorted_prices[0]]

    for i in range(1, len(sorted_prices)):
        if current_cluster:
            center = sum(current_cluster) / len(current_cluster)
            diff_pct = abs(sorted_prices[i] - center) / center * 100
            if diff_pct <= tolerance_pct:
                current_cluster.append(sorted_prices[i])
            else:
                clusters.append({
                    "center": round(sum(current_cluster) / len(current_cluster), 2),
                    "count": len(current_cluster),
                    "prices": current_cluster,
                })
                current_cluster = [sorted_prices[i]]

    if current_cluster:
        clusters.append({
            "center": round(sum(current_cluster) / len(current_cluster), 2),
            "count": len(current_cluster),
            "prices": current_cluster,
        })

    return clusters


# ============================================================
# Chan Theory basic structure detection
# ============================================================

def _detect_chan_structure(
    highs: List[float],
    lows: List[float],
    pivot_highs: List[dict],
    pivot_lows: List[dict],
) -> dict:
    """Detect basic Chan Theory structures.

    This is a simplified implementation focusing on:
    - Bi (笔): alternating pivot high/low pairs
    - Zhongshu (中枢): overlapping range of 3 consecutive bi
    """
    # Build alternating bi sequence from pivots
    all_pivots = []
    for p in pivot_highs:
        all_pivots.append({"index": p["index"], "price": p["price"], "type": "high"})
    for p in pivot_lows:
        all_pivots.append({"index": p["index"], "price": p["price"], "type": "low"})

    all_pivots.sort(key=lambda x: x["index"])

    # Remove consecutive same-type pivots (keep extreme)
    bi_sequence: List[dict] = []
    for p in all_pivots:
        if not bi_sequence or bi_sequence[-1]["type"] != p["type"]:
            bi_sequence.append(p)
        else:
            # Same type: keep the more extreme one
            if p["type"] == "high" and p["price"] > bi_sequence[-1]["price"]:
                bi_sequence[-1] = p
            elif p["type"] == "low" and p["price"] < bi_sequence[-1]["price"]:
                bi_sequence[-1] = p

    bi_count = max(0, len(bi_sequence) - 1)

    # Detect zhongshu (中枢): 3 consecutive bi forming overlapping range
    zhongshu_list = []
    if len(bi_sequence) >= 4:
        for i in range(len(bi_sequence) - 3):
            # Get the range of each bi
            ranges = []
            for j in range(i, i + 4):
                if j + 1 < len(bi_sequence):
                    hi = max(bi_sequence[j]["price"], bi_sequence[j + 1]["price"])
                    lo = min(bi_sequence[j]["price"], bi_sequence[j + 1]["price"])
                    ranges.append((lo, hi))

            if len(ranges) >= 3:
                # Zhongshu = intersection of all 3 bi ranges
                zs_low = max(r[0] for r in ranges[:3])
                zs_high = min(r[1] for r in ranges[:3])
                if zs_high > zs_low:
                    zhongshu_list.append({
                        "start_index": bi_sequence[i]["index"],
                        "end_index": bi_sequence[i + 3]["index"],
                        "zs_high": round(zs_high, 2),
                        "zs_low": round(zs_low, 2),
                        "zs_range_pct": round((zs_high - zs_low) / zs_low * 100, 2),
                    })

    # Determine current trend relative to zhongshu
    current_trend = "无法判断"
    if zhongshu_list:
        last_zs = zhongshu_list[-1]
        last_price = highs[-1] if len(highs) > 0 else 0
        last_low = lows[-1] if len(lows) > 0 else 0
        mid = (last_zs["zs_high"] + last_zs["zs_low"]) / 2
        if last_low > last_zs["zs_high"]:
            current_trend = "中枢上方（多头延续）"
        elif last_price < last_zs["zs_low"]:
            current_trend = "中枢下方（空头延续）"
        elif last_price > mid:
            current_trend = "中枢内偏上"
        else:
            current_trend = "中枢内偏下"

    return {
        "bi_count": bi_count,
        "zhongshu_count": len(zhongshu_list),
        "zhongshu_list": zhongshu_list[-3:] if zhongshu_list else [],  # Keep last 3
        "current_trend": current_trend,
    }


# ============================================================
# Handler
# ============================================================

def _handle_detect_structure(stock_code: str, mode: str = "box", days: int = 120) -> dict:
    """Detect price structure: pivots, boxes, or Chan Theory structures."""
    import pandas as pd

    manager = _get_fetcher_manager()
    df, source = manager.get_daily_data(stock_code, days=max(days, 120))

    if df is None or df.empty:
        return {"error": f"No historical data for {stock_code}"}

    if len(df) < 30:
        return {"error": f"Insufficient data for structure detection ({len(df)} days, need >= 30)"}

    highs = df["high"].tolist()
    lows = df["low"].tolist()
    closes = df["close"].tolist()

    # Detect pivots (always needed)
    pivot_highs, pivot_lows = _find_pivots(highs, lows, closes, window=5)

    result = {
        "code": stock_code,
        "mode": mode,
        "data_days": len(df),
        "pivot_highs_count": len(pivot_highs),
        "pivot_lows_count": len(pivot_lows),
        "recent_pivot_highs": [
            {"price": p["price"], "bars_ago": len(df) - 1 - p["index"]}
            for p in pivot_highs[-5:]
        ],
        "recent_pivot_lows": [
            {"price": p["price"], "bars_ago": len(df) - 1 - p["index"]}
            for p in pivot_lows[-5:]
        ],
    }

    if mode == "box":
        box = _detect_box(highs, lows, closes, pivot_highs, pivot_lows)
        result["box"] = box
    elif mode == "chan":
        chan = _detect_chan_structure(highs, lows, pivot_highs, pivot_lows)
        result["chan"] = chan
    elif mode == "pivots":
        pass  # Pivots already in result
    elif mode == "all":
        result["box"] = _detect_box(highs, lows, closes, pivot_highs, pivot_lows)
        result["chan"] = _detect_chan_structure(highs, lows, pivot_highs, pivot_lows)
    else:
        return {"error": f"Unknown mode '{mode}'. Use 'box', 'chan', 'pivots', or 'all'."}

    return result


# ============================================================
# Tool definition
# ============================================================

detect_structure_tool = ToolDefinition(
    name="detect_structure",
    description="Detect price structure from historical data. "
                "Modes: 'box' (consolidation box with support/resistance), "
                "'chan' (Chan Theory: bi/zhongshu detection), "
                "'pivots' (local highs/lows only), "
                "'all' (box + chan combined). "
                "Returns pivot points, box boundaries, touch counts, "
                "zhongshu ranges, and current zone/trend assessment.",
    parameters=[
        ToolParameter(
            name="stock_code",
            type="string",
            description="Stock code, e.g., '600519'",
        ),
        ToolParameter(
            name="mode",
            type="string",
            description="Detection mode: 'box', 'chan', 'pivots', or 'all'",
            required=False,
            default="box",
            enum=["box", "chan", "pivots", "all"],
        ),
        ToolParameter(
            name="days",
            type="integer",
            description="Days of history to analyze (default: 120, min: 30)",
            required=False,
            default=120,
        ),
    ],
    handler=_handle_detect_structure,
    category="analysis",
)


# ============================================================
# Export
# ============================================================

ALL_STRUCTURE_TOOLS = [
    detect_structure_tool,
]
