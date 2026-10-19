"""Read-only MCP tools over garminconnect.

Every tool runs the blocking garminconnect call in a worker thread and passes
the result through `compact()` so per-minute series don't flood Claude's context.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Annotated
from zoneinfo import ZoneInfo

import anyio
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from pydantic import Field

from .config import Settings
from .garmin_client import GarminManager, NotConnected

READ_ONLY = {"readOnlyHint": True, "openWorldHint": True}

# Fields kept when listing activities (the raw payload has ~100 keys each).
ACTIVITY_FIELDS = (
    "activityId", "activityName", "startTimeLocal", "activityType", "distance",
    "duration", "movingDuration", "elevationGain", "averageSpeed", "averageHR",
    "maxHR", "calories", "aerobicTrainingEffect", "anaerobicTrainingEffect",
    "trainingEffectLabel", "activityTrainingLoad", "avgPower", "normPower",
    "averageRunningCadenceInStepsPerMinute", "vO2MaxValue",
)

# Escape hatch: any read-only garminconnect method, but nothing that writes.
BLOCKED_PREFIXES = ("set_", "add_", "delete_", "upload_", "create_", "schedule_", "update_", "logout", "login")

DateStr = Annotated[str | None, Field(description="ISO date YYYY-MM-DD. Defaults to today in the user's timezone.")]


def compact(obj: Any, max_list: int = 48) -> Any:
    """Recursively shorten long lists, keeping a few items from each end."""
    if isinstance(obj, dict):
        return {k: compact(v, max_list) for k, v in obj.items()}
    if isinstance(obj, list):
        if len(obj) > max_list:
            return {
                "_truncated": True,
                "count": len(obj),
                "first": [compact(x, max_list) for x in obj[:3]],
                "last": [compact(x, max_list) for x in obj[-3:]],
            }
        return [compact(x, max_list) for x in obj]
    return obj


def slim_activity(a: dict[str, Any]) -> dict[str, Any]:
    out = {k: a.get(k) for k in ACTIVITY_FIELDS if a.get(k) is not None}
    if isinstance(out.get("activityType"), dict):
        out["activityType"] = out["activityType"].get("typeKey")
    return out


def register_tools(mcp: FastMCP, garmin: GarminManager, settings: Settings) -> None:
    tz = ZoneInfo(settings.timezone)
    setup_url = f"{settings.base_url}/setup"

    def today() -> str:
        return datetime.now(tz).date().isoformat()

    def resolve(d: str | None) -> str:
        if not d:
            return today()
        try:
            return date.fromisoformat(d).isoformat()
        except ValueError as exc:
            raise ToolError(f"'{d}' is not a valid date; use YYYY-MM-DD.") from exc

    async def call(method: str, *args: Any, **kwargs: Any) -> Any:
        try:
            return await anyio.to_thread.run_sync(lambda: garmin.call(method, *args, **kwargs))
        except NotConnected as exc:
            raise ToolError(f"{exc} The account owner needs to connect Garmin at {setup_url}") from exc
        except AttributeError as exc:
            raise ToolError(f"This garminconnect version has no method '{method}'.") from exc

    @mcp.tool(annotations=READ_ONLY)
    async def garmin_status() -> dict:
        """Check whether Garmin is connected and whose account it is."""
        if not garmin.has_tokens():
            return {"connected": False, "setup_url": setup_url}
        name = await call("get_full_name")
        return {"connected": True, "account_name": name, "today": today(), "timezone": settings.timezone}

    @mcp.tool(annotations=READ_ONLY)
    async def daily_summary(day: DateStr = None) -> dict:
        """Steps, calories, distance, floors, intensity minutes, resting HR and stress for one day."""
        return compact(await call("get_user_summary", resolve(day)))

    @mcp.tool(annotations=READ_ONLY)
    async def sleep(day: DateStr = None) -> dict:
        """Sleep for the night ending on `day`: duration, stages, sleep score, overnight HRV and SpO2."""
        return compact(await call("get_sleep_data", resolve(day)))

    @mcp.tool(annotations=READ_ONLY)
    async def heart_rate(day: DateStr = None) -> dict:
        """Resting, min and max heart rate for a day (intraday samples are truncated)."""
        return compact(await call("get_heart_rates", resolve(day)))

    @mcp.tool(annotations=READ_ONLY)
    async def hrv(day: DateStr = None) -> dict:
        """Overnight HRV summary, weekly average and baseline status."""
        return compact(await call("get_hrv_data", resolve(day)) or {})

    @mcp.tool(annotations=READ_ONLY)
    async def stress(day: DateStr = None) -> dict:
        """Average and max stress for a day plus time in each stress band."""
        return compact(await call("get_stress_data", resolve(day)))

    @mcp.tool(annotations=READ_ONLY)
    async def body_battery(
        start_day: DateStr = None,
        end_day: Annotated[str | None, Field(description="ISO date; defaults to start_day.")] = None,
    ) -> list | dict:
        """Body Battery charged/drained per day over a date range (max 31 days)."""
        start = resolve(start_day)
        end = resolve(end_day or start)
        if (date.fromisoformat(end) - date.fromisoformat(start)).days > 31:
            raise ToolError("Keep the range to 31 days or fewer.")
        return compact(await call("get_body_battery", start, end))

    @mcp.tool(annotations=READ_ONLY)
    async def training_readiness(day: DateStr = None) -> list | dict:
        """Training readiness score and its contributing factors."""
        return compact(await call("get_training_readiness", resolve(day)))

    @mcp.tool(annotations=READ_ONLY)
    async def training_status(day: DateStr = None) -> dict:
        """Training status, acute/chronic load and load focus."""
        return compact(await call("get_training_status", resolve(day)))

    @mcp.tool(annotations=READ_ONLY)
    async def fitness_metrics(day: DateStr = None) -> list | dict:
        """VO2 max (running/cycling) and fitness age."""
        return compact(await call("get_max_metrics", resolve(day)))

    @mcp.tool(annotations=READ_ONLY)
    async def race_predictions() -> list | dict:
        """Predicted 5K, 10K, half and full marathon times."""
        return compact(await call("get_race_predictions"))

    @mcp.tool(annotations=READ_ONLY)
    async def recent_activities(
        limit: Annotated[int, Field(ge=1, le=50)] = 10,
        offset: Annotated[int, Field(ge=0)] = 0,
    ) -> list[dict]:
        """Most recent activities, newest first, with distance, pace, HR, load and training effect."""
        acts = await call("get_activities", offset, limit)
        return [slim_activity(a) for a in acts or []]

    @mcp.tool(annotations=READ_ONLY)
    async def activities_between(
        start_day: Annotated[str, Field(description="ISO date YYYY-MM-DD")],
        end_day: Annotated[str, Field(description="ISO date YYYY-MM-DD")],
        activity_type: Annotated[str | None, Field(description="e.g. running, cycling, swimming, strength_training")] = None,
    ) -> list[dict]:
        """All activities in a date range, optionally filtered by type."""
        acts = await call("get_activities_by_date", resolve(start_day), resolve(end_day), activity_type)
        return [slim_activity(a) for a in acts or []]

    @mcp.tool(annotations=READ_ONLY)
    async def activity_details(activity_id: int) -> dict:
        """Full summary and lap splits for one activity (use an id from recent_activities)."""
        summary = await call("get_activity", str(activity_id))
        splits = await call("get_activity_splits", str(activity_id))
        return {"summary": compact(summary), "splits": compact(splits, max_list=60)}

    @mcp.tool(annotations=READ_ONLY)
    async def body_composition(
        start_day: DateStr = None,
        end_day: Annotated[str | None, Field(description="ISO date; defaults to start_day.")] = None,
    ) -> dict:
        """Weight, BMI and body fat entries over a date range."""
        start = resolve(start_day)
        return compact(await call("get_body_composition", start, resolve(end_day or start)))

    @mcp.tool(annotations=READ_ONLY)
    async def query_garmin(
        method: Annotated[str, Field(description="A read-only garminconnect method name starting with get_, e.g. get_spo2_data")],
        args: Annotated[list[Any] | None, Field(description="Positional arguments, e.g. ['2026-10-18']")] = None,
    ) -> Any:
        """Advanced: call any read-only garminconnect `get_*` method not covered by the other tools."""
        if not method.startswith("get_") or method.startswith(BLOCKED_PREFIXES):
            raise ToolError("Only read-only get_* methods are allowed.")
        return compact(await call(method, *(args or [])))
