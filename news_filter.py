import requests
from datetime import datetime, timedelta, timezone

FF_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"

def get_upcoming_events(minutes_before=30, minutes_after=30):
    """Return list event high impact USD yang dekat dengan sekarang."""
    try:
        r = requests.get(FF_URL, timeout=10)
        r.raise_for_status()
        events = r.json()
    except Exception as e:
        return {"error": str(e), "events": [], "has_high_impact": False}

    now_utc = datetime.now(timezone.utc)
    window_start = now_utc - timedelta(minutes=minutes_after)
    window_end = now_utc + timedelta(minutes=minutes_before)

    upcoming = []
    for e in events:
        if e.get("impact") != "High":
            continue
        if e.get("country") != "USD":
            continue
        try:
            dt = datetime.fromisoformat(e["date"].replace("Z", "+00:00"))
        except Exception:
            continue
        if window_start <= dt <= window_end:
            upcoming.append({
                "title": e.get("title", "?"),
                "time": dt.astimezone(timezone.utc).strftime("%H:%M UTC"),
                "impact": e.get("impact"),
            })

    return {
        "events": upcoming,
        "has_high_impact": len(upcoming) > 0,
    }
