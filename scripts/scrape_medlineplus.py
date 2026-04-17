"""
MedlinePlus scraper for MedInsight Stage 2.

Fetches lab test pages, extracts descriptions and range text, saves raw .txt
files to data/knowledge_base/medlineplus/, and upserts rows into lab_references.

Usage:
    python scripts/scrape_medlineplus.py
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import httpx
from bs4 import BeautifulSoup
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

import app.models  # noqa: F401 — registers all ORM classes
from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.core.logging import get_logger
from app.models.lab_reference import LabReference

log = get_logger(__name__)

_BASE_URL = "https://medlineplus.gov/lab-tests/"
_OUTPUT_DIR = _ROOT / "data" / "knowledge_base" / "medlineplus"
_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def _extract_description(soup: BeautifulSoup) -> str:
    """
    Extract the actual medical description from a MedlinePlus page.

    Tries three selectors in order before falling back to a heuristic scan:
    1. <div id="topic-summary"> or <section id="summary"> — first <p> inside
    2. First <p> inside <div class="main-content"> or <article>
    3. First <p> with >100 chars that contains no government/cookie banner text
    """
    _BANNER_WORDS = {"government", "official", "website", ".gov", "cookie"}

    # Strategy 1 — primary content containers
    for selector in (
        {"id": "topic-summary"},
        {"id": "summary"},
    ):
        container = soup.find(["div", "section"], selector)
        if container:
            p = container.find("p")
            if p:
                text = p.get_text(strip=True)
                if len(text) > 60:
                    return text

    # Strategy 2 — wider content area
    for selector in (
        {"class": "main-content"},
        "article",
    ):
        container = (
            soup.find("div", selector)
            if isinstance(selector, dict)
            else soup.find(selector)
        )
        if container:
            p = container.find("p")
            if p:
                text = p.get_text(strip=True)
                if len(text) > 60:
                    return text

    # Strategy 3 — heuristic fallback: first long <p> not from the cookie banner
    for tag in soup.find_all("p"):
        text = tag.get_text(strip=True)
        lower = text.lower()
        if len(text) > 100 and not any(w in lower for w in _BANNER_WORDS):
            return text

    return ""


def _extract_page(html: str) -> dict[str, str]:
    """
    Parse a MedlinePlus lab test page and return key text sections.

    Extracts title, description paragraph, normal results text, and
    abnormal results text. Falls back gracefully if sections are missing.
    """
    soup = BeautifulSoup(html, "html.parser")

    title = ""
    h1 = soup.find("h1")
    if h1:
        title = h1.get_text(strip=True)

    description = _extract_description(soup)

    normal_range_text = ""
    what_abnormal_text = ""
    for heading in soup.find_all(["h2", "h3"]):
        heading_lower = heading.get_text(strip=True).lower()
        sibling = heading.find_next_sibling()
        section_text = sibling.get_text(strip=True) if sibling else ""
        if "normal" in heading_lower and "result" in heading_lower:
            normal_range_text = section_text
        elif "abnormal" in heading_lower:
            what_abnormal_text = section_text

    full_text = soup.get_text(separator="\n", strip=True)

    return {
        "title": title,
        "description": description,
        "normal_range": normal_range_text,
        "what_abnormal": what_abnormal_text,
        "full_text": full_text,
    }


async def _upsert_reference(
    session: AsyncSession,
    test_name: str,
    source_url: str,
    description: str,
    raw_content: str,
) -> None:
    """Insert or update a lab_references row — safe to call on every scrape run."""
    stmt = pg_insert(LabReference).values(
        test_name=test_name,
        source_url=source_url,
        description=description or None,
        raw_content=raw_content[:5000] if raw_content else None,
        range_low=None,
        range_high=None,
    )
    stmt = stmt.on_conflict_do_update(
        constraint="uq_lab_reference_test_name",
        set_={
            "source_url": stmt.excluded.source_url,
            "description": stmt.excluded.description,
            "raw_content": stmt.excluded.raw_content,
        },
    )
    await session.execute(stmt)
    await session.commit()


async def scrape() -> None:
    """
    Main scrape loop — iterates over every test in settings.medlineplus_slugs.

    Each test gets a 1-second delay after its request to avoid hammering
    MedlinePlus. A single test failure never aborts the full run.
    """
    slugs: dict[str, str] = settings.medlineplus_slugs
    total = len(slugs)
    log.info("scrape_started", total_tests=total)

    success = 0
    skipped = 0

    async with httpx.AsyncClient(
        timeout=10,
        follow_redirects=True,
        headers={"User-Agent": "MedInsight/1.0 academic research bot"},
    ) as client:
        async with AsyncSessionLocal() as session:
            for test_name, slug in slugs.items():
                url = f"{_BASE_URL}{slug}/"
                try:
                    response = await client.get(url)

                    if response.status_code == 404:
                        log.warning(
                            "test_skipped",
                            reason="404_not_found",
                            test_name=test_name,
                            url=url,
                        )
                        skipped += 1
                        await asyncio.sleep(1)
                        continue

                    response.raise_for_status()

                    parsed = _extract_page(response.text)

                    out_file = _OUTPUT_DIR / f"{slug}.txt"
                    out_file.write_text(
                        f"Test: {test_name}\n"
                        f"URL: {url}\n\n"
                        f"Title: {parsed['title']}\n\n"
                        f"Description:\n{parsed['description']}\n\n"
                        f"Normal Range:\n{parsed['normal_range']}\n\n"
                        f"Abnormal Results:\n{parsed['what_abnormal']}\n\n"
                        f"Full Content:\n{parsed['full_text']}",
                        encoding="utf-8",
                    )

                    await _upsert_reference(
                        session=session,
                        test_name=test_name,
                        source_url=url,
                        description=parsed["description"],
                        raw_content=parsed["full_text"],
                    )

                    log.info("test_scraped", test_name=test_name, url=url)
                    success += 1

                except httpx.HTTPStatusError as exc:
                    log.error(
                        "test_skipped",
                        reason=f"http_{exc.response.status_code}",
                        test_name=test_name,
                        url=url,
                    )
                    skipped += 1

                except Exception as exc:
                    log.warning(
                        "test_skipped",
                        reason="parse_or_network_error",
                        test_name=test_name,
                        error=str(exc),
                    )
                    skipped += 1

                await asyncio.sleep(1)

    log.info("scrape_complete", success=success, skipped=skipped, total=total)


if __name__ == "__main__":
    asyncio.run(scrape())
