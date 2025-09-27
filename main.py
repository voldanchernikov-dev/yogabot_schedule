import os
import logging
import pytz
import gspread
from datetime import datetime
from google.oauth2.service_account import Credentials
from apscheduler.schedulers.background import BackgroundScheduler
from telegram import Bot
from telegram.ext import Application

# Логи
logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s",
    level=logging.INFO
)

# Настройки
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")  # ID чата или группы
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID")
SHEET_NAME = os.getenv("SHEET_NAME", "Лист1")

MORNING_HOUR = int(os.getenv("MORNING_HOUR", 9))
MORNING_MINUTE = int(os.getenv("MORNING_MINUTE", 0))
EVENING_HOUR = int(os.getenv("EVENING_HOUR", 18))
EVENING_MINUTE = int(os.getenv("EVENING_MINUTE", 0))

tz = pytz.timezone("Europe/Moscow")

# Авторизация Google Sheets
def open_sheet():
    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    creds = Credentials.from_service_account_file("service_account.json", scopes=scopes)
    gc = gspread.authorize(creds)
    sh = gc.open_by_key(SPREADSHEET_ID)
    return sh.worksheet(SHEET_NAME)

# Проверка наличия занятия
def has_lessons_today():
    try:
        ws = open_sheet()
        today = datetime.now(tz).strftime("%d.%m.%Y")
        records = ws.get_all_records()
        for row in records:
            if str(row.get("Дата")).strip() == today and row.get("Занятие"):
                return True
        return False
    except Exception as e:
        logging.error(f"Ошибка при проверке занятий: {e}")
        return False

# Сообщения
async def send_morning_message(app: Application):
    try:
        if has_lessons_today():
            await app.bot.send_message(chat_id=CHAT_ID, text="🌅 Доброе утро! Сегодня есть занятия.")
            logging.info("Утреннее сообщение отправлено")
        else:
            logging.info("Занятий нет, утреннее сообщение не отправлено")
    except Exception as e:
        logging.error(f"Ошибка при отправке утреннего сообщения: {e}")

async def send_evening_message(app: Application):
    try:
        if has_lessons_today():
            await app.bot.send_message(chat_id=CHAT_ID, text="🌙 Напоминание: занятия сегодня!")
            logging.info("Вечернее сообщение отправлено")
        else:
            logging.info("Занятий нет, вечернее сообщение не отправлено")
    except Exception as e:
        logging.error(f"Ошибка при отправке вечернего сообщения: {e}")

# Планировщик
def schedule_jobs(app: Application):
    scheduler = BackgroundScheduler(timezone=tz)

    scheduler.add_job(send_morning_message, "cron",
                      hour=MORNING_HOUR, minute=MORNING_MINUTE,
                      args=[app], id="notify_morning")

    scheduler.add_job(send_evening_message, "cron",
                      hour=EVENING_HOUR, minute=EVENING_MINUTE,
                      args=[app], id="notify_evening")

    scheduler.start()
    logging.info("Планировщик запущен")

# Основной запуск
def main():
    app = Application.builder().token(BOT_TOKEN).build()
    schedule_jobs(app)

    logging.info("Бот запущен")
    app.run_polling()

if __name__ == "__main__":
    main()
