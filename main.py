import os
import logging
from datetime import datetime
import pytz
from dotenv import load_dotenv

from apscheduler.schedulers.background import BackgroundScheduler
from telegram import Bot, Update
from telegram.ext import (
    Updater,
    CommandHandler,
    CallbackContext,
    Filters,
)

# ==================== Настройка логов ====================
logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ==================== Загружаем .env ====================
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID")
import json
SERVICE_ACCOUNT_JSON = os.getenv("SERVICE_ACCOUNT_JSON")
if SERVICE_ACCOUNT_JSON:
    SERVICE_ACCOUNT_INFO = json.loads(SERVICE_ACCOUNT_JSON)
else:
    SERVICE_ACCOUNT_INFO = None
GROUP_CHAT_ID = int(os.getenv("GROUP_CHAT_ID"))
ADMINS = [int(x) for x in os.getenv("ADMINS", "").split(",") if x]

if not BOT_TOKEN or not GROUP_CHAT_ID:
    raise ValueError("❌ Переменные окружения BOT_TOKEN и GROUP_CHAT_ID обязательны")

# ==================== Функции бота ====================
def start(update: Update, context: CallbackContext):
    update.message.reply_text("✅ Бот запущен и работает!")

def ping(update: Update, context: CallbackContext):
    """Команда /ping доступна только админам"""
    user_id = update.effective_user.id
    if user_id not in ADMINS:
        update.message.reply_text("⛔ У вас нет прав для этой команды.")
        return
    update.message.reply_text("🏓 Pong! Бот активен.")

def send_scheduled_message(context: CallbackContext):
    """Сообщение, отправляемое по расписанию"""
    bot: Bot = context.bot
    now = datetime.now(pytz.timezone("Europe/Moscow")).strftime("%Y-%m-%d %H:%M:%S")
    bot.send_message(
        chat_id=GROUP_CHAT_ID,
        text=f"⏰ Запланированное сообщение!\nВремя: {now}"
    )

# ==================== Основная функция ====================
def main():
    updater = Updater(BOT_TOKEN, use_context=True)
    dp = updater.dispatcher

    # Команды
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("ping", ping, filters=Filters.user(ADMINS)))

    # Планировщик
    scheduler = BackgroundScheduler(timezone=pytz.timezone("Europe/Moscow"))
    scheduler.add_job(send_scheduled_message, "cron", hour=17, minute=55, args=[updater.bot])
    scheduler.start()

    # Запуск
    logger.info("🚀 Бот запущен...")
    updater.start_polling()
    updater.idle()

if __name__ == "__main__":
    main()
