import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path

_STATS_FILE = Path(__file__).parent.parent / "data" / "model_stats.json"
_KNOWN_MODES = ("geminicli", "antigravity")
_LEGACY_MODE = "legacy"
_lock = asyncio.Lock()
_stats = None


def _empty_mode_stats():
    return {"total": {}, "daily": {}}


def _empty_stats():
    return {
        "version": 2,
        "modes": {mode: _empty_mode_stats() for mode in _KNOWN_MODES},
    }


def _normalize_count_map(value):
    if not isinstance(value, dict):
        return {}

    normalized = {}
    for model_name, count in value.items():
        try:
            count = int(count)
        except (TypeError, ValueError):
            continue
        if count > 0:
            normalized[str(model_name)] = count
    return normalized


def _normalize_daily_map(value):
    if not isinstance(value, dict):
        return {}

    normalized = {}
    for day, models in value.items():
        if isinstance(models, dict) and isinstance(models.get("models"), dict):
            models = models["models"]
        day_models = _normalize_count_map(models)
        if day_models:
            normalized[str(day)] = day_models
    return normalized


def _ensure_mode(data, mode):
    modes = data.setdefault("modes", {})
    if mode not in modes or not isinstance(modes[mode], dict):
        modes[mode] = _empty_mode_stats()
    modes[mode]["total"] = _normalize_count_map(modes[mode].get("total", {}))
    modes[mode]["daily"] = _normalize_daily_map(modes[mode].get("daily", {}))
    return modes[mode]


def _normalize_mode(mode: str) -> str:
    if not mode:
        return "geminicli"
    mode = str(mode)
    if mode in _KNOWN_MODES:
        return mode
    return "other"


def _normalize_stats(data):
    if not isinstance(data, dict):
        return _empty_stats()

    if isinstance(data.get("modes"), dict):
        normalized = {
            "version": 2,
            "modes": {},
        }
        for mode in _KNOWN_MODES:
            _ensure_mode(normalized, mode)
        for mode, mode_stats in data["modes"].items():
            if not isinstance(mode_stats, dict):
                continue
            normalized["modes"][str(mode)] = {
                "total": _normalize_count_map(mode_stats.get("total", {})),
                "daily": _normalize_daily_map(mode_stats.get("daily", {})),
            }
        return normalized

    normalized = _empty_stats()
    legacy_total = _normalize_count_map(data.get("total", {}))
    legacy_daily = _normalize_daily_map(data.get("daily", {}))
    if legacy_total or legacy_daily:
        normalized["modes"][_LEGACY_MODE] = {
            "total": legacy_total,
            "daily": legacy_daily,
        }
    return normalized


def _load():
    if _STATS_FILE.exists():
        try:
            return _normalize_stats(json.loads(_STATS_FILE.read_text(encoding="utf-8")))
        except Exception:
            pass
    return _empty_stats()


def _save(data):
    _STATS_FILE.parent.mkdir(exist_ok=True)
    _STATS_FILE.write_text(json.dumps(data), encoding="utf-8")


def _trim_daily(days_by_model):
    days = sorted(days_by_model.keys())
    for old in days[:-30]:
        del days_by_model[old]


def _combine_totals(mode_stats_list):
    combined = {}
    for mode_stats in mode_stats_list:
        for model_name, count in mode_stats.get("total", {}).items():
            combined[model_name] = combined.get(model_name, 0) + count
    return combined


def _combine_daily(mode_stats_list):
    combined = {}
    for mode_stats in mode_stats_list:
        for day, models in mode_stats.get("daily", {}).items():
            day_models = combined.setdefault(day, {})
            for model_name, count in models.items():
                day_models[model_name] = day_models.get(model_name, 0) + count
    return combined


def _daily_response(days_by_model):
    return {
        day: {"models": dict(models), "total": sum(models.values())}
        for day, models in sorted(days_by_model.items(), reverse=True)
    }


async def increment(model_name: str, mode: str = "geminicli"):
    if not model_name:
        return
    global _stats
    async with _lock:
        if _stats is None:
            _stats = _load()
        mode = _normalize_mode(mode)
        mode_stats = _ensure_mode(_stats, mode)
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        total = mode_stats["total"]
        total[model_name] = total.get(model_name, 0) + 1
        if today not in mode_stats["daily"]:
            mode_stats["daily"][today] = {}
            _trim_daily(mode_stats["daily"])
        day = mode_stats["daily"][today]
        day[model_name] = day.get(model_name, 0) + 1
        _save(_stats)


async def get_stats():
    global _stats
    async with _lock:
        if _stats is None:
            _stats = _load()
        modes = {
            mode: {
                "total": dict(mode_stats.get("total", {})),
                "grand_total": sum(mode_stats.get("total", {}).values()),
                "daily": _daily_response(mode_stats.get("daily", {})),
            }
            for mode, mode_stats in _stats.get("modes", {}).items()
            if mode in _KNOWN_MODES or mode_stats.get("total") or mode_stats.get("daily")
        }
        mode_stats_list = list(_stats.get("modes", {}).values())
        total = _combine_totals(mode_stats_list)
        daily = _daily_response(_combine_daily(mode_stats_list))
    return {
        "total": total,
        "grand_total": sum(total.values()),
        "daily": daily,
        "modes": modes,
        "mode_totals": {mode: data["grand_total"] for mode, data in modes.items()},
    }
