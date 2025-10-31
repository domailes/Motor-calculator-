import os
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler
import aiohttp

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
if not BOT_TOKEN or not DEEPSEEK_API_KEY:
    logger.error("❌ Не установлены BOT_TOKEN или DEEPSEEK_API_KEY")
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
                    return f"❌ Ошибка API: {response.status}"
    except Exception as e:
        logger.error(f"Connection error: {str(e)}")
        return f"❌ Ошибка соединения: {str(e)}"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        "🔧 **Расчет токов двигателя**\n\n"
        "Я помогу рассчитать номинальный ток электродвигателя.\n\n"
        "Введите номинальную мощность двигателя (кВт):"
    )
    return POWER

async def power_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        power = float(update.message.text.replace(',', '.'))
        if power <= 0:
            await update.message.reply_text("❌ Мощность должна быть положительным числом!")
            return POWER
            
        context.user_data['power'] = power
        await update.message.reply_text("⚡ Введите напряжение питания (В):")
        return VOLTAGE
    except ValueError:
        await update.message.reply_text("❌ Пожалуйста, введите корректное число для мощности!")
        return POWER

async def voltage_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        voltage = float(update.message.text.replace(',', '.'))
        if voltage <= 0:
            await update.message.reply_text("❌ Напряжение должно быть положительным числом!")
            return VOLTAGE
            
        context.user_data['voltage'] = voltage
        await update.message.reply_text("🎯 Введите КПД двигателя (в %, например 85):")
        return EFFICIENCY
    except ValueError:
        await update.message.reply_text("❌ Пожалуйста, введите корректное число для напряжения!")
        return VOLTAGE

async def efficiency_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        efficiency = float(update.message.text.replace(',', '.'))
        if efficiency <= 0 or efficiency > 100:
            await update.message.reply_text("❌ КПД должен быть в диапазоне 0-100%!")
            return EFFICIENCY
            
        context.user_data['efficiency'] = efficiency
        await update.message.reply_text("📊 Введите коэффициент мощности (cos φ, например 0.85):")
        return POWER_FACTOR
    except ValueError:
        await update.message.reply_text("❌ Пожалуйста, введите корректное число для КПД!")
        return EFFICIENCY

async def power_factor_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        power_factor = float(update.message.text.replace(',', '.'))
        if power_factor <= 0 or power_factor > 1:
            await update.message.reply_text("❌ Коэффициент мощности должен быть в диапазоне 0-1!")
            return POWER_FACTOR
            
        context.user_data['power_factor'] = power_factor
        await update.message.reply_text("🔢 Введите количество фаз (1 или 3):")
        return PHASE
    except ValueError:
        await update.message.reply_text("❌ Пожалуйста, введите корректное число для коэффициента мощности!")
        return POWER_FACTOR

async def phase_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        phase = int(update.message.text)
        if phase not in [1, 3]:
            await update.message.reply_text("❌ Пожалуйста, введите 1 или 3 для количества фаз!")
            return PHASE
        
        data = context.user_data
        
        # Формируем запрос для DeepSeek
        prompt = f"""
        Рассчитай номинальный ток электродвигателя со следующими параметрами:
        - Мощность: {data['power']} кВт
        - Напряжение: {data['voltage']} В
        - КПД: {data['efficiency']}%
        - Коэффициент мощности: {data['power_factor']}
        - Количество фаз: {phase}
        
        Предоставь подробный расчет с формулами и объяснениями:
        1. Формула расчета для {phase}-фазной сети
        2. Пошаговый расчет с подстановкой значений
        3. Итоговое значение тока в Амперах
        4. Рекомендации по выбору защитной аппаратуры (автоматический выключатель, тепловое реле)
        5. Укажи стандартные значения для подобных двигателей
        
        Ответ должен быть четким, технически точным и полезным для инженера.
        Используй только русский язык в ответе.
        """
        
        # Отправляем сообщение о начале расчета
        processing_msg = await update.message.reply_text("⏳ Выполняю расчет с помощью DeepSeek...")
        
        # Вызываем DeepSeek API
        deepseek_response = await call_deepseek_api(prompt)
        
        # Удаляем сообщение "Выполняю расчет..."
        await context.bot.delete_message(
            chat_id=update.effective_chat.id,
            message_id=processing_msg.message_id
        )
        
        # Отправляем результат (разбиваем на части если слишком длинный)
        result_text = f"🔧 **Результаты расчета:**\n\n{deepseek_response}"
        
        if len(result_text) > 4096:
            for x in range(0, len(result_text), 4096):
                await update.message.reply_text(result_text[x:x+4096])
        else:
            await update.message.reply_text(result_text)
        
        # Очищаем данные пользователя
        context.user_data.clear()
        
        return ConversationHandler.END
        
    except ValueError:
        await update.message.reply_text("❌ Пожалуйста, введите корректное число фаз!")
        return PHASE

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("❌ Расчет отменен")
    context.user_data.clear()
    return ConversationHandler.END

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error(f"Ошибка: {context.error}", exc_info=context.error)
    if update and update.message:
        await update.message.reply_text("❌ Произошла ошибка. Попробуйте снова.")

def main():
    try:
        # Создаем приложение бота
        application = Application.builder().token(BOT_TOKEN).build()
        
        # Настройка обработчиков
        conv_handler = ConversationHandler(
            entry_points=[CommandHandler('start', start)],
            states={
                POWER: [MessageHandler(filters.TEXT & ~filters.COMMAND, power_input)],
                VOLTAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, voltage_input)],
                EFFICIENCY: [MessageHandler(filters.TEXT & ~filters.COMMAND, efficiency_input)],
                POWER_FACTOR: [MessageHandler(filters.TEXT & ~filters.COMMAND, power_factor_input)],
                PHASE: [MessageHandler(filters.TEXT & ~filters.COMMAND, phase_input)],
            },
            fallbacks=[CommandHandler('cancel', cancel)]
        )
        
        application.add_handler(conv_handler)
        application.add_error_handler(error_handler)
        
        # Команда для прямого расчета
        application.add_handler(CommandHandler("calc", start))
        
        # Запускаем бота
        print("🤖 Бот запущен на Render...")
        application.run_polling()
        
    except Exception as e:
        logger.error(f"Ошибка при запуске бота: {e}")
        exit(1)

if __name__ == '__main__':
    main()
