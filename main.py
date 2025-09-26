import os
import json
import logging
from datetime import datetime
import pytz

import gspread
from google.oauth2.service_account import Credentials
from telegram import Bot
from telegram.ext import Application, CommandHandler
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# Логирование
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Конфиги ---
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID")
GROUP_CHAT_ID = int(os.getenv("GROUP_CHAT_ID", "0"))

SERVICE_ACCOUNT_FILE = os.getenv("SERVICE_ACCOUNT_FILE")
GOOGLE_CREDENTIALS = os.getenv("GOOGLE_CREDENTIALS")

ADMINS = os.getenv("ADMINS", "").split(",")  # список админов через запятую

tz = pytz.timezone("Europe/Moscow")
bot = Bot(token=BOT_TOKEN)

# --- Google Sheets ---
def get_gspread_client():
    if GOOGLE_CREDENTIALS:
        creds_dict = json.loads(GOOGLE_CREDENTIALS)
        creds = Credentials.from_service_account_info(creds_dict, scopes=[
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ])
    elif SERVICE_ACCOUNT_FILE and os.path.exists(SERVICE_ACCOUNT_FILE):
        creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=[
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ])
    else:
        raise RuntimeError("Нет данных для Google API")
    return gspread.authorize(creds)

def check_schedule():
    client = get_gspread_client()
    sheet = client.open_by_key(SPREADSHEET_ID).sheet1

    today = datetime.now(tz).strftime("%d.%m.%Y")

    dates = sheet.col_values(1)  # допустим, даты в 1-й колонке
    values = sheet.col_values(2) # суммы в 2-й

    for i, d in enumerate(dates):
        if d.strip() == today:
            return values[i] if i < len(values) else None
    return None

# --- Задачи ---
async def send_morning():
    await bot.send_message(
        chat_id=GROUP_CHAT_ID,
        text="☀️ Всем доброго дня!) Записываемся на занятия:\n"
             "https://docs.google.com/spreadsheets/d/1Z39dIQrgdhSoWdD5AE9jIMtfn1ahTxl-femjqxyER0Q/edit#gid=1614712337"
    )

async def send_evening():
    value = check_schedule()
    if value:
        await bot.send_message(
            chat_id=GROUP_CHAT_ID,
            text=f"Подводим итоги — по {value} р. Приносите наличными до конца недели."
        )

async def restart_bot():
    logger.info("Ровно 00:00 — перезапуск бота через exit()")
    os._exit(0)

# --- Команды для админов ---
async def test(update, context):
    user_id = str(update.effective_user.id)
    if user_id not in ADMINS:
        await update.message.reply_text("⛔ Доступ запрещён")
        return
    await update.message.reply_text("✅ Тестовое сообщение отправлено.")
    await send_evening()

# --- Main ---
if __name__ == "__main__":
    from asyncio import get_event_loop

    scheduler = AsyncIOScheduler(timezone=tz)

    # Cron-задачи
    scheduler.add_job(send_morning, "cron", hour=11, minute=0)
    scheduler.add_job(send_evening, "cron", hour=18, minute=0)
    scheduler.add_job(restart_bot, "cron", hour=0, minute=0)

    scheduler.start()

    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("test", test))

    logger.info("Бот запущен и ждёт по расписанию...")
    app.run_polling()
