"""Web scraping tool built on Scrapy selectors + httpx fetch.

Scrapy is used for HTML parsing (Selector, HtmlResponse) rather than a full
CrawlerProcess, which avoids Twisted reactor conflicts inside uvicorn.
"""

from __future__ import annotations

import re
from urllib.parse import urlparse

import httpx
from langchain_core.tools import tool
from scrapy.http import HtmlResponse
from scrapy.selector import Selector

from config import settings

_MAX_BODY_CHARS = 12_000
_MAX_LINKS = 25
_USER_AGENT = "MCP-Agent/1.0 (+https://github.com; scrapy-tool)"


def _normalize_url(url: str) -> str:
    parsed = urlparse(url.strip())
    if parsed.scheme not in ("http", "https"):
        msg = "URL must start with http:// or https://"
        raise ValueError(msg)
    if not parsed.netloc:
        msg = "URL must include a host name"
        raise ValueError(msg)
    return url.strip()


def _extract_text(selector: Selector) -> str:
    for tag in ("script", "style", "noscript", "svg"):
        for node in selector.css(tag):
            node_root = node.root
            parent = node_root.getparent()
            if parent is not None:
                parent.remove(node_root)

    chunks: list[str] = []
    for block in selector.css("h1, h2, h3, h4, h5, h6, p, li, article, main, section"):
        text = " ".join(block.css("::text").getall())
        text = re.sub(r"\s+", " ", text).strip()
        if len(text) >= 2:
            chunks.append(text)

    if not chunks:
        text = " ".join(selector.css("body ::text").getall())
        text = re.sub(r"\s+", " ", text).strip()
        return text

    seen: set[str] = set()
    unique: list[str] = []
    for chunk in chunks:
        key = chunk.lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(chunk)
    return "\n".join(unique)


def _fetch_and_parse(url: str) -> str:
    timeout = httpx.Timeout(settings.TOOL_TIMEOUT_SECONDS)
    headers = {"User-Agent": _USER_AGENT, "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8"}

    with httpx.Client(follow_redirects=True, timeout=timeout, headers=headers) as client:
        response = client.get(url)
        response.raise_for_status()

    content_type = response.headers.get("content-type", "")
    if "html" not in content_type.lower() and "text/" not in content_type.lower():
        return (
            f"URL: {url}\n"
            f"Status: {response.status_code}\n"
            f"Content-Type: {content_type or 'unknown'}\n\n"
            "This response is not HTML. Only web pages can be scraped with this tool."
        )

    html_response = HtmlResponse(url=url, body=response.content, encoding=response.encoding)
    selector = Selector(response=html_response)

    title = selector.css("title::text").get(default="").strip()
    description = selector.css('meta[name="description"]::attr(content)').get(default="").strip()
    text = _extract_text(selector)
    if len(text) > _MAX_BODY_CHARS:
        text = text[:_MAX_BODY_CHARS] + "\n\n[truncated]"

    links: list[str] = []
    for href in selector.css("a::attr(href)").getall():
        href = href.strip()
        if not href or href.startswith(("#", "javascript:", "mailto:")):
            continue
        if href not in links:
            links.append(href)
        if len(links) >= _MAX_LINKS:
            break

    parts = [
        f"URL: {url}",
        f"Status: {response.status_code}",
        f"Title: {title or '(none)'}",
    ]
    if description:
        parts.append(f"Description: {description}")
    parts.append("")
    parts.append("Content:")
    parts.append(text or "(no readable text found)")
    if links:
        parts.append("")
        parts.append("Links (sample):")
        parts.extend(f"- {link}" for link in links)

    return "\n".join(parts)


@tool
def scrape_webpage(url: str) -> str:
    """Fetch a public web page and return its title, description, main text, and sample links.

    Use this when the user asks to read, summarize, or extract information from a URL.
    Only http/https URLs are supported.
    """
    try:
        normalized = _normalize_url(url)
        return _fetch_and_parse(normalized)
    except ValueError as exc:
        return f"Invalid URL: {exc}"
    except httpx.HTTPStatusError as exc:
        return f"HTTP error {exc.response.status_code} fetching {url}"
    except httpx.RequestError as exc:
        return f"Request failed for {url}: {exc}"
    except Exception as exc:  # noqa: BLE001 - surface unexpected scrape failures to the model
        return f"Scrape failed for {url}: {exc}"
