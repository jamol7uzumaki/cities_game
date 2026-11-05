import os
TOKEN = os.getenv("BOT_TOKEN") or "9008129962:AAF6UbJ8ABuRkfB1mdwoLlGlUrJfWZ86rA"
import asyncio
import logging
import sqlite3
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.types import Message

# Инициализация базы данных SQLite для групп
def init_db():
    conn = sqlite3.connect("cities_game.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS game_state (
            chat_id INTEGER PRIMARY KEY,
            current_city TEXT,
            last_letter TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS used_cities (
            chat_id INTEGER,
            city TEXT,
            PRIMARY KEY (chat_id, city)
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS players (
            chat_id INTEGER,
            user_id INTEGER,
            username TEXT,
            score INTEGER DEFAULT 0,
            PRIMARY KEY (chat_id, user_id)
        )
    """)
    conn.commit()
    conn.close()

init_db()

# Функция для получения последней рабочей буквы (игнорируем Ь, Ъ, Ы, Й)
SUPPRESS_LETTERS = {'ь', 'ъ', 'ы', 'й'}
def get_last_letter(city: str) -> str:
    city = city.lower().strip()
    for char in reversed(city):
        if char not in SUPPRESS_LETTERS:
            return char
    return city[-1]

# База данных реальных городов
VALID_CITIES = {
    "самарканд", "ташкент", "бухара", "хива", "навои", "карши", "нукус", "андижан", "фергана", "наманган",
    "москва", "петербург", "александрия", "ярославль", "лиссабон", "ницца", "астана", 
    "амстердам", "мадрид", "дамаск", "киев", "вена", "анкара", "афины", "стокгольм", 
    "каир", "рига", "архангельск", "лондон", "париж", "берлин", "рим", "токио", 
    "пекин", "сеул", "дубай", "доха", "сингапур", "баку", "ереван", "тбилиси", "минск", "краснодар"
}

dp = Dispatcher()

@dp.message(Command("start_cities", "cities"))
async def cmd_start_cities(message: Message):
    if message.chat.type == "private":
        await message.answer("Эта игра предназначена для групповых чатов! Добавьте меня в группу.")
        return
    
    chat_id = message.chat.id
    
    conn = sqlite3.connect("cities_game.db")
    cursor = conn.cursor()
    cursor.execute("DELETE FROM game_state WHERE chat_id = ?", (chat_id,))
    cursor.execute("DELETE FROM used_cities WHERE chat_id = ?", (chat_id,))
    cursor.execute("""
        INSERT INTO game_state (chat_id, current_city, last_letter) 
        VALUES (?, NULL, NULL)
    """, (chat_id,))
    conn.commit()
    conn.close()
    
    await message.answer(
        "🏙 **Игра в города началась!**\n\n"
        "Правила простые:\n"
        "1. Пишите название реального города.\n"
        "2. Каждый следующий город должен начинаться на ту же букву, которой заканчивался предыдущий (буквы Ь, Ъ, Ы, Й пропускаются).\n"
        "3. Один и тот же город нельзя назвать повторно в этом чате.\n\n"
        "Любой участник может написать первый город, чтобы запустить цепочку!"
    )

@dp.message(Command("top", "rating"))
async def cmd_rating(message: Message):
    if message.chat.type == "private":
        return
    
    chat_id = message.chat.id
    conn = sqlite3.connect("cities_game.db")
    cursor = conn.cursor()
    cursor.execute("""
        SELECT username, score FROM players 
        WHERE chat_id = ? ORDER BY score DESC LIMIT 10
    """, (chat_id,))
    top_players = cursor.fetchall()
    conn.close()
    
    if not top_players:
        await message.answer("🏆 В этом чате пока нет участников с очками. Начните игру командой /cities!")
        return
    
    text = "🏆 **Рейтинг игроков в городах:**\n\n"
    for i, (uname, score) in enumerate(top_players, 1):
        name = uname if uname else "Аноним"
        text += f"{i}. {name} — {score} очков\n"
        
    await message.answer(text)

@dp.message(F.text & ~F.text.startswith("/"))
async def handle_city_message(message: Message):
    if message.chat.type == "private":
        return

    chat_id = message.chat.id
    text_clean = message.text.strip().lower()
    
    conn = sqlite3.connect("cities_game.db")
    cursor = conn.cursor()
    
    cursor.execute("SELECT current_city, last_letter FROM game_state WHERE chat_id = ?", (chat_id,))
    state = cursor.fetchone()
    
    if not state:
        conn.close()
        return  # Игра не запущена в этом чате
    
    current_city, required_letter = state
    city_name = text_clean.capitalize()
    
    # 1. Проверка: существует ли такой город в нашей базе
    if text_clean not in VALID_CITIES:
        conn.close()
        await message.reply("❌ Такого города нет в моем словаре (или это не город)! Попробуйте другой.")
        return

    # 2. Проверка первой буквы (если это не первый ход)
    if required_letter is not None:
        if text_clean[0] != required_letter:
            conn.close()
            await message.reply(f"❌ Неправильно! Город должен начинаться на букву **«{required_letter.upper()}»**.")
            return

    # 3. Проверка, назывался ли город ранее в этом чате
    cursor.execute("SELECT 1 FROM used_cities WHERE chat_id = ? AND city = ?", (chat_id, text_clean))
    if cursor.fetchone():
        conn.close()
        await message.reply("⚠️ Этот город уже называли в данной игре!")
        return

    # Вычисляем новую требуемую букву
    new_last_letter = get_last_letter(text_clean)

    # Сохраняем и обновляем состояние
    cursor.execute("INSERT OR IGNORE INTO used_cities (chat_id, city) VALUES (?, ?)", (chat_id, text_clean))
    cursor.execute("UPDATE game_state SET current_city = ?, last_letter = ? WHERE chat_id = ?", 
                   (text_clean, new_last_letter, chat_id))
    
    # Начисляем очки игроку
    user = message.from_user
    username = user.username or user.first_name
    cursor.execute("""
        INSERT INTO players (chat_id, user_id, username, score) 
        VALUES (?, ?, ?, 1)
        ON CONFLICT(chat_id, user_id) DO UPDATE SET score = score + 1
    """, (chat_id, user.id, username))
    
    conn.commit()
    conn.close()

    # Успешный ответ
    await message.react([types.ReactionTypeEmoji(emoji="👍")])
    await message.reply(
        f"✅ Принято: **{city_name}**!\n"
        f"Следующий игрок называет город на букву: **«{new_last_letter.upper()}»** 🔠"
    )

async def main():
    logging.basicConfig(level=logging.INFO)
    bot = Bot(token=TOKEN)
    print("Бот запущен...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())