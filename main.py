import os
import logging
from datetime import datetime
from dotenv import load_dotenv

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Bot
from telegram.ext import (
    Updater,
    CommandHandler,
    CallbackQueryHandler,
    CallbackContext,
    MessageHandler,
    Filters,
)

import gspread
from oauth2client.service_account import ServiceAccountCredentials
from apscheduler.schedulers.background import BackgroundScheduler
import pytz

# ====================== ЛОГИ ======================
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# ====================== ENV ======================
load_dotenv()
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID")
SERVICE_ACCOUNT_FILE = os.getenv("SERVICE_ACCOUNT_FILE")
GROUP_CHAT_ID = os.getenv("GROUP_CHAT_ID")
ADMINS = [int(x) for x in os.getenv("ADMINS", "").split(",") if x]

# ====================== GOOGLE SHEETS ======================
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_name(SERVICE_ACCOUNT_FILE, scope)
client = gspread.authorize(creds)
sheet = client.open_by_key(SPREADSHEET_ID).sheet1

# ====================== КОМАНДЫ ======================
def start(update: Update, context: CallbackContext):
    update.message.reply_text("Бот запущен. Используй /ping или другие команды.")

def ping(update: Update, context: CallbackContext):
    user_id = update.message.from_user.id
    if user_id not in ADMINS:
        update.message.reply_text("⛔ У вас нет доступа к этой команде.")
        return
    update.message.reply_text("✅ Бот работает!")

def broadcast(update: Update, context: CallbackContext):
    """Рассылка только для админов"""
    user_id = update.message.from_user.id
    if user_id not in ADMINS:
        update.message.reply_text("⛔ У вас нет доступа.")
        return

    text = " ".join(context.args)
    if not text:
        update.message.reply_text("⚠ Использование: /broadcast <текст>")
        return

    users = sheet.col_values(1)  # допустим, в 1 столбце — user_id
    bot: Bot = context.bot

    for uid in users:
        try:
            bot.send_message(chat_id=int(uid), text=text)
        except Exception as e:
            logger.warning(f"Не удалось отправить {uid}: {e}")

    update.message.reply_text("✅ Рассылка завершена.")

# ====================== JOB ======================
def scheduled_message(context: CallbackContext):
    """Отправка сообщения по расписанию"""
    context.bot.send_message(chat_id=GROUP_CHAT_ID, text="📢 Запланированное сообщение!")

# ====================== MAIN ======================
def main():
    updater = Updater(BOT_TOKEN, use_context=True)
    dp = updater.dispatcher

    # команды
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("ping", ping))
    dp.add_handler(CommandHandler("broadcast", broadcast, pass_args=True))

    # планировщик
    scheduler = BackgroundScheduler(timezone=pytz.timezone("Europe/Moscow"))
    scheduler.add_job(scheduled_message, "cron", hour=18, minute=0, args=[updater.bot])
    scheduler.start()

    updater.start_polling()
    updater.idle()

if __name__ == "__main__":
    main()
