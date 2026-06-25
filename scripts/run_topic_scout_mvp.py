"""
Offline MVP runner for GEO hotspot collection and topic brief generation.

Current scope:
- Six topic-basis collection branches are pluggable collectors.
- No network dependency is required; empty/example/local JSON inputs are supported.
- Knowledge-vault loading is optional and never blocks the report.
- Historical article deduplication is intentionally disabled for this MVP.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Callable

from dedup import dedup_candidates


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "outputs" / "topic-briefs"


@dataclass(frozen=True)
class TopicCategory:
    key: str
    topic_type: str
    search_target: str
    translation_chain: str
    queries: tuple[str, ...]


@dataclass
class BranchResult:
    key: str
    topic_type: str
    query: str
    search_target: str
    translation_chain: str
    items: list[dict[str, Any]]
    empty_reason: str = ""
    warning: str = ""


@dataclass
class ScoreResult:
    candidate: dict[str, Any]
    status: str
    user_value: int
    differentiation: int
    spread: int
    total: int
    matched_geo: list[str]
    capabilities: list[str]
    risk: str
    reason: str


CATEGORIES: tuple[TopicCategory, ...] = (
    TopicCategory(
        key="industry",
        topic_type="行业选题",
        search_target="竞品爆款文章、同行观点、GEO服务商共性痛点",
        translation_chain="竞品爆款仿写 / 行业痛点 -> 服务商问题 -> 差异化角度",
        queries=(
            "GEO 服务商 客户 痛点",
            "AI搜索优化 服务商 月报 验收",
            "GEO 爆款 公众号",
        ),
    ),
    TopicCategory(
        key="market_hotspot",
        topic_type="市场热点选题",
        search_target="国内AI平台、营销科技、AI搜索、广告商业化、品牌监测热点",
        translation_chain="获得热点 -> 选题角度 -> 选题依据 -> 利他因素",
        queries=(
            "AI搜索 品牌监测",
            "大模型 搜索 广告",
            "豆包 DeepSeek 元宝 品牌 推荐",
        ),
    ),
    TopicCategory(
        key="policy",
        topic_type="国家政策选题",
        search_target="网信办、工信部、市监总局、信通院、地方AI政策",
        translation_chain="政策 -> 行业影响 -> 选题角度 -> 研究院话语权 -> 指导行动",
        queries=(
            "生成式人工智能 监管",
            "算法备案 AI应用治理",
            "广告合规 数字营销",
        ),
    ),
    TopicCategory(
        key="research_report",
        topic_type="研报选题",
        search_target="信通院、QuestMobile、艾瑞、易观、平台白皮书、营销报告",
        translation_chain="研报 -> 受众人群 -> 选题角度 -> 选题依据 -> 执行策略",
        queries=(
            "AI营销 报告",
            "品牌AI竞争力",
            "AI搜索 用户行为",
            "GEO 白皮书",
        ),
    ),
    TopicCategory(
        key="product_service",
        topic_type="产品服务选题",
        search_target="模力指数服务升级、服务优势、客户试用/交付场景",
        translation_chain="服务升级 -> 服务优势 -> 试用场景 -> 选题角度 -> 选题依据",
        queries=(
            "GEO诊断 服务升级",
            "AI答案监测 试用",
            "品牌体检 服务商",
        ),
    ),
    TopicCategory(
        key="product_feature",
        topic_type="产品功能选题",
        search_target="品牌诊断、问题监控、舆情监控、内容监控、竞品对比、报告生成",
        translation_chain="功能优势 -> 问题 -> 目标受众 -> 选题角度 -> 选题依据",
        queries=(
            "品牌诊断 竞品对比",
            "AI答案监测 报告生成",
            "信源分析 排名波动",
        ),
    ),
)


EXAMPLE_RESULTS: dict[str, list[dict[str, str]]] = {
    "industry": [
        {
            "title": "AI搜索品牌可见性讨论升温，答案入口开始被行业关注",
            "snippet": "行业文章讨论品牌可见性和AI搜索趋势，暂缺案例和报告锚点，适合作为储备观察。",
            "source": "example_industry",
            "url": "https://example.local/geo-industry-observation",
            "date": "2026-06-25",
        }
    ],
    "market_hotspot": [
        {
            "title": "微信小微AI助手灰度上线，品牌在微信内的答案入口要重新算账",
            "snippet": "微信开始灰度原生AI助手小微，入口、搜索、服务调用和小程序推荐可能改变品牌可见性。GEO服务商需要解释客户为什么要监测微信生态里的AI答案。",
            "source": "example_wechat",
            "url": "https://example.local/wechat-ai-xiaowei",
            "date": "2026-06-25",
        },
        {
            "title": "大模型搜索广告测试提速，品牌推荐位开始从自然答案走向商业化",
            "snippet": "多个AI搜索入口出现广告和推荐位测试，客户会追问自然可见性、付费曝光和竞品推荐之间的归因边界。",
            "source": "example_hotspot",
            "url": "https://example.local/ai-search-ads",
            "date": "2026-06-25",
        },
    ],
    "policy": [
        {
            "title": "地方生成式AI应用治理指引发布，广告内容标注和算法备案被反复强调",
            "snippet": "政策信号涉及生成式人工智能、广告合规、内容标注和风险预警。服务商需要把客户的AI答案监测报告从效果汇报扩展到合规复盘。",
            "source": "example_policy",
            "url": "https://example.local/ai-policy",
            "date": "2026-06-25",
        }
    ],
    "research_report": [
        {
            "title": "AI搜索用户行为报告：超过70%的用户会先相信答案摘要而不是点进官网",
            "snippet": "报告显示，品牌官网流量和AI答案引用之间出现断层。GEO诊断、信源分析和竞品对比能帮助服务商把争论变成数据。",
            "source": "example_report",
            "url": "https://example.local/ai-search-report",
            "date": "2026-06-25",
        }
    ],
    "product_service": [
        {
            "title": "模力指数试用场景升级：从品牌体检扩展到月度报告复盘",
            "snippet": "服务升级面向GEO服务商交付、验收和续费沟通，重点承接AI答案监测、品牌体检、竞品对比和报告生成。",
            "source": "example_product",
            "url": "https://example.local/molizhishu-service",
            "date": "2026-06-25",
        }
    ],
    "product_feature": [
        {
            "title": "品牌诊断新增竞品对比视图，客户可以看到谁被AI答案优先引用",
            "snippet": "功能围绕AI答案监测、品牌诊断、信源分析和报告生成，适合转化为服务商验收指标和客户沟通话术。",
            "source": "example_feature",
            "url": "https://example.local/feature-competitor",
            "date": "2026-06-25",
        },
        {
            "title": "某明星AI写真滤镜爆火，社交平台转发量破百万",
            "snippet": "娱乐热点与GEO、品牌监测、AI搜索和服务商交付没有直接关系。",
            "source": "example_noise",
            "url": "https://example.local/noise",
            "date": "2026-06-25",
        },
    ],
}


KNOWLEDGE_FILES = (
    Path("00_入口_先读我.md"),
    Path("10_核心规则") / "品牌声音与读者定位.md",
    Path("20_专项流程") / "GEO写作专项.md",
    Path("20_专项流程") / "热点事件型文章.md",
    Path("30_模板") / "文章Brief模板.md",
)


GEO_KEYWORDS = (
    "GEO",
    "生成式引擎",
    "AI搜索",
    "AI 搜索",
    "AI答案",
    "AI 答案",
    "答案摘要",
    "答案引用",
    "品牌可见",
    "品牌监测",
    "大模型",
    "模型搜索",
    "豆包",
    "DeepSeek",
    "元宝",
    "微信小微",
    "小微AI",
    "生成式人工智能",
    "算法备案",
    "广告合规",
    "搜索广告",
)

PRODUCT_CAPABILITY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "AI答案监测": ("AI答案监测", "AI 答案监测", "答案监测", "答案摘要", "答案引用"),
    "品牌体检": ("品牌体检", "品牌可见", "品牌监测", "品牌官网"),
    "GEO诊断": ("GEO诊断", "GEO 诊断", "生成式引擎", "AI搜索"),
    "竞品对比": ("竞品对比", "竞品推荐", "竞品", "谁被AI答案优先引用"),
    "信源分析": ("信源分析", "信源", "引用", "官网流量"),
    "报告复盘": ("报告复盘", "月度报告", "验收", "复盘", "报告生成"),
    "风险预警": ("风险预警", "合规", "投诉", "备案", "标注"),
}

PAIN_KEYWORDS = (
    "客户",
    "服务商",
    "交付",
    "验收",
    "续费",
    "报价",
    "预算",
    "归因",
    "投诉",
    "风险",
    "合规",
    "竞品",
    "监测",
    "报告",
    "数据",
)

DIFFERENTIATION_KEYWORDS = (
    "灰度",
    "内测",
    "指引",
    "标准",
    "白皮书",
    "报告",
    "信源",
    "归因",
    "可追溯",
    "入口",
    "商业化",
    "断层",
)

PLATFORM_KEYWORDS = (
    "微信",
    "豆包",
    "DeepSeek",
    "元宝",
    "百度",
    "小红书",
    "抖音",
    "官网",
    "信通院",
    "网信办",
    "工信部",
)

RISK_TERMS = (
    "保证",
    "第一",
    "霸屏",
    "黑帽",
    "投毒",
    "封禁",
    "投诉",
    "合规",
    "备案",
    "待核验",
)

NEGATIVE_RELEVANCE_TERMS = (
    "没有直接关系",
    "无直接关系",
    "娱乐热点",
    "娱乐八卦",
    "明星",
    "写真",
    "滤镜",
    "转发量破百万",
)


def compact_text(value: Any, limit: int | None = None) -> str:
    text = "" if value is None else str(value)
    text = re.sub(r"\s+", " ", text).strip()
    if limit and len(text) > limit:
        return text[: limit - 1].rstrip() + "..."
    return text


def clamp_score(value: int) -> int:
    return max(1, min(5, value))


def contains_any(text: str, keywords: tuple[str, ...]) -> list[str]:
    return [keyword for keyword in keywords if keyword.lower() in text.lower()]


def has_number(text: str) -> bool:
    return bool(re.search(r"\d|一|二|三|四|五|六|七|八|九|十|百|千|万|亿", text))


def table_cell(value: Any) -> str:
    text = compact_text(value)
    return text.replace("|", "\\|") or "-"


def chinese_weekday(day: date) -> str:
    return "一二三四五六日"[day.weekday()]


def parse_run_date(value: str | None) -> date:
    if not value:
        return datetime.now().date()
    return datetime.strptime(value, "%Y-%m-%d").date()


def as_item_list(value: Any) -> list[dict[str, Any]]:
    if value is None:
        return []
    if isinstance(value, str):
        try:
            return as_item_list(json.loads(value))
        except json.JSONDecodeError:
            return []
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    if isinstance(value, dict):
        for key in ("results", "articles", "items", "candidates", "data"):
            if key in value:
                return as_item_list(value.get(key))
        if any(value.get(key) for key in ("title", "name", "url", "link", "snippet", "summary", "content")):
            return [value]
    return []


def collect_empty_fixture(category: TopicCategory, _: dict[str, Any] | None = None) -> BranchResult:
    return BranchResult(
        key=category.key,
        topic_type=category.topic_type,
        query=" / ".join(category.queries[:2]),
        search_target=category.search_target,
        translation_chain=category.translation_chain,
        items=[],
        empty_reason="offline_empty_fixture",
    )


def collect_example_fixture(category: TopicCategory, _: dict[str, Any] | None = None) -> BranchResult:
    items = EXAMPLE_RESULTS.get(category.key, [])
    return BranchResult(
        key=category.key,
        topic_type=category.topic_type,
        query=" / ".join(category.queries[:2]),
        search_target=category.search_target,
        translation_chain=category.translation_chain,
        items=items,
        empty_reason="" if items else "example_fixture_no_items",
    )


def collect_from_local_json(category: TopicCategory, input_data: dict[str, Any] | list[Any] | None) -> BranchResult:
    items: list[dict[str, Any]] = []
    warning = ""

    if input_data is None:
        warning = "input_json_unavailable"
    elif isinstance(input_data, dict):
        keys = (
            category.key,
            category.topic_type,
            category.topic_type.replace("选题", ""),
            f"search_{category.key}",
        )
        for key in keys:
            if key in input_data:
                items = as_item_list(input_data.get(key))
                break
    elif isinstance(input_data, list):
        for entry in input_data:
            if not isinstance(entry, dict):
                continue
            entry_key = str(entry.get("key") or entry.get("category") or entry.get("topic_type") or "")
            if entry_key in (category.key, category.topic_type, category.topic_type.replace("选题", "")):
                items.extend(as_item_list(entry))

    return BranchResult(
        key=category.key,
        topic_type=category.topic_type,
        query=" / ".join(category.queries[:2]),
        search_target=category.search_target,
        translation_chain=category.translation_chain,
        items=items,
        empty_reason="" if items else "local_json_no_items",
        warning=warning,
    )


def load_local_json(path: Path | None) -> tuple[dict[str, Any] | list[Any] | None, list[str]]:
    if path is None:
        return None, ["input_json_missing"]
    if not path.exists():
        return None, [f"input_json_not_found: {path}"]
    try:
        return json.loads(path.read_text(encoding="utf-8")), []
    except json.JSONDecodeError as exc:
        return None, [f"input_json_invalid: {exc}"]
    except OSError as exc:
        return None, [f"input_json_read_failed: {exc}"]


def collect_branches(args: argparse.Namespace) -> tuple[list[BranchResult], list[str]]:
    warnings: list[str] = []
    input_data: dict[str, Any] | list[Any] | None = None

    collectors: dict[str, Callable[[TopicCategory, dict[str, Any] | list[Any] | None], BranchResult]] = {
        "empty": collect_empty_fixture,
        "example": collect_example_fixture,
        "file": collect_from_local_json,
    }

    if args.fixture == "file":
        input_data, warnings = load_local_json(Path(args.input_json) if args.input_json else None)

    collector = collectors[args.fixture]
    return [collector(category, input_data) for category in CATEGORIES], warnings


def clean_candidates(branches: list[BranchResult]) -> tuple[list[dict[str, Any]], list[str]]:
    candidates: list[dict[str, Any]] = []
    warnings: list[str] = []

    for branch in branches:
        for index, item in enumerate(branch.items):
            title = compact_text(item.get("title") or item.get("name"), 120)
            snippet = compact_text(
                item.get("snippet")
                or item.get("summary")
                or item.get("description")
                or item.get("content"),
                320,
            )
            if not title and not snippet:
                warnings.append(f"{branch.topic_type}: item_{index + 1}_missing_title_and_snippet")
                continue
            if not title:
                title = compact_text(snippet, 60)

            source = compact_text(
                item.get("source")
                or item.get("source_name")
                or item.get("platform")
                or item.get("account")
                or branch.key,
                60,
            )
            candidates.append(
                {
                    "title": title,
                    "snippet": snippet,
                    "url": compact_text(item.get("url") or item.get("link"), 240),
                    "source": source,
                    "date": compact_text(item.get("date") or item.get("published_at"), 40),
                    "topic_type": branch.topic_type,
                    "topic_basis": branch.translation_chain,
                    "search_query": branch.query,
                    "search_target": branch.search_target,
                    "branch_key": branch.key,
                }
            )

    return candidates, warnings


def matched_capabilities(text: str) -> list[str]:
    matches: list[str] = []
    for capability, keywords in PRODUCT_CAPABILITY_KEYWORDS.items():
        if contains_any(text, keywords):
            matches.append(capability)
    return matches


def audit_risk(candidate: dict[str, Any], capabilities: list[str]) -> str:
    text = f"{candidate.get('title', '')} {candidate.get('snippet', '')}"
    risks = contains_any(text, RISK_TERMS)
    notes: list[str] = []
    if not candidate.get("url"):
        notes.append("缺少来源链接，事实需二次核验")
    if risks:
        notes.append("表达需避开绝对承诺/攻击性判断：" + "、".join(risks[:3]))
    if not capabilities:
        notes.append("产品承接边界不清")
    if not notes:
        notes.append("常规事实核验，避免把推断写成事实")
    return "；".join(notes)


def score_candidate(candidate: dict[str, Any]) -> ScoreResult:
    text = f"{candidate.get('title', '')} {candidate.get('snippet', '')}"
    topic_type = str(candidate.get("topic_type", ""))
    geo_matches = contains_any(text, GEO_KEYWORDS)
    capabilities = matched_capabilities(text)

    if topic_type in ("产品服务选题", "产品功能选题") and not capabilities:
        capabilities = ["报告复盘"]

    risk = audit_risk(candidate, capabilities)

    negative_matches = contains_any(text, NEGATIVE_RELEVANCE_TERMS)
    if negative_matches:
        return ScoreResult(
            candidate=candidate,
            status="discard",
            user_value=1,
            differentiation=1,
            spread=1,
            total=3,
            matched_geo=geo_matches,
            capabilities=capabilities,
            risk=risk,
            reason="命中非GEO/非业务相关噪声：" + "、".join(negative_matches[:3]),
        )

    if not geo_matches:
        return ScoreResult(
            candidate=candidate,
            status="discard",
            user_value=1,
            differentiation=1,
            spread=1,
            total=3,
            matched_geo=[],
            capabilities=capabilities,
            risk=risk,
            reason="GEO相关性不足",
        )

    if not capabilities and topic_type != "行业选题":
        return ScoreResult(
            candidate=candidate,
            status="discard",
            user_value=2,
            differentiation=2,
            spread=2,
            total=6,
            matched_geo=geo_matches,
            capabilities=[],
            risk=risk,
            reason="缺少自然产品承接能力",
        )

    pain_count = len(contains_any(text, PAIN_KEYWORDS))
    value = 1
    if capabilities:
        value += 1
    if pain_count >= 2:
        value += 1
    if contains_any(text, ("客户", "服务商", "交付", "验收", "续费")):
        value += 1
    if has_number(text) or contains_any(text, ("归因", "合规", "风险", "报告")):
        value += 1

    differentiation = 2
    if contains_any(text, DIFFERENTIATION_KEYWORDS):
        differentiation += 1
    if topic_type in ("国家政策选题", "研报选题", "产品功能选题"):
        differentiation += 1
    if len(set(geo_matches)) >= 2 or len(capabilities) >= 2:
        differentiation += 1

    spread = 2
    if contains_any(text, PLATFORM_KEYWORDS):
        spread += 1
    if has_number(text):
        spread += 1
    if contains_any(text, ("客户", "竞品", "风险", "合规", "广告", "入口")):
        spread += 1

    user_value = clamp_score(value)
    differentiation = clamp_score(differentiation)
    spread = clamp_score(spread)
    total = user_value + differentiation + spread

    if total >= 12:
        status = "recommend"
        reason = "GEO相关、可承接到产品能力，且具备服务商沟通价值"
    elif total >= 9:
        status = "reserve"
        reason = "有GEO相关性，但角度或证据还需要补强"
    else:
        status = "discard"
        reason = "分数不足，暂不进入选题池"

    return ScoreResult(
        candidate=candidate,
        status=status,
        user_value=user_value,
        differentiation=differentiation,
        spread=spread,
        total=total,
        matched_geo=geo_matches,
        capabilities=capabilities,
        risk=risk,
        reason=reason,
    )


def load_optional_knowledge() -> tuple[list[str], list[str]]:
    roots = [PROJECT_ROOT / "AI_Writing_Vault", PROJECT_ROOT.parent / "AI_Writing_Vault"]
    existing_root = next((root for root in roots if root.exists()), None)
    if existing_root is None:
        return [], ["knowledge_vault_missing_optional"]

    loaded: list[str] = []
    warnings: list[str] = []
    for relative_path in KNOWLEDGE_FILES:
        path = existing_root / relative_path
        if not path.exists():
            warnings.append(f"knowledge_file_missing_optional: {path}")
            continue
        try:
            # Read a small slice only to validate availability; the MVP scorer is heuristic.
            path.read_text(encoding="utf-8")[:2000]
            loaded.append(str(path))
        except OSError as exc:
            warnings.append(f"knowledge_file_read_failed_optional: {path} ({exc})")
    return loaded, warnings


def split_scores(scores: list[ScoreResult]) -> tuple[list[ScoreResult], list[ScoreResult], list[ScoreResult]]:
    recommended = [score for score in scores if score.status == "recommend"]
    reserve = [score for score in scores if score.status == "reserve"]
    discarded = [score for score in scores if score.status == "discard"]
    recommended.sort(key=lambda item: item.total, reverse=True)
    reserve.sort(key=lambda item: item.total, reverse=True)
    discarded.sort(key=lambda item: item.total, reverse=True)
    return recommended, reserve, discarded


def title_direction(score: ScoreResult) -> str:
    title = score.candidate.get("title", "")
    if score.total >= 12:
        return f"{title}：服务商该把哪些监测指标写进客户报告？"
    if score.total >= 9:
        return f"{title}：先作为储备，等待更多事实锚点"
    return title


def render_branch_review(branches: list[BranchResult]) -> list[str]:
    lines = [
        "## 六类采集复盘",
        "",
        "| 选题类型 | 检索目标 | 查询词 | 结果数 | 状态 |",
        "|---|---|---|---:|---|",
    ]
    for branch in branches:
        status_parts: list[str] = []
        if branch.empty_reason:
            status_parts.append(branch.empty_reason)
        if branch.warning:
            status_parts.append(branch.warning)
        status = "；".join(status_parts) if status_parts else "ok"
        lines.append(
            f"| {table_cell(branch.topic_type)} | {table_cell(branch.search_target)} | "
            f"{table_cell(branch.query)} | {len(branch.items)} | {table_cell(status)} |"
        )
    return lines


def render_recommended(scores: list[ScoreResult]) -> list[str]:
    lines = ["## 推荐选题", ""]
    if not scores:
        lines.append("今日无推荐选题。")
        return lines

    for index, score in enumerate(scores, start=1):
        candidate = score.candidate
        lines.extend(
            [
                f"### {index}. {title_direction(score)}",
                "",
                "| 字段 | 内容 |",
                "|---|---|",
                f"| 选题类型 | {table_cell(candidate.get('topic_type'))} |",
                f"| 主题 | {table_cell(candidate.get('title'))} |",
                f"| 第一读者 | GEO服务商负责人 / AI搜索优化团队 / 内容营销负责人 |",
                f"| 事件事实 | {table_cell(candidate.get('snippet'))} |",
                f"| 事实口径 | {table_cell('本地采集样本；正式发布前需核验原文链接' if candidate.get('url') else '本地样本；缺少原文链接，需补证')} |",
                f"| 选题依据 | {table_cell(candidate.get('topic_basis'))} |",
                f"| 产品主能力 | {table_cell('、'.join(score.capabilities) if score.capabilities else '暂不承接')} |",
                f"| 服务商落点 | 客户沟通 / 交付验收 / 报告复盘 / 风险预警 |",
                f"| 差异化角度 | 不只转述热点，重点回答服务商怎样把争论变成可监测指标。 |",
                f"| 标题方向 | {table_cell(title_direction(score))} |",
                f"| 最大风险 | {table_cell(score.risk)} |",
                f"| 发布结论预判 | {'可发' if score.total >= 12 else '需补证'} |",
                "",
                "#### 三维评分",
                f"- 用户价值：{score.user_value}/5",
                f"- 差异化：{score.differentiation}/5",
                f"- 传播性：{score.spread}/5",
                f"- 综合分：{score.total}/15",
                "",
                "#### 8项痛点深挖",
                "1. 多花了什么钱：预算被AI入口、广告位或内容投放重新分配。",
                "2. 在哪被质疑：客户会质疑交付指标、归因口径和验收证据。",
                "3. 没有监测争论什么：谁被推荐、为什么被引用、结果是否稳定。",
                "4. 什么指标变事实：答案出现率、引用信源、竞品对比、波动记录。",
                "5. 竞品压力在哪：竞品可能先占据答案摘要或推荐位。",
                "6. 投诉/合规风险：避免承诺排名，事实与推断分开写。",
                "7. 影响哪个阶段：售前解释、交付验收、月报复盘和续费沟通。",
                "8. 承接哪个能力：" + table_cell("、".join(score.capabilities) if score.capabilities else "暂不承接"),
                "",
            ]
        )
    return lines


def render_reserve(scores: list[ScoreResult]) -> list[str]:
    lines = [
        "## 储备选题（9-11分）",
        "",
        "| # | 选题 | 类型 | 评分 | 储备原因 | 何时激活 |",
        "|---:|---|---|---:|---|---|",
    ]
    if not scores:
        lines.append("| - | 今日无储备选题 | - | - | - | - |")
        return lines

    for index, score in enumerate(scores, start=1):
        lines.append(
            f"| {index} | {table_cell(title_direction(score))} | "
            f"{table_cell(score.candidate.get('topic_type'))} | {score.total}/15 | "
            f"{table_cell(score.reason)} | 补到官方来源、报告数据或客户案例后激活 |"
        )
    return lines


def render_discarded(scores: list[ScoreResult]) -> list[str]:
    lines = [
        "## 已放弃选题",
        "",
        "| # | 选题 | 类型 | 放弃原因 |",
        "|---:|---|---|---|",
    ]
    if not scores:
        lines.append("| - | 今日无放弃选题 | - | - |")
        return lines

    for index, score in enumerate(scores, start=1):
        lines.append(
            f"| {index} | {table_cell(score.candidate.get('title'))} | "
            f"{table_cell(score.candidate.get('topic_type'))} | {table_cell(score.reason)} |"
        )
    return lines


def render_quality_review(
    warnings: list[str],
    branch_warnings: list[str],
    knowledge_loaded: list[str],
    knowledge_warnings: list[str],
    feishu_status: str,
) -> list[str]:
    lines = ["## 搜索质量复盘", ""]
    all_warnings = warnings + branch_warnings + knowledge_warnings
    lines.append(f"- 知识库增强：{'已加载 ' + str(len(knowledge_loaded)) + ' 个文件' if knowledge_loaded else '可选跳过'}")
    lines.append("- 历史文章去重：未启用（按MVP要求，本轮不读取已发文章做排除）")
    lines.append(f"- 飞书推送：{feishu_status}")
    if not all_warnings:
        lines.append("- 运行告警：无")
    else:
        lines.append("- 运行告警：")
        for warning in all_warnings:
            lines.append(f"  - {warning}")
    return lines


def render_markdown(
    run_date: date,
    fixture: str,
    branches: list[BranchResult],
    raw_count: int,
    cleaned_count: int,
    deduped_count: int,
    recommended: list[ScoreResult],
    reserve: list[ScoreResult],
    discarded: list[ScoreResult],
    warnings: list[str],
    clean_warnings: list[str],
    knowledge_loaded: list[str],
    knowledge_warnings: list[str],
    feishu_status: str,
) -> str:
    all_empty = raw_count == 0 and cleaned_count == 0 and deduped_count == 0
    conclusion = (
        "今日未检索到可用 GEO 热点。"
        if all_empty
        else f"推荐写 {len(recommended)} 条，储备 {len(reserve)} 条，放弃 {len(discarded)} 条。"
    )

    lines = [
        "# 模力指数选题日报",
        f"**日期**：{run_date.isoformat()}（周{chinese_weekday(run_date)}）",
        f"**运行模式**：{fixture}",
        "**扫描方式**：六类选题依据本地采集占位 -> 清洗 -> 去重 -> GEO评分 -> 风险审核 -> Markdown保存",
        f"**原始候选数**：{raw_count} 条 | **清洗后候选数**：{cleaned_count} 条 | **去重后候选数**：{deduped_count} 条",
        f"**推荐写**：{len(recommended)} 条 | **可储备**：{len(reserve)} 条 | **已放弃**：{len(discarded)} 条",
        f"**结论**：{conclusion}",
        "",
        "---",
        "",
    ]

    if all_empty:
        lines.extend(
            [
                "## 今日结论",
                "",
                "今日未检索到可用 GEO 热点，所有采集分支均为空。下一轮优先追踪：AI搜索广告商业化、国内大模型入口变化、生成式AI监管/备案、GEO服务商交付验收争议。",
                "",
            ]
        )

    lines.extend(render_branch_review(branches))
    lines.append("")
    lines.extend(render_recommended(recommended))
    lines.append("")
    lines.extend(render_reserve(reserve))
    lines.append("")
    lines.extend(render_discarded(discarded))
    lines.append("")
    lines.extend(
        render_quality_review(
            warnings=warnings,
            branch_warnings=clean_warnings,
            knowledge_loaded=knowledge_loaded,
            knowledge_warnings=knowledge_warnings,
            feishu_status=feishu_status,
        )
    )
    lines.extend(
        [
            "",
            "## 下一次扫描建议",
            "",
            "- 优先补真实检索源：微信搜一搜、36氪/虎嗅、政策官网、研报来源、产品更新日志。",
            "- 每个分支允许空结果，但必须保留 empty_reason 或 warning。",
            "- 如果继续全空，日报保持空日报，不硬编选题。",
            "",
        ]
    )
    return "\n".join(lines)


def resolve_output_path(run_date: date, output: str | None, overwrite: bool) -> Path:
    if output:
        path = Path(output)
        if not path.is_absolute():
            path = PROJECT_ROOT / path
        return path

    DEFAULT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    preferred = DEFAULT_OUTPUT_DIR / f"{run_date.isoformat()}-topic-brief.md"
    if overwrite or not preferred.exists():
        return preferred

    for index in range(1, 100):
        candidate = DEFAULT_OUTPUT_DIR / f"{run_date.isoformat()}-topic-brief-{index}.md"
        if not candidate.exists():
            return candidate
    raise RuntimeError("could not resolve a non-conflicting output path")


def send_feishu_if_configured(webhook: str | None, markdown: str) -> str:
    webhook = webhook or os.environ.get("FEISHU_WEBHOOK_URL")
    if not webhook:
        return "未配置 webhook，仅保存 Markdown"

    payload = {
        "msg_type": "text",
        "content": {"text": compact_text(markdown, 3500)},
    }
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        webhook,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return f"已尝试推送，HTTP {response.status}"
    except Exception as exc:  # Network must not block report generation.
        return f"推送失败但已保存 Markdown：{exc}"


def run(args: argparse.Namespace) -> dict[str, Any]:
    run_date = parse_run_date(args.date)
    branches, input_warnings = collect_branches(args)
    raw_count = sum(len(branch.items) for branch in branches)
    cleaned, clean_warnings = clean_candidates(branches)
    deduped = dedup_candidates(
        cleaned,
        min_common_words=args.min_common_words,
        similarity_threshold=args.similarity_threshold,
    )[: args.max_candidates]
    scored = [score_candidate(candidate) for candidate in deduped]
    recommended, reserve, discarded = split_scores(scored)
    knowledge_loaded, knowledge_warnings = load_optional_knowledge()

    feishu_status = "未配置 webhook，仅保存 Markdown"
    markdown = render_markdown(
        run_date=run_date,
        fixture=args.fixture,
        branches=branches,
        raw_count=raw_count,
        cleaned_count=len(cleaned),
        deduped_count=len(deduped),
        recommended=recommended[: args.count],
        reserve=reserve,
        discarded=discarded,
        warnings=input_warnings,
        clean_warnings=clean_warnings,
        knowledge_loaded=knowledge_loaded,
        knowledge_warnings=knowledge_warnings,
        feishu_status=feishu_status,
    )

    output_path = resolve_output_path(run_date, args.output, args.overwrite)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(markdown, encoding="utf-8")

    if args.feishu_webhook or os.environ.get("FEISHU_WEBHOOK_URL"):
        feishu_status = send_feishu_if_configured(args.feishu_webhook, markdown)
        markdown = markdown.replace("飞书推送：未配置 webhook，仅保存 Markdown", f"飞书推送：{feishu_status}")
        output_path.write_text(markdown, encoding="utf-8")

    return {
        "status": "ok",
        "output_path": str(output_path),
        "fixture": args.fixture,
        "raw_count": raw_count,
        "cleaned_count": len(cleaned),
        "deduped_count": len(deduped),
        "recommended_count": min(len(recommended), args.count),
        "reserve_count": len(reserve),
        "discarded_count": len(discarded),
        "feishu": feishu_status,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the offline GEO topic scout MVP workflow.")
    parser.add_argument("--fixture", choices=("empty", "example", "file"), default="empty")
    parser.add_argument("--input-json", help="Local JSON input used when --fixture file is selected.")
    parser.add_argument("--date", help="Report date in YYYY-MM-DD format. Defaults to today.")
    parser.add_argument("--output", help="Output Markdown path. Defaults to outputs/topic-briefs/YYYY-MM-DD-topic-brief.md.")
    parser.add_argument("--overwrite", action="store_true", help="Allow overwriting the preferred dated output file.")
    parser.add_argument("--count", type=int, default=3, help="Maximum recommended topics to render.")
    parser.add_argument("--max-candidates", type=int, default=20)
    parser.add_argument("--min-common-words", type=int, default=5)
    parser.add_argument("--similarity-threshold", type=float, default=0.45)
    parser.add_argument("--feishu-webhook", help="Optional Feishu webhook. If omitted, only Markdown is saved.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    summary = run(args)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
