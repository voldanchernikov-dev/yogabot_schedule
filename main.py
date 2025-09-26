import os
import logging
import sqlite3
from datetime import datetime, timedelta

from dotenv import load_dotenv
import gspread
from google.oauth2.service_account import Credentials
from apscheduler.schedulers.background import BackgroundScheduler

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Bot
from telegram.ext import (
    Updater,
    CommandHandler,
    CallbackContext,
    CallbackQueryHandler,
    MessageHandler,
    Filters,
)

# ==============================
# ЛОГИРОВАНИЕ
# ==============================
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# ==============================
# ЗАГРУЗКА .ENV
# ==============================
load_dotenv()

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID")
SERVICE_ACCOUNT_FILE = os.getenv("SERVICE_ACCOUNT_FILE")
GROUP_CHAT_ID = int(os.getenv("GROUP_CHAT_ID"))
ADMINS = [int(x) for x in os.getenv("ADMINS", "").split(",") if x.strip()]

# ==============================
# GOOGLE SHEETS
# ==============================
def get_gsheet_client():
    creds = Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE,
        scopes=["https://www.googleapis.com/auth/spreadsheets"],
    )
    return gspread.authorize(creds)

# ==============================
# БАЗА ДАННЫХ
# ==============================
def init_db():
    conn = sqlite3.connect("bot.db")
    cur = conn.cursor()
    cur.execute(
        """CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            last_name TEXT
        )"""
    )
    conn.commit()
    conn.close()

def add_user(user_id, username, first_name, last_name):
    conn = sqlite3.connect("bot.db")
    cur = conn.cursor()
    cur.execute(
        """INSERT OR REPLACE INTO users (user_id, username, first_name, last_name)
           VALUES (?, ?, ?, ?)""",
        (user_id, username, first_name, last_name),
    )
    conn.commit()
    conn.close()

def get_user_count():
    conn = sqlite3.connect("bot.db")
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM users")
    count = cur.fetchone()[0]
    conn.close()
    return count

# ==============================
# ОБРАБОТЧИКИ КОМАНД
# ==============================
def start(update: Update, context: CallbackContext):
    user = update.effective_user
    add_user(user.id, user.username, user.first_name, user.last_name)
    update.message.reply_text(f"Привет, {user.first_name}! 👋 Ты зарегистрирован.")

def ping(update: Update, context: CallbackContext):
    if update.effective_user.id not in ADMINS:
        update.message.reply_text("⛔ Доступ только для администраторов.")
        return
    count = get_user_count()
    update.message.reply_text(f"✅ Бот работает. Зарегистрировано пользователей: {count}")

def broadcast(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    message = " ".join(context.args)
    if not message:
        update.message.reply_text("❌ Укажи сообщение: /broadcast <текст>")
        return
    context.bot.send_message(chat_id=user_id, text=f"📢 Ваша рассылка:\n\n{message}")

# ==============================
# INLINE CALLBACKS
# ==============================
def button_handler(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    query.edit_message_text(text=f"Вы нажали: {query.data}")

# ==============================
# JOBS
# ==============================
def send_morning(context: CallbackContext):
    context.bot.send_message(chat_id=GROUP_CHAT_ID, text="🌅 Доброе утро!")

def send_evening(context: CallbackContext):
    context.bot.send_message(chat_id=GROUP_CHAT_ID, text="🌙 Спокойной ночи!")

def restart_bot(context: CallbackContext):
    context.bot.send_message(chat_id=GROUP_CHAT_ID, text="♻️ Бот перезапускается...")
    os._exit(0)

# ==============================
# ОСНОВНОЙ ЗАПУСК
# ==============================
def main():
    init_db()

    updater = Updater(BOT_TOKEN, use_context=True)
    dp = updater.dispatcher

    # команды
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("ping", ping))
    dp.add_handler(CommandHandler("broadcast", broadcast, pass_args=True))

    # inline
    dp.add_handler(CallbackQueryHandler(button_handler))

    # планировщик
    scheduler = BackgroundScheduler(timezone="Europe/Moscow")
    scheduler.add_job(send_morning, "cron", hour=9, minute=0, args=[dp.bot])
    scheduler.add_job(send_evening, "cron", hour=21, minute=0, args=[dp.bot])
    scheduler.add_job(restart_bot, "cron", hour=4, minute=0, args=[dp.bot])
    scheduler.start()

    logger.info("Бот запущен...")
    updater.start_polling()
    updater.idle()


if __name__ == "__main__":
    main()
