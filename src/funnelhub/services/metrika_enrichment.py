from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from funnelhub.config import Settings
from funnelhub.db.models import LeadUtm

logger = logging.getLogger(__name__)

METRIKA_LOG_FIELDS = (
    "ym:s:visitID,"
    "ym:s:clientID,"
    "ym:s:dateTime,"
    "ym:s:lastDirectSearchPhrase,"
    "ym:s:lastSearchPhrase,"
    "ym:s:UTMTerm"
)


async def fetch_metrika_search_queries(
    *,
    token: str,
    counter_id: str,
    date_from: str,
    date_to: str,
    timeout_seconds: float = 120.0,
) -> dict[str, str]:
    """Requests and downloads raw visits logs from Yandex Metrika Logs API.

    Returns a dict mapping client_id -> search phrase.
    """
    headers = {"Authorization": f"OAuth {token}"}
    client_phrase_map: dict[str, str] = {}

    async with httpx.AsyncClient(timeout=30.0) as client:
        # 1. Create log request
        create_url = (
            f"https://api-metrika.yandex.net/management/v1/counter/{counter_id}/logrequests"
        )
        payload = {
            "date1": date_from,
            "date2": date_to,
            "fields": METRIKA_LOG_FIELDS,
            "source": "visits",
        }
        resp = await client.post(create_url, params=payload, headers=headers)
        if resp.status_code != 200:
            logger.error("Failed to create Metrika log request: %s %s", resp.status_code, resp.text)
            return {}

        log_req = resp.json().get("log_request", {})
        request_id = log_req.get("request_id")
        if not request_id:
            logger.error("No request_id in Metrika log request response: %s", resp.text)
            return {}

        logger.info("Created Metrika log request %s (%s)", request_id, log_req.get("status"))

        status_url = (
            f"https://api-metrika.yandex.net/management/v1/counter/{counter_id}/"
            f"logrequest/{request_id}"
        )
        clean_url = (
            f"https://api-metrika.yandex.net/management/v1/counter/{counter_id}/"
            f"logrequest/{request_id}/clean"
        )

        try:
            # 2. Poll until processed
            start_time = asyncio.get_event_loop().time()
            parts_count = 0
            while True:
                if asyncio.get_event_loop().time() - start_time > timeout_seconds:
                    logger.warning("Timed out waiting for Metrika log request %s", request_id)
                    break

                await asyncio.sleep(2.5)
                status_resp = await client.get(status_url, headers=headers)
                if status_resp.status_code != 200:
                    continue

                status_data = status_resp.json().get("log_request", {})
                current_status = status_data.get("status")
                if current_status == "processed":
                    parts = status_data.get("parts", [])
                    parts_count = len(parts)
                    break
                elif current_status in ("processing_failed", "canceled"):
                    logger.warning(
                        "Metrika log request %s ended with status %s",
                        request_id,
                        current_status,
                    )
                    break

            # 3. Download parts
            for part_num in range(parts_count):
                download_url = (
                    f"https://api-metrika.yandex.net/management/v1/counter/{counter_id}/"
                    f"logrequest/{request_id}/part/{part_num}/download"
                )
                dl_resp = await client.get(download_url, headers=headers)
                if dl_resp.status_code != 200:
                    continue

                tsv_lines = dl_resp.text.strip().splitlines()
                if len(tsv_lines) <= 1:
                    continue

                for line in tsv_lines[1:]:
                    cols = line.split("\t")
                    if len(cols) < 5:
                        continue
                    client_id = cols[1].strip()
                    if not client_id or client_id == "0":
                        continue

                    direct_phrase = cols[3].strip() if len(cols) > 3 else ""
                    search_phrase = cols[4].strip() if len(cols) > 4 else ""

                    resolved_query = ""
                    if direct_phrase and direct_phrase.lower() != "other":
                        resolved_query = direct_phrase
                    elif search_phrase:
                        resolved_query = search_phrase
                    elif direct_phrase.lower() == "other":
                        resolved_query = "РСЯ (Рекламная сеть)"

                    if resolved_query:
                        existing = client_phrase_map.get(client_id)
                        if not existing or existing == "РСЯ (Рекламная сеть)":
                            client_phrase_map[client_id] = resolved_query

        finally:
            # 4. Clean up the log request
            try:
                await client.post(clean_url, headers=headers)
            except Exception as exc:
                logger.debug("Failed to clean up Metrika log request %s: %s", request_id, exc)

    return client_phrase_map


async def enrich_lead_utm_search_queries(
    session: AsyncSession,
    settings: Settings,
    *,
    date_from: str | None = None,
    date_to: str | None = None,
) -> int:
    """Fetches search phrases from Metrika and updates lead_utm rows."""
    if not settings.yandex_metrika_token or not settings.yandex_metrika_counter_id:
        logger.warning("Yandex Metrika integration is not configured.")
        return 0

    now = datetime.now(UTC)
    yesterday_str = (now - timedelta(days=1)).strftime("%Y-%m-%d")
    if not date_from:
        date_from = (now - timedelta(days=60)).strftime("%Y-%m-%d")
    if not date_to or date_to >= now.strftime("%Y-%m-%d"):
        date_to = yesterday_str

    logger.info("Enriching search queries from Metrika for range %s to %s", date_from, date_to)
    phrase_map = await fetch_metrika_search_queries(
        token=settings.yandex_metrika_token,
        counter_id=str(settings.yandex_metrika_counter_id),
        date_from=date_from,
        date_to=date_to,
    )
    if not phrase_map:
        logger.info("No search phrases returned from Metrika.")
        return 0

    logger.info("Retrieved %d client ID phrase mappings from Metrika", len(phrase_map))

    updated_count = 0
    for client_id, search_query in phrase_map.items():
        stmt = (
            update(LeadUtm)
            .where(
                LeadUtm.metrika_client_id == client_id,
                (LeadUtm.search_query.is_(None))
                | (LeadUtm.search_query == "")
                | (LeadUtm.search_query == "РСЯ (Рекламная сеть)"),
            )
            .values(search_query=search_query)
        )
        res = await session.execute(stmt)
        rowcount = int(getattr(res, "rowcount", 0) or 0)
        updated_count += rowcount

    if updated_count > 0:
        await session.flush()
        logger.info("Enriched %d LeadUtm records with search queries", updated_count)

    return updated_count
