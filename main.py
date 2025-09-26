import os
import json
import pytz
import gspread
import asyncio
from datetime import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from google.oauth2.service_account import Credentials
from telegram import Bot
from dotenv import load_dotenv

# Загружаем переменные окружения
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
GSHEET_ID = os.getenv("GSHEET_ID")
TARGET_GID = os.getenv("TARGET_GID")
GOOGLE_CREDENTIALS = os.getenv("GOOGLE_CREDENTIALS")

# Читаем креды из JSON-строки
creds_dict = json.loads(GOOGLE_CREDENTIALS)
creds = Credentials.from_service_account_info(
    creds_dict, scopes=["https://www.googleapis.com/auth/spreadsheets"]
)

gc = gspread.authorize(creds)
bot = Bot(token=BOT_TOKEN)

# Функция получения значения из таблицы
def get_today_value():
    sh = gc.open_by_key(GSHEET_ID)
    ws = sh.get_worksheet_by_id(int(TARGET_GID))

    today = datetime.now(pytz.timezone("Europe/Moscow")).strftime("%d.%m.%Y")

    # ищем строку по сегодняшней дате
    col_values = ws.col_values(1)  # колонка с датами
    for i, date in enumerate(col_values, start=1):
        if date.strip() == today:
            row = ws.row_values(i)
            if len(row) > 13:  # колонка N (14-я)
                return row[13]
    return None

# Сообщения
async def send_morning():
    text = "☀️ Всем доброго дня!) Записываемся на занятия:\nhttps://docs.google.com/spreadsheets/d/1Z39dIQrgdhSoWdD5AE9jIMtfn1ahTxl-femjqxyER0Q/edit#gid=1614712337"
    await bot.send_message(chat_id=CHAT_ID, text=text)

async def send_evening():
    value = get_today_value()
    if value:
        text = f"Подводим итоги — по {value} р. Приносите наличными до конца недели."
        await bot.send_message(chat_id=CHAT_ID, text=text)

# Планировщик
async def scheduler():
    scheduler = AsyncIOScheduler(timezone="Europe/Moscow")
    scheduler.add_job(send_morning, "cron", hour=11, minute=0)
    scheduler.add_job(send_evening, "cron", hour=18, minute=0)
    scheduler.start()

    while True:
        await asyncio.sleep(60)

if __name__ == "__main__":
    asyncio.run(scheduler())
