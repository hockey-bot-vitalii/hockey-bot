#!/usr/bin/env python3
import logging
import datetime as dt
from zoneinfo import ZoneInfo
import re

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, ContextTypes

from app.config import get_config
from app import db
from app.signals import collect_signals, format_signal_message, to_db_payload
from app.reports import summarize_last, week_stats
from app.sources import nhl as nhl_source

def parse_leagues(text: str):
    items = [x.strip().upper() for x in text.split(",") if x.strip()]
    ok = []
    for x in items:
        if x in ("NHL","KHL","VHL"):
            ok.append(x)
    return ok

def parse_hhmm(s: str):
    if not re.match(r"^\d{1,2}:\d{2}$", s):
        return None
    hh, mm = s.split(":")
    hh = int(hh); mm = int(mm)
    if hh < 0 or hh > 23 or mm < 0 or mm > 59:
        return None
    return f"{hh:02d}:{mm:02d}"

def get_user_settings(chat_id: int, cfg):
    u = db.get_user(chat_id)
    minc = cfg.default_min_confidence
    leagues = ["NHL"]
    daily_time = cfg.default_daily_time
    if u:
        if u.get("min_confidence") is not None:
            minc = int(u["min_confidence"])
        if u.get("leagues"):
            leagues = [x.strip().upper() for x in u["leagues"].split(",") if x.strip()]
        if u.get("daily_time"):
            daily_time = u["daily_time"]
    return minc, leagues, daily_time

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    db.upsert_user(chat_id, dt.datetime.utcnow().isoformat())
    cfg = context.application.bot_data["cfg"]
    minc, leagues, daily_time = get_user_settings(chat_id, cfg)
    await update.message.reply_text(
        "✅ Готово. Я запомнил этот чат.\n\n"
        "Команды:\n"
        "• /now — сигналы сейчас\n"
        "• /setmin 65 — порог\n"
        "• /settime 10:30 — время ежедневного отчёта\n"
        "• /setleagues NHL,KHL,VHL — лиги\n"
        "• /report — журнал\n"
        "• /week — сводка\n\n"
        f"Текущие: порог {minc}%, лиги {','.join(leagues)}, время {daily_time}",
        disable_web_page_preview=True
    )

async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cfg = context.application.bot_data["cfg"]
    chat_id = update.effective_chat.id
    u = db.get_user(chat_id)
    if not u:
        await update.message.reply_text("Сначала /start")
        return
    minc, leagues, daily_time = get_user_settings(chat_id, cfg)
    await update.message.reply_text(
        f"Настройки:\n• min: {minc}%\n• leagues: {','.join(leagues)}\n• daily: {daily_time} ({cfg.timezone})"
    )

async def cmd_setmin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if not context.args:
        await update.message.reply_text("Пример: /setmin 65")
        return
    try:
        v = int(context.args[0])
        if v < 50 or v > 80:
            raise ValueError
    except ValueError:
        await update.message.reply_text("Порог 50..80. Пример: /setmin 65")
        return
    db.set_min_confidence(chat_id, v)
    await update.message.reply_text(f"Ок. Порог: {v}%")

async def cmd_settime(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if not context.args:
        await update.message.reply_text("Пример: /settime 10:30")
        return
    hhmm = parse_hhmm(context.args[0])
    if not hhmm:
        await update.message.reply_text("Формат HH:MM, например /settime 10:30")
        return
    db.set_daily_time(chat_id, hhmm)
    await update.message.reply_text("Ок. Время сохранено.\n⚠️ Применится при следующем рестарте бота.")

async def cmd_setleagues(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if not context.args:
        await update.message.reply_text("Пример: /setleagues NHL,KHL,VHL")
        return
    leagues = parse_leagues(" ".join(context.args))
    if not leagues:
        await update.message.reply_text("Доступно: NHL,KHL,VHL. Пример: /setleagues NHL,KHL")
        return
    db.set_leagues(chat_id, ",".join(leagues))
    await update.message.reply_text(f"Ок. Лиги: {','.join(leagues)}")

async def send_signals(app: Application, chat_id: int, cfg):
    minc, leagues, _ = get_user_settings(chat_id, cfg)
    today = dt.datetime.now(ZoneInfo(cfg.timezone)).date()
    sigs = collect_signals(today, leagues)
    sigs = [s for s in sigs if int(s.get("confidence", 0)) >= minc]

    if not sigs:
        await app.bot.send_message(chat_id=chat_id, text="Сегодня сигналов нет (по текущим фильтрам).")
        return

    for s in sigs[:5]:
        sid = db.insert_signal(to_db_payload(s))
        msg = format_signal_message(s) + f"\n\n<b>ID записи:</b> #{sid}"
        await app.bot.send_message(chat_id=chat_id, text=msg, parse_mode=ParseMode.HTML, disable_web_page_preview=True)

async def cmd_now(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cfg = context.application.bot_data["cfg"]
    await send_signals(context.application, update.effective_chat.id, cfg)

async def cmd_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(summarize_last(15), parse_mode=ParseMode.HTML, disable_web_page_preview=True)

async def cmd_week(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(week_stats(), parse_mode=ParseMode.HTML, disable_web_page_preview=True)

async def daily_job(context: ContextTypes.DEFAULT_TYPE):
    cfg = context.application.bot_data["cfg"]
    for chat_id in db.get_all_chat_ids():
        try:
            await send_signals(context.application, chat_id, cfg)
        except Exception:
            logging.exception("Failed daily send to %s", chat_id)

async def settle_job(context: ContextTypes.DEFAULT_TYPE):
    pending = db.list_pending_signals()
    for r in pending:
        if r["league"] != "NHL" or not r.get("game_id"):
            continue
        try:
            fin = nhl_source.fetch_final_score(str(r["game_id"]))
            if not fin:
                continue
            status = nhl_source.grade_pick(r["pick"], fin["away_score"], fin["home_score"])
            db.close_signal(r["id"], status, fin["score"])
        except Exception:
            logging.exception("Failed settle signal #%s", r["id"])

def main():
    cfg = get_config()
    logging.basicConfig(
        level=getattr(logging, cfg.log_level, logging.INFO),
        format="%(asctime)s %(levelname)s %(message)s"
    )
    db.init_db()

    if not cfg.bot_token:
        raise SystemExit("BOT_TOKEN не задан. Впиши в .env")

    app = Application.builder().token(cfg.bot_token).build()
    app.bot_data["cfg"] = cfg

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("setmin", cmd_setmin))
    app.add_handler(CommandHandler("settime", cmd_settime))
    app.add_handler(CommandHandler("setleagues", cmd_setleagues))
    app.add_handler(CommandHandler("now", cmd_now))
    app.add_handler(CommandHandler("report", cmd_report))
    app.add_handler(CommandHandler("week", cmd_week))

    tz = ZoneInfo(cfg.timezone)
    hh, mm = [int(x) for x in cfg.default_daily_time.split(":")]
    app.job_queue.run_daily(daily_job, time=dt.time(hh, mm, tzinfo=tz), name="daily_signals")
    app.job_queue.run_repeating(settle_job, interval=30*60, first=60, name="settle_results")

    logging.info("Bot started. TZ=%s daily=%s", cfg.timezone, cfg.default_daily_time)
    app.run_polling(close_loop=False)

if __name__ == "__main__":
    main()
