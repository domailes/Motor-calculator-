import os
import logging
import asyncio
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    Updater, CommandHandler, MessageHandler, Filters, 
    ConversationHandler, CallbackContext
)
import aiohttp
import json

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Получаем переменные окружения
BOT_TOKEN = os.environ.get('BOT_TOKEN')
DEEPSEEK_API_KEY = os.environ.get('DEEPSEEK_API_KEY')
DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"

# Проверка переменных окружения
if not BOT_TOKEN:
    logger.error("❌ BOT_TOKEN не установлен!")
    exit(1)
if not DEEPSEEK_API_KEY:
    logger.error("❌ DEEPSEEK_API_KEY не установлен!")
    exit(1)

# Состояния для диалога
POWER, VOLTAGE, EFFICIENCY, POWER_FACTOR, PHASE = range(5)

async def call_deepseek_api(prompt: str) -> str:
    """Асинхронный вызов API DeepSeek"""
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}"
    }
    
    data = {
        "model": "deepseek-chat",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.3,
        "max_tokens": 2000
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(DEEPSEEK_API_URL, headers=headers, json=data, timeout=30) as response:
                if response.status == 200:
                    result = await response.json()
                    return result["choices"][0]["message"]["content"]
                else:
                    error_text = await response.text()
                    logger.error(f"API Error: {response.status} - {error_text}")
                    return f"❌ Ошибка API DeepSeek: {response.status}"
    except Exception as e:
        logger.error(f"Connection error: {str(e)}")
        return f"❌ Ошибка соединения с DeepSeek: {str(e)}"

def start(update: Update, context: CallbackContext) -> int:
    user = update.message.from_user
    logger.info(f"Пользователь {user.first_name} начал диалог")
    
    update.message.reply_text(
        "🔧 *Расчет токов двигателя*\n\n"
        "Я помогу рассчитать номинальный ток электродвигателя.\n\n"
        "*Введите номинальную мощность двигателя (кВт):*",
        parse_mode='Markdown'
    )
    return POWER

def power_input(update: Update, context: CallbackContext) -> int:
    try:
        power = float(update.message.text.replace(',', '.'))
        if power <= 0:
            update.message.reply_text("❌ Мощность должна быть положительным числом!")
            return POWER
            
        context.user_data['power'] = power
        update.message.reply_text(
            "⚡ *Введите напряжение питания (В):*",
            parse_mode='Markdown'
        )
        return VOLTAGE
    except ValueError:
        update.message.reply_text("❌ Пожалуйста, введите корректное число для мощности!")
        return POWER

def voltage_input(update: Update, context: CallbackContext) -> int:
    try:
        voltage = float(update.message.text.replace(',', '.'))
        if voltage <= 0:
            update.message.reply_text("❌ Напряжение должно быть положительным числом!")
            return VOLTAGE
            
        context.user_data['voltage'] = voltage
        update.message.reply_text(
            "🎯 *Введите КПД двигателя (в %, например 85):*",
            parse_mode='Markdown'
        )
        return EFFICIENCY
    except ValueError:
        update.message.reply_text("❌ Пожалуйста, введите корректное число для напряжения!")
        return VOLTAGE

def efficiency_input(update: Update, context: CallbackContext) -> int:
    try:
        efficiency = float(update.message.text.replace(',', '.'))
        if efficiency <= 0 or efficiency > 100:
            update.message.reply_text("❌ КПД должен быть в диапазоне 0-100%!")
            return EFFICIENCY
            
        context.user_data['efficiency'] = efficiency
        update.message.reply_text(
            "📊 *Введите коэффициент мощности (cos φ, например 0.85):*",
            parse_mode='Markdown'
        )
        return POWER_FACTOR
    except ValueError:
        update.message.reply_text("❌ Пожалуйста, введите корректное число для КПД!")
        return EFFICIENCY

def power_factor_input(update: Update, context: CallbackContext) -> int:
    try:
        power_factor = float(update.message.text.replace(',', '.'))
        if power_factor <= 0 or power_factor > 1:
            update.message.reply_text("❌ Коэффициент мощности должен быть в диапазоне 0-1!")
            return POWER_FACTOR
            
        context.user_data['power_factor'] = power_factor
        
        # Создаем клавиатуру для выбора фаз
        keyboard = [['1', '3']]
        reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True)
        
        update.message.reply_text(
            "🔢 *Выберите количество фаз:*",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        return PHASE
    except ValueError:
        update.message.reply_text("❌ Пожалуйста, введите корректное число для коэффициента мощности!")
        return POWER_FACTOR

def phase_input(update: Update, context: CallbackContext) -> int:
    try:
        phase = int(update.message.text)
        if phase not in [1, 3]:
            update.message.reply_text("❌ Пожалуйста, выберите 1 или 3 для количества фаз!")
            return PHASE
        
        context.user_data['phase'] = phase
        
        # Убираем клавиатуру
        update.message.reply_text(
            "⏳ *Выполняю расчет с помощью DeepSeek...*",
            reply_markup=ReplyKeyboardRemove(),
            parse_mode='Markdown'
        )
        
        # Запускаем асинхронный расчет
        asyncio.run(perform_calculation(update, context))
        
        return ConversationHandler.END
        
    except ValueError:
        update.message.reply_text("❌ Пожалуйста, введите корректное число фаз!")
        return PHASE

async def perform_calculation(update: Update, context: CallbackContext):
    """Асинхронная функция для выполнения расчета"""
    try:
        data = context.user_data
        
        # Формируем запрос для DeepSeek
        prompt = f"""
        Рассчитай номинальный ток электродвигателя со следующими параметрами:
        - Мощность: {data['power']} кВт
        - Напряжение: {data['voltage']} В
        - КПД: {data['efficiency']}%
        - Коэффициент мощности: {data['power_factor']}
        - Количество фаз: {data['phase']}
        
        Предоставь подробный расчет с формулами и объяснениями:
        1. Формула расчета для {data['phase']}-фазной сети
        2. Пошаговый расчет с подстановкой значений
        3. Итоговое значение тока в Амперах
        4. Рекомендации по выбору защитной аппаратуры (автоматический выключатель, тепловое реле)
        5. Укажи стандартные значения для подобных двигателей
        
        Ответ должен быть четким, технически точным и полезным для инженера.
        Используй только русский язык в ответе.
        """
        
        # Вызываем DeepSeek API
        deepseek_response = await call_deepseek_api(prompt)
        
        # Отправляем результат
        result_text = f"🔧 *Результаты расчета:*\n\n{deepseek_response}"
        
        # Разбиваем длинные сообщения
        if len(result_text) > 4096:
            for x in range(0, len(result_text), 4096):
                update.message.reply_text(
                    result_text[x:x+4096],
                    parse_mode='Markdown'
                )
        else:
            update.message.reply_text(
                result_text,
                parse_mode='Markdown'
            )
        
        # Очищаем данные пользователя
        context.user_data.clear()
        
    except Exception as e:
        logger.error(f"Ошибка при расчете: {e}")
        update.message.reply_text(
            "❌ Произошла ошибка при расчете. Попробуйте снова.",
            reply_markup=ReplyKeyboardRemove()
        )

def cancel(update: Update, context: CallbackContext) -> int:
    user = update.message.from_user
    logger.info(f"Пользователь {user.first_name} отменил диалог")
    
    update.message.reply_text(
        "❌ Расчет отменен",
        reply_markup=ReplyKeyboardRemove()
    )
    context.user_data.clear()
    return ConversationHandler.END

def error_handler(update: Update, context: CallbackContext):
    """Обработчик ошибок"""
    logger.error(f"Ошибка: {context.error}", exc_info=context.error)
    
    try:
        if update and update.message:
            update.message.reply_text(
                "❌ Произошла ошибка. Попробуйте снова.",
                reply_markup=ReplyKeyboardRemove()
            )
    except Exception as e:
        logger.error(f"Ошибка при отправке сообщения об ошибке: {e}")

def main():
    """Запуск бота"""
    try:
        # Создаем Updater и передаем ему токен бота
        updater = Updater(BOT_TOKEN, use_context=True)
        
        # Получаем диспетчер для регистрации обработчиков
        dp = updater.dispatcher
        
        # Настройка обработчиков диалога
        conv_handler = ConversationHandler(
            entry_points=[CommandHandler('start', start)],
            states={
                POWER: [MessageHandler(Filters.text & ~Filters.command, power_input)],
                VOLTAGE: [MessageHandler(Filters.text & ~Filters.command, voltage_input)],
                EFFICIENCY: [MessageHandler(Filters.text & ~Filters.command, efficiency_input)],
                POWER_FACTOR: [MessageHandler(Filters.text & ~Filters.command, power_factor_input)],
                PHASE: [MessageHandler(Filters.text & ~Filters.command, phase_input)],
            },
            fallbacks=[CommandHandler('cancel', cancel)],
            allow_reentry=True
        )
        
        dp.add_handler(conv_handler)
        dp.add_error_handler(error_handler)
        
        # Команда для прямого расчета
        dp.add_handler(CommandHandler("calc", start))
        
        # Запускаем бота
        logger.info("🤖 Бот запущен...")
        updater.start_polling()
        updater.idle()
        
    except Exception as e:
        logger.error(f"Ошибка при запуске бота: {e}")
        exit(1)

if __name__ == '__main__':
    main()
