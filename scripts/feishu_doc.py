"""
Feishu/Lark cloud document publisher.

This module uses tenant_access_token and the Docx v1 APIs. Credentials are read
from environment variables or CLI arguments by the caller; secrets must not be
written to repository files.
"""

from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any


FEISHU_API_BASE = "https://open.feishu.cn/open-apis"


@dataclass(frozen=True)
class FeishuDocConfig:
    app_id: str
    app_secret: str
    folder_token: str = ""
    doc_base_url: str = ""
    timeout: int = 30

    @classmethod
    def from_sources(
        cls,
        *,
        app_id: str | None = None,
        app_secret: str | None = None,
        folder_token: str | None = None,
        doc_base_url: str | None = None,
        timeout: int | None = None,
    ) -> "FeishuDocConfig":
        return cls(
            app_id=app_id or os.environ.get("FEISHU_APP_ID", ""),
            app_secret=app_secret or os.environ.get("FEISHU_APP_SECRET", ""),
            folder_token=folder_token or os.environ.get("FEISHU_FOLDER_TOKEN", ""),
            doc_base_url=(doc_base_url or os.environ.get("FEISHU_DOC_BASE_URL", "")).rstrip("/"),
            timeout=timeout or int(os.environ.get("FEISHU_DOC_TIMEOUT", "30")),
        )

    def missing_reason(self) -> str:
        if not self.app_id:
            return "feishu_app_id_missing"
        if not self.app_secret:
            return "feishu_app_secret_missing"
        return ""


@dataclass(frozen=True)
class FeishuDocResult:
    ok: bool
    document_id: str = ""
    url: str = ""
    title: str = ""
    warning: str = ""
    error: str = ""
    raw: dict[str, Any] | None = None


class FeishuDocClient:
    def __init__(self, config: FeishuDocConfig):
        self.config = config
        self._tenant_access_token = ""

    def request_json(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        auth: bool = True,
    ) -> dict[str, Any]:
        headers = {"Content-Type": "application/json; charset=utf-8"}
        if auth:
            headers["Authorization"] = f"Bearer {self.tenant_access_token()}"

        data = json.dumps(payload or {}, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            f"{FEISHU_API_BASE}{path}",
            data=data if method.upper() != "GET" else None,
            headers=headers,
            method=method.upper(),
        )
        try:
            with urllib.request.urlopen(request, timeout=self.config.timeout) as response:
                body = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"http_{exc.code}: {detail[:800]}") from exc
        except Exception as exc:
            raise RuntimeError(str(exc)) from exc

        try:
            parsed = json.loads(body)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"invalid_json_response: {body[:500]}") from exc

        if parsed.get("code") not in (0, None):
            raise RuntimeError(json.dumps(parsed, ensure_ascii=False)[:1000])
        return parsed

    def tenant_access_token(self) -> str:
        if self._tenant_access_token:
            return self._tenant_access_token

        missing = self.config.missing_reason()
        if missing:
            raise RuntimeError(missing)

        response = self.request_json(
            "POST",
            "/auth/v3/tenant_access_token/internal",
            {
                "app_id": self.config.app_id,
                "app_secret": self.config.app_secret,
            },
            auth=False,
        )
        token = response.get("tenant_access_token", "")
        if not token:
            raise RuntimeError("tenant_access_token_missing")
        self._tenant_access_token = token
        return token

    def create_document(self, title: str) -> dict[str, Any]:
        payload: dict[str, Any] = {"title": title[:800] or "模力指数选题日报"}
        if self.config.folder_token:
            payload["folder_token"] = self.config.folder_token
        response = self.request_json("POST", "/docx/v1/documents", payload)
        return response.get("data", {}).get("document", {})

    def document_url(self, document_id: str) -> str:
        if not document_id:
            return ""
        if self.config.doc_base_url:
            return f"{self.config.doc_base_url}/{document_id}"
        return ""

    def append_blocks(self, document_id: str, blocks: list[dict[str, Any]]) -> str:
        if not blocks:
            return ""

        warnings: list[str] = []
        index = 0
        for chunk in chunks(blocks, 40):
            payload = {"index": index, "children": chunk}
            try:
                self.request_json(
                    "POST",
                    f"/docx/v1/documents/{document_id}/blocks/{document_id}/children",
                    payload,
                )
                index += len(chunk)
                time.sleep(0.35)
            except RuntimeError as exc:
                warnings.append(str(exc))
                break
        return "；".join(warnings)

    def append_plain_text(self, document_id: str, markdown: str) -> str:
        lines = markdown_to_plain_doc_lines(markdown)
        return self.append_blocks(document_id, [text_block(line) for line in lines])

    def publish_blocks(self, title: str, blocks: list[dict[str, Any]]) -> FeishuDocResult:
        try:
            document = self.create_document(title)
            document_id = document.get("document_id", "")
            if not document_id:
                return FeishuDocResult(ok=False, error="document_id_missing", raw=document)

            warning = self.append_blocks(document_id, blocks)
            if warning and any(block.get("block_type") != 2 for block in blocks):
                retry_warning = self.append_blocks(document_id, [as_plain_text_block(block) for block in blocks])
                warning = f"{warning}；已回退为普通文本重试：{retry_warning}" if retry_warning else "标题块写入失败，已回退为普通文本"

            url = self.document_url(document_id)
            if not url:
                missing_url = "FEISHU_DOC_BASE_URL 未配置，已创建文档但无法拼出可点击链接"
                warning = f"{warning}；{missing_url}" if warning else missing_url

            return FeishuDocResult(
                ok=True,
                document_id=document_id,
                url=url,
                title=document.get("title", title),
                warning=warning,
                raw=document,
            )
        except RuntimeError as exc:
            return FeishuDocResult(ok=False, error=str(exc))

    def publish_markdown(self, title: str, markdown: str) -> FeishuDocResult:
        return self.publish_blocks(title, [text_block(line) for line in markdown_to_plain_doc_lines(markdown)])


