import os
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler
import aiohttp
import json

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Получаем переменные окружения
BOT_TOKEN = os.environ['BOT_TOKEN']
DEEPSEEK_API_KEY = os.environ['DEEPSEEK_API_KEY']
DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"

# Состояния для диалога
POWER, VOLTAGE, EFFICIENCY, POWER_FACTOR, PHASE = range(5)
user_data = {}

async def call_deepseek_api(prompt: str) -> str:
    """Асинхронный вызов API DeepSeek"""
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
            async with session.post(DEEPSEEK_API_URL, headers=headers, json=data, timeout=30) as response:
                if response.status == 200:
                    result = await response.json()
                    return result["choices"][0]["message"]["content"]
                else:
                    return f"❌ Ошибка API: {response.status}"
    except Exception as e:
        return f"❌ Ошибка соединения: {str(e)}"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🔧 **Расчет токов двигателя**\n\n"
        "Введите номинальную мощность двигателя (кВт):"
    )
    return POWER

async def power_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        power = float(update.message.text.replace(',', '.'))
        user_data[update.effective_user.id] = {'power': power}
        await update.message.reply_text("⚡ Введите напряжение питания (В):")
        return VOLTAGE
    except ValueError:
        await update.message.reply_text("❌ Введите корректное число!")
        return POWER

async def voltage_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        voltage = float(update.message.text.replace(',', '.'))
        user_data[update.effective_user.id]['voltage'] = voltage
        await update.message.reply_text("🎯 Введите КПД двигателя (в %, например 85):")
        return EFFICIENCY
    except ValueError:
        await update.message.reply_text("❌ Введите корректное число!")
        return VOLTAGE

async def efficiency_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        efficiency = float(update.message.text.replace(',', '.'))
        user_data[update.effective_user.id]['efficiency'] = efficiency
        await update.message.reply_text("📊 Введите коэффициент мощности (cos φ, например 0.85):")
        return POWER_FACTOR
    except ValueError:
        await update.message.reply_text("❌ Введите корректное число!")
        return EFFICIENCY

async def power_factor_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        power_factor = float(update.message.text.replace(',', '.'))
        user_data[update.effective_user.id]['power_factor'] = power_factor
        await update.message.reply_text("🔢 Введите количество фаз (1 или 3):")
        return PHASE
    except ValueError:
        await update.message.reply_text("❌ Введите корректное число!")
        return POWER_FACTOR

async def phase_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        phase = int(update.message.text)
        if phase not in [1, 3]:
            await update.message.reply_text("❌ Введите 1 или 3!")
            return PHASE
        
        data = user_data[update.effective_user.id]
        
        # Формируем запрос для DeepSeek
        prompt = f"""
        Рассчитай номинальный ток электродвигателя:
        - Мощность: {data['power']} кВт
        - Напряжение: {data['voltage']} В  
        - КПД: {data['efficiency']}%
        - cos φ: {data['power_factor']}
        - Фазы: {data['phase']}
        
        Предоставь:
        1. Формулу расчета
        2. Пошаговый расчет
        3. Итоговый ток в А
        4. Рекомендации по защитной аппаратуре
        """
        
        processing_msg = await update.message.reply_text("⏳ Выполняю расчет...")
        deepseek_response = await call_deepseek_api(prompt)
        await processing_msg.delete()
        
        result_text = f"🔧 **Результаты расчета:**\n\n{deepseek_response}"
        
        if len(result_text) > 4096:
            for x in range(0, len(result_text), 4096):
                await update.message.reply_text(result_text[x:x+4096])
        else:
            await update.message.reply_text(result_text)
        
        del user_data[update.effective_user.id]
        return ConversationHandler.END
        
    except ValueError:
        await update.message.reply_text("❌ Введите корректное число!")
        return PHASE

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Расчет отменен")
    if update.effective_user.id in user_data:
        del user_data[update.effective_user.id]
    return ConversationHandler.END

def main():
    application = Application.builder().token(BOT_TOKEN).build()
    
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
    application.run_polling()

if __name__ == '__main__':
    main()
