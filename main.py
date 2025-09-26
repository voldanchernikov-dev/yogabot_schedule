import os
import json
import logging
from datetime import datetime
import pytz

import gspread
from oauth2client.service_account import ServiceAccountCredentials
from telegram import Bot, Update
from telegram.ext import Updater, CommandHandler, CallbackContext
from apscheduler.schedulers.background import BackgroundScheduler

# Логирование
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Конфиги ---
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID")
GROUP_CHAT_ID = int(os.getenv("GROUP_CHAT_ID"))
ADMINS = [int(x) for x in os.getenv("ADMINS", "").split(",") if x.strip()]

SERVICE_ACCOUNT_FILE = os.getenv("SERVICE_ACCOUNT_FILE")
GOOGLE_CREDENTIALS = os.getenv("GOOGLE_CREDENTIALS")

tz = pytz.timezone("Europe/Moscow")
bot = Bot(token=BOT_TOKEN)

# --- Google Sheets ---
def get_gspread_client():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    if GOOGLE_CREDENTIALS:
        creds_dict = json.loads(GOOGLE_CREDENTIALS)
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    elif SERVICE_ACCOUNT_FILE and os.path.exists(SERVICE_ACCOUNT_FILE):
        creds = ServiceAccountCredentials.from_json_keyfile_name(SERVICE_ACCOUNT_FILE, scope)
    else:
        raise RuntimeError("Нет данных для Google API")
    return gspread.authorize(creds)

def check_schedule():
    client = get_gspread_client()
    sheet = client.open_by_key(SPREADSHEET_ID).sheet1

    today = datetime.now(tz).strftime("%d.%m.%Y")
    dates = sheet.col_values(1)  # даты в колонке 1
    values = sheet.col_values(2) # суммы в колонке 2

    for i, d in enumerate(dates):
        if d.strip() == today:
            return values[i] if i < len(values) else None
    return None

# --- Задачи ---
def send_morning():
    bot.send_message(
        chat_id=GROUP_CHAT_ID,
        text="☀️ Всем доброго дня!) Записываемся на занятия:\n"
             "https://docs.google.com/spreadsheets/d/1Z39dIQrgdhSoWdD5AE9jIMtfn1ahTxl-femjqxyER0Q/edit#gid=1614712337"
    )

def send_evening():
    value = check_schedule()
    if value:
        bot.send_message(
            chat_id=GROUP_CHAT_ID,
            text=f"Подводим итоги — по {value} р. Приносите наличными до конца недели."
        )

def restart_bot():
    logger.info("Ровно 00:00 — перезапуск бота через exit()")
    os._exit(0)

# --- Команды ---
def ping(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    if user_id not in ADMINS:
        update.message.reply_text("⛔ У вас нет доступа")
        return
    update.message.reply_text("✅ Бот работает и задачи активны")

# --- Main ---
def main():
    updater = Updater(token=BOT_TOKEN, use_context=True)
    dp = updater.dispatcher

    dp.add_handler(CommandHandler("ping", ping))

    # Планировщик
    scheduler = BackgroundScheduler(timezone=tz)
    scheduler.add_job(send_morning, "cron", hour=11, minute=0)
    scheduler.add_job(send_evening, "cron", hour=18, minute=0)
    scheduler.add_job(restart_bot, "cron", hour=0, minute=0)
    scheduler.start()

    logger.info("Бот запущен и ждёт по расписанию...")
    updater.start_polling()
    updater.idle()

if __name__ == "__main__":
    main()
