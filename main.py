import os
from dotenv import load_dotenv
import sqlite3
from datetime import datetime
import urllib.parse
from openai import OpenAI
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

load_dotenv()

# Настройка OpenAI API
client = OpenAI(
    base_url=os.getenv("OPENAI_BASE_URL"),
    api_key=os.getenv("OPENAI_API_KEY"),
)

# Создаем подключение к базе данных
conn = sqlite3.connect('birthdays.db', check_same_thread=False)
cursor = conn.cursor()

# Создаем таблицу для хранения дней рождения
cursor.execute('''
CREATE TABLE IF NOT EXISTS birthdays
(user_id INTEGER, name TEXT, date TEXT)
''')
conn.commit()

# Создаем таблицу для отслеживания новых пользователей
cursor.execute('''
CREATE TABLE IF NOT EXISTS users
(user_id INTEGER PRIMARY KEY)
''')
conn.commit()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id

    # Проверяем, новый ли это пользователь
    cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    if not cursor.fetchone():
        # Это новый пользователь, отправляем приветственное сообщение
        welcome_message = (
            "🎉 Добро пожаловать в Birthday Reminder Bot! 🎂\n\n"
            "Я ваш персональный помощник для запоминания и празднования дней рождения!\n\n"
            "🔹 Сохраняйте дни рождения близких\n"
            "🔹 Просматривайте список сохраненных дат\n"
            "🔹 Генерируйте уникальные поздравления с помощью ИИ\n"
            "🔹 Добавляйте напоминания прямо в календарь\n\n"
            "Начните прямо сейчас и никогда не забывайте важные даты! 🥳"
        )
        await update.message.reply_text(welcome_message)

        # Добавляем пользователя в базу данных
        cursor.execute("INSERT INTO users (user_id) VALUES (?)", (user_id,))
        conn.commit()

    # Показываем основное меню
    keyboard = [
        [InlineKeyboardButton("Добавить день рождения", callback_data='add')],
        [InlineKeyboardButton("Просмотреть дни рождения", callback_data='view')],
        [InlineKeyboardButton("Сгенерировать поздравление", callback_data='generate')],
        [InlineKeyboardButton("Добавить напоминание в календарь", callback_data='add_to_calendar')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text('Выберите действие:', reply_markup=reply_markup)


async def button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    if query.data == 'add_to_calendar':
        user_id = update.effective_user.id
        cursor.execute("SELECT name FROM birthdays WHERE user_id = ?", (user_id,))
        names = cursor.fetchall()
        if names:
            keyboard = [[InlineKeyboardButton(name[0], callback_data=f'cal_{name[0]}')] for name in names]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text("Выберите человека для добавления в календарь:", reply_markup=reply_markup)
        else:
            await query.edit_message_text("У вас пока нет сохраненных дней рождения.")

    if query.data == 'add':
        await query.edit_message_text("Введите имя родственника:")
        context.user_data['state'] = 'waiting_name'
    elif query.data == 'view':
        user_id = update.effective_user.id
        try:
            cursor.execute("SELECT name, date FROM birthdays WHERE user_id = ?", (user_id,))
            birthdays = cursor.fetchall()
            if birthdays:
                message = "Сохраненные дни рождения:\n\n"
                for name, date in birthdays:
                    message += f"{name}: {date}\n"
            else:
                message = "У вас пока нет сохраненных дней рождения."

            keyboard = [
                [InlineKeyboardButton("Добавить день рождения", callback_data='add')],
                [InlineKeyboardButton("Сгенерировать поздравление", callback_data='generate')],
                [InlineKeyboardButton("Главное меню", callback_data='main')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(message, reply_markup=reply_markup)
        except sqlite3.Error as e:
            await query.edit_message_text(f"Произошла ошибка при чтении из базы данных: {e}")
    elif query.data == 'generate':
        user_id = update.effective_user.id
        cursor.execute("SELECT name FROM birthdays WHERE user_id = ?", (user_id,))
        names = cursor.fetchall()
        if names:
            keyboard = [[InlineKeyboardButton(name[0], callback_data=f'gen_{name[0]}')] for name in names]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text("Выберите человека для поздравления:", reply_markup=reply_markup)
        else:
            await query.edit_message_text("У вас пока нет сохраненных дней рождения.")
    elif query.data == 'main':
        await start(update, context)  # Возвращаемся в главное меню


async def add_to_calendar(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    name = query.data.split('_')[1]
    user_id = update.effective_user.id

    cursor.execute("SELECT date FROM birthdays WHERE user_id = ? AND name = ?", (user_id, name))
    birthday = cursor.fetchone()

    if birthday:
        birthday_date = datetime.strptime(birthday[0], "%d.%m.%Y")

        # Создаем ссылку для добавления события в Google Календарь
        event_name = f"День рождения {name}"
        event_details = f"Сегодня день рождения у {name}!"
        event_date = birthday_date.strftime("%Y%m%d")

        base_url = "https://www.google.com/calendar/render"
        event_params = {
            "action": "TEMPLATE",
            "text": event_name,
            "details": event_details,
            "dates": f"{event_date}/{event_date}",
            "recur": "RRULE:FREQ=YEARLY"
        }
        calendar_url = f"{base_url}?{urllib.parse.urlencode(event_params)}"

        # Создаем кнопку с ссылкой
        keyboard = [[InlineKeyboardButton("Добавить в Google Календарь", url=calendar_url)]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(
            f"Нажмите на кнопку ниже, чтобы добавить напоминание о дне рождения {name} в ваш Google Календарь:",
            reply_markup=reply_markup
        )
    else:
        await query.edit_message_text(f"День рождения для {name} не найден.")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    state = context.user_data.get('state')

    if state == 'waiting_name':
        context.user_data['name'] = update.message.text
        await update.message.reply_text("Введите дату рождения в формате ДД.ММ.ГГГГ:")
        context.user_data['state'] = 'waiting_date'
    elif state == 'waiting_date':
        date_text = update.message.text
        try:
            date = datetime.strptime(date_text, "%d.%m.%Y")
            formatted_date = date.strftime("%d.%m.%Y")
            name = context.user_data['name']
            try:
                cursor.execute("INSERT INTO birthdays (user_id, name, date) VALUES (?, ?, ?)",
                               (user_id, name, formatted_date))
                conn.commit()
                await update.message.reply_text(f"День рождения {name} успешно сохранен!")
            except sqlite3.Error as e:
                await update.message.reply_text(f"Произошла ошибка при сохранении в базу данных: {e}")
        except ValueError:
            await update.message.reply_text("Неверный формат даты. Попробуйте еще раз (ДД.ММ.ГГГГ):")
            return
        del context.user_data['state']
        await start(update, context)
    elif state == 'waiting_interests':
        interests = update.message.text
        name = context.user_data['selected_name']
        try:
            completion = client.chat.completions.create(
                model="google/gemini-flash-1.5",
                messages=[
                    {"role": "user",
                     "content": f"Создайте короткое! уникальное поздравление с днем рождения для {name}. Его/Её интересы: {interests}. При поздравлении нужно учитывать пол человека которого ты поздравляешь. Старайся делать такие поздравления, чтобы это было не кринжово. Правильно склоняй имена и фамилии. Если в {name} есть фамилия то обращайся исключительно на 'вы'",
                     },
                ],
            )
            greeting = completion.choices[0].message.content
            await update.message.reply_text(f"Вот индивидуальное поздравление для {name}:\n\n{greeting}")
        except Exception as e:
            await update.message.reply_text(f"Произошла ошибка при генерации поздравления: {e}")
        del context.user_data['state']
        del context.user_data['selected_name']
        await start(update, context)
    else:
        await start(update, context)


async def generate_greeting(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    name = query.data.split('_')[1]
    context.user_data['selected_name'] = name
    context.user_data['state'] = 'waiting_interests'
    await query.edit_message_text(f"Введите интересы и увлечения {name} для создания индивидуального поздравления:")


async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    print(f"Произошла ошибка: {context.error}")


def main() -> None:
    application = Application.builder().token(os.getenv("TELEGRAM_BOT_TOKEN")).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(add_to_calendar, pattern=r'^cal_'))
    application.add_handler(CallbackQueryHandler(generate_greeting, pattern=r'^gen_'))
    application.add_handler(CallbackQueryHandler(button))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    application.add_error_handler(error_handler)

    application.run_polling()


if __name__ == '__main__':
    main()