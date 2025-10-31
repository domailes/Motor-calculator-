import os
import logging
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    Updater, CommandHandler, MessageHandler, Filters, 
    ConversationHandler, CallbackContext
)
import aiohttp
import asyncio

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Получаем переменные окружения
BOT_TOKEN = os.environ.get('BOT_TOKEN')
DEEPSEEK_API_KEY = os.environ.get('DEEPSEEK_API_KEY')

if not BOT_TOKEN:
    logger.error("❌ BOT_TOKEN не установлен!")
    exit(1)
if not DEEPSEEK_API_KEY:
    logger.error("❌ DEEPSEEK_API_KEY не установлен!")
    exit(1)

# Состояния для диалога
POWER, VOLTAGE, EFFICIENCY, POWER_FACTOR, PHASE = range(5)

def start(update: Update, context: CallbackContext) -> int:
    update.message.reply_text(
        "🔧 *Расчет токов двигателя*\n\n"
        "Введите номинальную мощность двигателя (кВт):",
        parse_mode='Markdown'
    )
    return POWER

def power_input(update: Update, context: CallbackContext) -> int:
    try:
        power = float(update.message.text.replace(',', '.'))
        context.user_data['power'] = power
        update.message.reply_text("⚡ Введите напряжение питания (В):")
        return VOLTAGE
    except ValueError:
        update.message.reply_text("❌ Введите корректное число!")
        return POWER

def voltage_input(update: Update, context: CallbackContext) -> int:
    try:
        voltage = float(update.message.text.replace(',', '.'))
        context.user_data['voltage'] = voltage
        update.message.reply_text("🎯 Введите КПД двигателя (в %, например 85):")
        return EFFICIENCY
    except ValueError:
        update.message.reply_text("❌ Введите корректное число!")
        return VOLTAGE

def efficiency_input(update: Update, context: CallbackContext) -> int:
    try:
        efficiency = float(update.message.text.replace(',', '.'))
        context.user_data['efficiency'] = efficiency
        update.message.reply_text("📊 Введите коэффициент мощности (cos φ, например 0.85):")
        return POWER_FACTOR
    except ValueError:
        update.message.reply_text("❌ Введите корректное число!")
        return EFFICIENCY

def power_factor_input(update: Update, context: CallbackContext) -> int:
    try:
        power_factor = float(update.message.text.replace(',', '.'))
        context.user_data['power_factor'] = power_factor
        
        keyboard = [['1', '3']]
        reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True)
        
        update.message.reply_text(
            "🔢 Выберите количество фаз:",
            reply_markup=reply_markup
        )
        return PHASE
    except ValueError:
        update.message.reply_text("❌ Введите корректное число!")
        return POWER_FACTOR

def phase_input(update: Update, context: CallbackContext) -> int:
    try:
        phase = int(update.message.text)
        context.user_data['phase'] = phase
        
        update.message.reply_text(
            "⏳ Выполняю расчет...",
            reply_markup=ReplyKeyboardRemove()
        )
        
        # Запускаем расчет
        asyncio.run(perform_calculation(update, context))
        
        return ConversationHandler.END
        
    except ValueError:
        update.message.reply_text("❌ Введите 1 или 3!")
        return PHASE

async def perform_calculation(update: Update, context: CallbackContext):
    """Выполняет расчет через DeepSeek"""
    try:
        data = context.user_data
        
        prompt = f"""
        Рассчитай номинальный ток электродвигателя:
        - Мощность: {data['power']} кВт
        - Напряжение: {data['voltage']} В
        - КПД: {data['efficiency']}%
        - cos φ: {data['power_factor']}
        - Фазы: {data['phase']}
        
        Дай расчет с формулами и итоговый ток в А.
        """
        
        # Вызов DeepSeek API
        deepseek_response = await call_deepseek_api(prompt)
        
        result_text = f"🔧 *Результаты:*\n\n{deepseek_response}"
        update.message.reply_text(result_text, parse_mode='Markdown')
        
        context.user_data.clear()
        
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        update.message.reply_text("❌ Ошибка расчета")

async def call_deepseek_api(prompt: str) -> str:
    """Вызов API DeepSeek"""
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}"
    }
    
    data = {
        "model": "deepseek-chat",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.3
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://api.deepseek.com/v1/chat/completions", 
                headers=headers, 
                json=data, 
                timeout=30
            ) as response:
                if response.status == 200:
                    result = await response.json()
                    return result["choices"][0]["message"]["content"]
                return f"❌ Ошибка API: {response.status}"
    except Exception as e:
        return f"❌ Ошибка соединения: {str(e)}"

def cancel(update: Update, context: CallbackContext) -> int:
    update.message.reply_text("❌ Расчет отменен")
    context.user_data.clear()
    return ConversationHandler.END

def main():
    try:
        updater = Updater(BOT_TOKEN, use_context=True)
        dp = updater.dispatcher
        
        conv_handler = ConversationHandler(
            entry_points=[CommandHandler('start', start)],
            states={
                POWER: [MessageHandler(Filters.text & ~Filters.command, power_input)],
                VOLTAGE: [MessageHandler(Filters.text & ~Filters.command, voltage_input)],
                EFFICIENCY: [MessageHandler(Filters.text & ~Filters.command, efficiency_input)],
                POWER_FACTOR: [MessageHandler(Filters.text & ~Filters.command, power_factor_input)],
                PHASE: [MessageHandler(Filters.text & ~Filters.command, phase_input)],
            },
            fallbacks=[CommandHandler('cancel', cancel)]
        )
        
        dp.add_handler(conv_handler)
        
        logger.info("🤖 Бот запущен...")
        updater.start_polling()
        updater.idle()
        
    except Exception as e:
        logger.error(f"Ошибка запуска: {e}")
        exit(1)

if __name__ == '__main__':
    main()
