import os
import logging
from datetime import datetime
import pytz
import gspread
from google.oauth2.service_account import Credentials
from telegram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import asyncio

# ===============================
# Настройки
# ===============================
TOKEN = os.getenv("BOT_TOKEN")  # токен телеграм бота
CHAT_ID = os.getenv("CHAT_ID")  # id чата/группы, куда слать
GSHEET_ID = os.getenv("GSHEET_ID")  # id таблицы
TARGET_GID = os.getenv("TARGET_GID")  # gid вкладки

# Временная зона
TIMEZONE = pytz.timezone("Europe/Moscow")

# ===============================
# Логирование
# ===============================
logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s",
    level=logging.INFO
)

# ===============================
# Google Sheets
# ===============================
def get_sheet():
    creds = Credentials.from_service_account_file(
        "service_account.json",
        scopes=["https://www.googleapis.com/auth/spreadsheets"]
    )
    client = gspread.authorize(creds)
    spreadsheet = client.open_by_key(GSHEET_ID)

    # находим вкладку по gid
    for worksheet in spreadsheet.worksheets():
        if str(worksheet.id) == str(TARGET_GID):
            return worksheet
    raise Exception("Вкладка с таким gid не найдена")

def get_today_value():
    sheet = get_sheet()
    today_str = datetime.now(TIMEZONE).strftime("%d.%m.%Y")
    data = sheet.get_all_records()

    for row in data:
        if str(row.get("Дата")) == today_str:
            return row.get("n")  # колонка n (сумма)
    return None

# ===============================
# Отправка сообщений
# ===============================
async def send_message(text: str):
    bot = Bot(token=TOKEN)
    await bot.send_message(chat_id=CHAT_ID, text=text)

async def job_11():
    value = get_today_value()
    if value is not None:
        msg = "☀️ Всем доброго дня!) Записываемся на занятия:\nhttps://docs.google.com/spreadsheets/d/{}#gid={}".format(GSHEET_ID, TARGET_GID)
        await send_message(msg)
        logging.info("Сообщение в 11:00 отправлено")
    else:
        logging.info("Сегодня занятий нет (11:00)")

async def job_18():
    value = get_today_value()
    if value is not None:
        msg = f"Подводим итоги — по {value} р. Приносите наличными до конца недели."
        await send_message(msg)
        logging.info("Сообщение в 18:00 отправлено")
    else:
        logging.info("Сегодня занятий нет (18:00)")

# Автоперезапуск каждый день в 00:00
async def restart():
    logging.info("Перезапуск задач...")
    scheduler.remove_all_jobs()
    scheduler.add_job(job_11, "cron", hour=11, minute=0, timezone=TIMEZONE)
    scheduler.add_job(job_18, "cron", hour=18, minute=0, timezone=TIMEZONE)
    scheduler.add_job(restart, "cron", hour=0, minute=0, timezone=TIMEZONE)

# ===============================
# Основной запуск
# ===============================
async def main():
    scheduler.add_job(job_11, "cron", hour=11, minute=0, timezone=TIMEZONE)
    scheduler.add_job(job_18, "cron", hour=18, minute=0, timezone=TIMEZONE)
    scheduler.add_job(restart, "cron", hour=0, minute=0, timezone=TIMEZONE)
    scheduler.start()
    logging.info("Бот запущен и ждёт заданий...")
    while True:
        await asyncio.sleep(3600)

if __name__ == "__main__":
    scheduler = AsyncIOScheduler()
    asyncio.run(main())
