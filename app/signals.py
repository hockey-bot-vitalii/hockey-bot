import datetime as dt
import json
from typing import List, Dict, Any

from .sources import nhl, khl, vhl

SUPPORTED = {"NHL": nhl, "KHL": khl, "VHL": vhl}

def collect_signals(date: dt.date, leagues: List[str]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for lg in leagues:
        mod = SUPPORTED.get(lg.upper())
        if not mod:
            continue
        out.extend(mod.build_signals(date))
    out.sort(key=lambda x: x.get("confidence", 0), reverse=True)
    return out

def format_signal_message(s: Dict[str, Any]) -> str:
    league = s["league"]
    match = s["match"]
    pick = s["pick"]
    conf = int(s["confidence"])
    why = s.get("why", [])
    risks = s.get("risks", [])
    sources = s.get("sources", [])

    lines = [
        f"🏒 <b>{league}</b>",
        f"<b>{match}</b>",
        "",
        f"<b>Рассмотреть:</b> {pick}",
        f"<b>Оценка:</b> {conf}%",
    ]
    if why:
        lines += ["", "<b>Почему:</b>"] + [f"• {w}" for w in why[:6]]
    if risks:
        lines += ["", "<b>Риски:</b>"] + [f"• {r}" for r in risks[:4]]
    if sources:
        lines += ["", "<b>Источники:</b>"] + [
            f"• {src.get('name','Источник')}: {src.get('url','')}" for src in sources[:5]
        ]
    return "\n".join(lines)

def to_db_payload(s: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "created_at": dt.datetime.utcnow().isoformat(),
        "league": s["league"],
        "game_id": s.get("game_id"),
        "match": s["match"],
        "pick": s["pick"],
        "confidence": int(s["confidence"]),
        "why_json": json.dumps(s.get("why", []), ensure_ascii=False),
        "risks_json": json.dumps(s.get("risks", []), ensure_ascii=False),
        "sources_json": json.dumps(s.get("sources", []), ensure_ascii=False),
    }
