#!/usr/bin/env python3
"""
Enriches VK leads in PostgreSQL with real names and profile data from VK API.
"""
import asyncio
import os
import sys

import asyncpg
import httpx


async def main() -> None:
    token = os.environ.get("VK_GROUP_ACCESS_TOKEN")
    if not token:
        print("[ERROR] VK_GROUP_ACCESS_TOKEN is not set.")
        sys.exit(1)

    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        print("[ERROR] DATABASE_URL is not set.")
        sys.exit(1)

    dsn = db_url.replace("postgresql+asyncpg://", "postgresql://")
    conn = await asyncpg.connect(dsn)

    rows = await conn.fetch("""
        SELECT mi.id as identity_id, mi.lead_id, mi.external_user_id, l.full_name
        FROM messenger_identities mi
        JOIN leads l ON l.id = mi.lead_id
        WHERE mi.channel IN ('vk', 'vk_most')
          AND mi.external_user_id ~ '^[0-9]+$'
    """)
    print(f"[INFO] Found {len(rows)} VK identities to enrich.")

    vk_map: dict[str, list[asyncpg.Record]] = {}
    for r in rows:
        uid = str(r["external_user_id"])
        vk_map.setdefault(uid, []).append(r)

    all_uids = list(vk_map.keys())
    chunk_size = 100
    updated_count = 0

    async with httpx.AsyncClient(timeout=15.0) as client:
        for i in range(0, len(all_uids), chunk_size):
            chunk = all_uids[i : i + chunk_size]
            uids_str = ",".join(chunk)

            try:
                resp = await client.get(
                    "https://api.vk.com/method/users.get",
                    params={
                        "user_ids": uids_str,
                        "fields": "domain,city,country,photo_200",
                        "access_token": token,
                        "v": "5.199",
                    },
                )
                data = resp.json()
                if "error" in data:
                    print(f"[ERROR] VK API error: {data['error']}")
                    continue

                users = data.get("response", [])
                for u in users:
                    uid = str(u.get("id"))
                    first_name = (u.get("first_name") or "").strip()
                    last_name = (u.get("last_name") or "").strip()
                    full_name = f"{first_name} {last_name}".strip()
                    domain = u.get("domain") or None
                    city_dict = u.get("city") or {}
                    city = city_dict.get("title") if isinstance(city_dict, dict) else None
                    country_dict = u.get("country") or {}
                    country = country_dict.get("title") if isinstance(country_dict, dict) else None

                    for record in vk_map.get(uid, []):
                        lead_id = record["lead_id"]
                        identity_id = record["identity_id"]

                        await conn.execute(
                            """
                            UPDATE leads
                            SET first_name = COALESCE(NULLIF($1, ''), first_name),
                                last_name = COALESCE(NULLIF($2, ''), last_name),
                                full_name = COALESCE(NULLIF($3, ''), full_name),
                                city = COALESCE($4, city),
                                country = COALESCE($5, country),
                                updated_at = NOW()
                            WHERE id = $6
                        """,
                            first_name,
                            last_name,
                            full_name,
                            city,
                            country,
                            lead_id,
                        )

                        await conn.execute(
                            """
                            UPDATE messenger_identities
                            SET display_name = COALESCE(NULLIF($1, ''), display_name),
                                username = COALESCE($2, username),
                                updated_at = NOW()
                            WHERE id = $3
                        """,
                            full_name,
                            domain,
                            identity_id,
                        )

                        updated_count += 1

                total_chunks = (len(all_uids) + chunk_size - 1) // chunk_size
                print(f"[PROGRESS] Chunk {i // chunk_size + 1}/{total_chunks} ({len(users)} users)")
                await asyncio.sleep(0.3)
            except Exception as e:
                print(f"[ERROR] Exception during VK request: {e}")

    await conn.close()
    print(f"\n[DONE] Enriched {updated_count} leads/identities with real names from VK API!")


if __name__ == "__main__":
    asyncio.run(main())
