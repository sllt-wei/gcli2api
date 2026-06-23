import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path

_STATS_FILE = Path(__file__).parent.parent / "data" / "model_stats.json"
_lock = asyncio.Lock()
_stats = None


def _load():
    if _STATS_FILE.exists():
        try:
            return json.loads(_STATS_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"total": {}, "daily": {}}


def _save(data):
    _STATS_FILE.parent.mkdir(exist_ok=True)
    _STATS_FILE.write_text(json.dumps(data), encoding="utf-8")


async def increment(model_name: str):
    if not model_name:
        return
    global _stats
    async with _lock:
        if _stats is None:
            _stats = _load()
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        _stats["total"][model_name] = _stats["total"].get(model_name, 0) + 1
        if today not in _stats["daily"]:
            _stats["daily"][today] = {}
            days = sorted(_stats["daily"].keys())
            for old in days[:-30]:
                del _stats["daily"][old]
        day = _stats["daily"][today]
        day[model_name] = day.get(model_name, 0) + 1
        _save(_stats)


async def get_stats():
    global _stats
    async with _lock:
        if _stats is None:
            _stats = _load()
        total = dict(_stats["total"])
        daily = {
            day: {"models": dict(models), "total": sum(models.values())}
            for day, models in sorted(_stats["daily"].items(), reverse=True)
        }
    return {
        "total": total,
        "grand_total": sum(total.values()),
        "daily": daily,
    }
