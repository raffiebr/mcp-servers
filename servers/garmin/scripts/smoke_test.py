"""End-to-end check from your laptop: OAuth sign-in, list tools, call two of them.

    uv run python scripts/smoke_test.py https://garmin.example.com

A browser opens for Google sign-in; use an account on ALLOWED_EMAILS.
"""

import asyncio
import sys

from fastmcp import Client


async def main(base: str) -> None:
    async with Client(f"{base.rstrip('/')}/mcp", auth="oauth") as client:
        tools = await client.list_tools()
        print(f"{len(tools)} tools:", ", ".join(t.name for t in tools))
        status = await client.call_tool("garmin_status")
        print("garmin_status:", status.data)
        if status.data and status.data.get("connected"):
            summary = await client.call_tool("daily_summary")
            print("daily_summary keys:", list((summary.data or {}).keys())[:10])


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"))
