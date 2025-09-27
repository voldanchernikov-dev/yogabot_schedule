import os
import logging
from datetime import datetime, date
from typing import List
import gspread
from google.oauth2.service_account import Credentials
from telegram.ext import Application, CommandHandler
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import pytz

# --- Logging ---
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# --- Config ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
GROUP_CHAT_ID = int(os.getenv("GROUP_CHAT_ID", "0"))
ADMINS = [int(x.strip()) for x in os.getenv("ADMINS", "").split(",") if x.strip()]

TZ = pytz.timezone("Europe/Moscow")

SHEET_URL = "https://docs.google.com/spreadsheets/d/1Z39dIQrgdhSoWdD5AE9jIMtfn1ahTxl-femjqxyER0Q/edit#gid=1614712337"
SHEET_NAME = "Лист1"

# --- Google Sheets ---
def open_sheet():
    creds = Credentials.from_service_account_file(
        "creds.json",
        scopes=["https://www.googleapis.com/auth/spreadsheets"]
    )
    client = gspread.authorize(creds)
    return client.open_by_url(SHEET_URL).worksheet(SHEET_NAME)


def parse_date_from_cell(value: str):
    try:
        return datetime.strptime(value.strip(), "%d.%m.%Y").date()
    except Exception:
        return None


def find_todays_items(ws) -> List[str]:
    today = datetime.now(TZ).date()
    records = ws.get_all_records()
    results = []
    for row in records:
        keys = {k.strip().lower(): k for k in row.keys()}
        d_key, n_key = None, None
        for k in keys:
            if "дата" in k or k.startswith("c"):
                d_key = keys[k]
            if "стоимость" in k or k.startswith("n"):
                n_key = keys[k]
        if not d_key or not n_key:
            continue

        d_val = row.get(d_key)
        n_val = row.get(n_key)

        parsed = None
        if isinstance(d_val, str):
            parsed = parse_date_from_cell(d_val)
        elif isinstance(d_val, (int, float)):
            try:
                parsed = date.fromordinal(date(1900, 1, 1).toordinal() + int(d_val) - 2)
            except Exception:
                parsed = None

        if parsed == today and n_val:
            results.append(str(n_val))
    return results


# --- Messages ---
async def send_morning_message(app, dry=False):
    if not GROUP_CHAT_ID:
        return
    try:
        ws = open_sheet()
        items = find_todays_items(ws)
        if not items:
            logger.info("⏭ Занятий нет — утреннее сообщение не отправлено.")
            return

        text = (
            "☀️ Всем доброго дня!) Записываемся на занятия:\n"
            "https://docs.google.com/spreadsheets/d/1Z39dIQrgdhSoWdD5AE9jIMtfn1ahTxl-femjqxyER0Q/edit#gid=1614712337"
        )
        if dry:
            logger.info("Dry run morning message:\n%s", text)
            return
        await app.bot.send_message(chat_id=GROUP_CHAT_ID, text=text)
        logger.info("✅ Отправлено утреннее сообщение.")
    except Exception as e:
        logger.exception("❌ Ошибка при отправке утреннего сообщения: %s", e)


async def send_evening_message(app, dry=False):
    if not GROUP_CHAT_ID:
        return
    try:
        ws = open_sheet()
        items = find_todays_items(ws)
        if not items:
            logger.info("⏭ Занятий нет — вечернее сообщение не отправлено.")
            return
        for it in items:
            text = f"Подводим итоги — по {it}р. Приносите наличными до конца недели."
            if dry:
                logger.info("Dry run evening message:\n%s", text)
                continue
            await app.bot.send_message(chat_id=GROUP_CHAT_ID, text=text)
            logger.info("✅ Отправлено вечернее сообщение: %s", it)
    except Exception as e:
        logger.exception("❌ Ошибка при отправке вечернего сообщения: %s", e)


# --- Commands ---
async def ping(update, context):
    if update.effective_chat.type != "private":
        return
    if update.effective_user.id not in ADMINS:
        return
    await update.message.reply_text(
        "Бот живой.\n"
        "Следующие запланированные отправки:\n"
        " - 11:00 (утро)\n"
        " - 18:00 (вечер)\n"
        " - 00:00 (рестарт без сообщений)"
    )


# --- Scheduler jobs ---
def schedule_jobs(scheduler: AsyncIOScheduler, app):
    tz = TZ

    scheduler.add_job(send_morning_message, "cron", hour=12, minute=55, timezone=tz, args=[app], id="notify_11")
    scheduler.add_job(send_evening_message, "cron", hour=12, minute=56, timezone=tz, args=[app], id="notify_18")

    def restart_now():
        logger.info("⏰ 00:00 — сообщение в чат НЕ отправляется. Выполняем рестарт бота...")
        os._exit(0)

    scheduler.add_job(restart_now, "cron", hour=0, minute=0, timezone=tz, id="restart_midnight")


# --- Main ---
def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN not set")

    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("ping", ping))

    scheduler = AsyncIOScheduler()
    schedule_jobs(scheduler, app)
    scheduler.start()

    logger.info("🚀 Бот запущен и слушает события...")
    app.run_polling()


if __name__ == "__main__":
    main()
