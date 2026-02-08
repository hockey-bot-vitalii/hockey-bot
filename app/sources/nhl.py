import datetime as dt
from dataclasses import dataclass
from typing import List, Dict, Any, Optional
import requests

SCHEDULE_URL = "https://api-web.nhle.com/v1/schedule/{date}"
STANDINGS_URL = "https://api-web.nhle.com/v1/standings/{date}"
GAMECENTER_URL = "https://api-web.nhle.com/v1/gamecenter/{game_id}/landing"

def _get_json(url: str, timeout: int = 20) -> Dict[str, Any]:
    r = requests.get(url, timeout=timeout)
    r.raise_for_status()
    return r.json()

@dataclass
class Match:
    game_id: str
    start_utc: str
    home: str
    away: str

def fetch_today_matches(date: dt.date) -> List[Match]:
    data = _get_json(SCHEDULE_URL.format(date=date.isoformat()))
    out: List[Match] = []
    for day in data.get("gameWeek", []):
        for game in day.get("games", []):
            home = game.get("homeTeam", {}).get("name", {}).get("default") or game.get("homeTeam", {}).get("placeName", {}).get("default")
            away = game.get("awayTeam", {}).get("name", {}).get("default") or game.get("awayTeam", {}).get("placeName", {}).get("default")
            if not home or not away:
                continue
            out.append(Match(
                game_id=str(game.get("id")),
                start_utc=game.get("startTimeUTC",""),
                home=home,
                away=away
            ))
    return out

def fetch_standings_map(date: dt.date) -> Dict[str, Dict[str, Any]]:
    data = _get_json(STANDINGS_URL.format(date=date.isoformat()))
    mp: Dict[str, Dict[str, Any]] = {}
    for row in data.get("standings", []):
        name = row.get("teamName", {}).get("default")
        if name:
            mp[name] = row
    return mp

def _point_pct(row: Dict[str, Any]) -> Optional[float]:
    v = row.get("pointPctg")
    try:
        return float(v)
    except Exception:
        return None

def build_signals(date: dt.date) -> List[Dict[str, Any]]:
    matches = fetch_today_matches(date)
    standings = fetch_standings_map(date)
    signals: List[Dict[str, Any]] = []

    for m in matches:
        h = standings.get(m.home)
        a = standings.get(m.away)
        if not h or not a:
            continue
        hp = _point_pct(h)
        ap = _point_pct(a)
        if hp is None or ap is None:
            continue

        diff = hp - ap
        # MVP: берем только явный перекос
        if abs(diff) < 0.08:
            continue

        conf = max(50, min(80, int(55 + diff * 125)))
        if diff >= 0.08:
            pick = "1X (хозяева не проиграют)"
            stronger = m.home
        else:
            pick = "X2 (гости не проиграют)"
            stronger = m.away

        why = [
            f"По таблице {stronger} заметно сильнее по % очков: {m.home} {hp:.3f} vs {m.away} {ap:.3f}",
            "База (MVP): без учёта вратарей/травм/формы. Подключим источники следующим шагом."
        ]
        risks = [
            "Ранний гол/удаления могут сломать сценарий.",
            "Хоккей вариативен — это не гарантия."
        ]
        sources = [
            {"name":"NHL schedule API", "url": SCHEDULE_URL.format(date=date.isoformat())},
            {"name":"NHL standings API", "url": STANDINGS_URL.format(date=date.isoformat())},
        ]

        signals.append({
            "league": "NHL",
            "game_id": m.game_id,
            "match": f"{m.away} — {m.home}",
            "pick": pick,
            "confidence": conf,
            "why": why,
            "risks": risks,
            "sources": sources,
        })

    signals.sort(key=lambda x: x.get("confidence", 0), reverse=True)
    return signals

def fetch_final_score(game_id: str) -> Optional[Dict[str, Any]]:
    data = _get_json(GAMECENTER_URL.format(game_id=game_id))
    if data.get("gameState") != "FINAL":
        return None
    home = data.get("homeTeam", {}).get("name", {}).get("default")
    away = data.get("awayTeam", {}).get("name", {}).get("default")
    hs = data.get("homeTeam", {}).get("score")
    as_ = data.get("awayTeam", {}).get("score")
    if home and away and hs is not None and as_ is not None:
        return {"score": f"{away} {as_} — {home} {hs}", "away_score": int(as_), "home_score": int(hs)}
    return None

def grade_pick(pick: str, away_score: int, home_score: int) -> str:
    if "1X" in pick:
        return "WIN" if home_score >= away_score else "LOSE"
    if "X2" in pick:
        return "WIN" if away_score >= home_score else "LOSE"
    return "VOID"