def chunks(items: list[str], size: int):
    for index in range(0, len(items), size):
        yield items[index : index + size]


def markdown_to_plain_doc_lines(markdown: str, limit: int = 180) -> list[str]:
    lines: list[str] = []
    for raw in markdown.splitlines():
        line = raw.strip()
        if not line:
            continue
        if re.fullmatch(r"-{3,}", line):
            lines.append("————————")
            continue
        if re.fullmatch(r"\|?\s*:?-+:?\s*(\|\s*:?-+:?\s*)+\|?", line):
            continue
        line = line.strip("|")
        line = re.sub(r"\s*\|\s*", "  |  ", line)
        line = re.sub(r"^#{1,6}\s*", "", line)
        line = re.sub(r"^\d+\.\s*", "", line)
        line = re.sub(r"^-\s*", "· ", line)
        line = re.sub(r"\*\*(.+?)\*\*", r"\1", line)
        line = re.sub(r"`([^`]+)`", r"\1", line)
        line = re.sub(r"\s+", " ", line).strip()
        if not line:
            continue
        if len(line) <= limit:
            lines.append(line)
            continue
        for start in range(0, len(line), limit):
            lines.append(line[start : start + limit])
    return lines


def text_block(content: str) -> dict[str, Any]:
    return {
        "block_type": 2,
        "text": {
            "elements": [
                {
                    "text_run": {
                        "content": content,
                        "text_element_style": {},
                    }
                }
            ],
            "style": {},
        },
    }


def heading_block(content: str, level: int = 2) -> dict[str, Any]:
    level = max(1, min(9, level))
    return {
        "block_type": 2 + level,
        f"heading{level}": {
            "elements": [
                {
                    "text_run": {
                        "content": content,
                        "text_element_style": {},
                    }
                }
            ],
            "style": {},
        },
    }


def as_plain_text_block(block: dict[str, Any]) -> dict[str, Any]:
    text = ""
    try:
        rich_text = block.get("text") or next(
            (value for key, value in block.items() if key.startswith("heading") and isinstance(value, dict)),
            {},
        )
        elements = rich_text.get("elements", [])
        text = "".join(
            element.get("text_run", {}).get("content", "")
            for element in elements
        )
    except Exception:
        text = str(block)
    return text_block(text)
