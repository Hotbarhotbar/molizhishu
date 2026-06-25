"""
模力指数选题系统 — 搜索结果合并去重脚本

输入：来自6个平台的搜索结果（JSON）
输出：去重后的结构化候选列表

用法：
  python dedup.py <input.json> [--min-common-words 3] [--max-results 20]

输入格式 (JSON):
  [
    {"source": "weibo", "results": [{"title": "...", "snippet": "...", "url": "..."}, ...]},
    {"source": "zhihu", "results": [...]},
    ...
  ]
"""

import json
import re
import sys
from pathlib import Path
from typing import Any


def empty_result(reason: str = "", warning: str = "") -> dict:
    result = {
        "candidates": [],
        "total_scanned": 0,
        "total_deduped": 0,
        "sources_covered": [],
    }
    if reason:
        result["empty_reason"] = reason
    if warning:
        result["warning"] = warning
    return result


def tokenize(text: str) -> set[str]:
    """中文+英文混合分词：中文单字切分，英文按空格分词"""
    # 提取中文和英文单词
    chinese_chars = set(re.findall(r"[一-鿿]", text))
    english_words = set(re.findall(r"[a-zA-Z0-9]+", text.lower()))
    return chinese_chars | english_words


def title_similarity(title1: str, title2: str) -> float:
    """基于公共词/字的标题相似度（Jaccard）"""
    tokens1 = tokenize(title1)
    tokens2 = tokenize(title2)
    if not tokens1 or not tokens2:
        return 0.0
    intersection = tokens1 & tokens2
    union = tokens1 | tokens2
    return len(intersection) / len(union)


def dedup_candidates(
    candidates: list[dict],
    min_common_words: int = 5,
    similarity_threshold: float = 0.45,
) -> list[dict]:
    """
    去重逻辑：
    1. 基于 Jaccard 标题相似度（>= similarity_threshold）判断重复（主要依据）
    2. 基于公共词数（>= min_common_words）作为辅助判断
    3. 保留先出现的条目（跨平台出现则合并来源）

    注意：min_common_words 设得较高（5），避免"AI搜索"等通用词导致误合并。
    相似度阈值设得较低（0.45），因为跨平台报道同一事件时标题措辞可能差异较大。
    """
    seen_titles: list[str] = []
    deduped: list[dict] = []

    for item in candidates:
        title_lower = item.get("title", "").strip().lower()
        if not title_lower:
            continue

        is_dup = False
        for idx, seen_title in enumerate(seen_titles):
            common_words = tokenize(title_lower) & tokenize(seen_title)
            sim = title_similarity(title_lower, seen_title)
            # 两个条件都满足才算重复：相似度达标 AND 公共词数达标
            if sim >= similarity_threshold and len(common_words) >= min_common_words:
                # 合并来源
                existing_sources = deduped[idx].get("sources", [deduped[idx].get("source", "")])
                new_source = item.get("source", "")
                if new_source and new_source not in existing_sources:
                    existing_sources.append(new_source)
                deduped[idx]["sources"] = existing_sources
                is_dup = True
                break

        if not is_dup:
            seen_titles.append(title_lower)
            item["sources"] = [item.get("source", "")]
            deduped.append(item)

    return deduped


def as_items(value: Any) -> list[Any]:
    """Normalize common search-result containers to a list."""
    if value is None:
        return []

    if isinstance(value, str):
        try:
            return as_items(json.loads(value))
        except json.JSONDecodeError:
            return []

    if isinstance(value, list):
        return value

    if isinstance(value, dict):
        for key in ("results", "articles", "items", "data"):
            nested = value.get(key)
            if nested:
                return as_items(nested)

        if any(value.get(key) for key in ("title", "name", "url", "link", "snippet", "summary")):
            return [value]

    return []


def iter_source_groups(input_data: Any):
    """Yield (source_name, items) from supported input shapes."""
    if isinstance(input_data, list):
        for index, entry in enumerate(input_data):
            if isinstance(entry, dict) and any(key in entry for key in ("results", "articles", "items", "data")):
                source_name = (
                    entry.get("source")
                    or entry.get("source_name")
                    or entry.get("source_platform")
                    or entry.get("platform")
                    or f"source_{index + 1}"
                )
                yield source_name, as_items(entry)
            else:
                yield "input", as_items(input_data)
                break
        return

    if isinstance(input_data, dict):
        for key, value in input_data.items():
            source_name = str(key).replace("search_", "")
            if isinstance(value, dict):
                source_name = (
                    value.get("source")
                    or value.get("source_name")
                    or value.get("source_platform")
                    or value.get("platform")
                    or source_name
                )
            yield source_name, as_items(value)


def main(args: Any) -> dict:
    """
    主函数：合并多路搜索结果并去重

    Args:
        args: {
            "search_weibo": [...],
            "search_zhihu": [...],
            "search_baidu": [...],
            "search_36kr": [...],
            "search_wechat": [...],
            "search_xiaohongshu": [...],
        }

    Returns:
        {
            "candidates": [...],
            "total_scanned": int,
            "total_deduped": int,
            "sources_covered": [...],
        }
    """
    all_results: list[dict] = []

    for source_name, items in iter_source_groups(args):
        for item in items:
            if not isinstance(item, dict):
                continue
            title = item.get("title", "") or item.get("name", "")
            snippet = (
                item.get("snippet", "")
                or item.get("description", "")
                or item.get("summary", "")
                or item.get("content", "")
            )
            url = item.get("url", "") or item.get("link", "")
            source = item.get("source", "") or item.get("source_name", "") or source_name

            if not title:
                continue

            all_results.append(
                {
                    "title": title.strip(),
                    "snippet": snippet.strip()[:300] if snippet else "",
                    "url": url.strip() if url else "",
                    "source": str(source),
                }
            )

    deduped = dedup_candidates(all_results)

    # 控制数量上限
    deduped = deduped[:20]

    return {
        "candidates": deduped,
        "total_scanned": len(all_results),
        "total_deduped": len(deduped),
        "sources_covered": list(set(item.get("source", "") for item in deduped)),
    }


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(json.dumps(empty_result("missing_input_path"), ensure_ascii=False, indent=2))
        sys.exit(0)

    input_path = Path(sys.argv[1])
    if not input_path.exists():
        print(json.dumps(empty_result("input_file_not_found", str(input_path)), ensure_ascii=False, indent=2))
        sys.exit(0)

    try:
        with open(input_path, encoding="utf-8") as f:
            input_data = json.load(f)
    except json.JSONDecodeError as e:
        print(json.dumps(empty_result("invalid_json", str(e)), ensure_ascii=False, indent=2))
        sys.exit(0)
    except OSError as e:
        print(json.dumps(empty_result("input_read_failed", str(e)), ensure_ascii=False, indent=2))
        sys.exit(0)

    result = main(input_data)
    print(json.dumps(result, ensure_ascii=False, indent=2))
