from . import db

def summarize_last(limit: int = 15) -> str:
    rows = db.list_recent_signals(limit=limit)
    if not rows:
        return "Пока нет записей."
    lines = ["📊 <b>Последние сигналы</b>"]
    for r in rows:
        status = r["status"]
        st = "⏳" if status == "PENDING" else ("✅" if status == "WIN" else ("❌" if status == "LOSE" else "⚪️"))
        score = f" — {r['final_score']}" if r.get("final_score") else ""
        lines.append(f"{st} <b>#{r['id']}</b> {r['league']} • {r['match']} • {r['pick']} • {r['confidence']}%{score}")
    return "\n".join(lines)

def week_stats() -> str:
    rows = db.list_recent_signals(limit=200)
    if not rows:
        return "Пока нет статистики."
    win = sum(1 for r in rows if r["status"] == "WIN")
    lose = sum(1 for r in rows if r["status"] == "LOSE")
    pend = sum(1 for r in rows if r["status"] == "PENDING")
    total = win + lose + pend
    return "\n".join([
        "📈 <b>Сводка (последние записи)</b>",
        f"Всего: {total}",
        f"Зашло: {win}",
        f"Не зашло: {lose}",
        f"Ожидают: {pend}",
    ])
