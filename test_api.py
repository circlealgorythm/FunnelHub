import asyncio

import aiohttp


async def main():
    async with aiohttp.ClientSession() as session:
        # We test the API locally over localhost:8000
        async with session.delete("http://127.0.0.1:8000/api/inbox/database/leads/00000000-0000-0000-0000-000000000000") as resp:
            print("Status:", resp.status)
            print("Response:", await resp.text())

asyncio.run(main())
