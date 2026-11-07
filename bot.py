import os
import http.server
import socketserver
import threading

# Запускаем фиктивный веб-сервер для Render с защитой от ошибки занятого порта
def run_dummy_server():
    port = int(os.environ.get("PORT", 10000))
    handler = http.server.SimpleHTTPRequestHandler
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("", port), handler) as httpd:
        httpd.serve_forever()

threading.Thread(target=run_dummy_server, daemon=True).start()

TOKEN = os.getenv("BOT_TOKEN") or "9008129962:AAF6UbJ8ABuRkfB1mdwoLlGlUrJfWZ86rA"

import asyncio
import logging
import sqlite3
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.types import Message

# Инициализация базы данных SQLite для групп
def init_db():
    conn = sqlite3.connect("countries_game.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS game_state (
            chat_id INTEGER PRIMARY KEY,
            current_country TEXT,
            last_letter TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS used_countries (
            chat_id INTEGER,
            country TEXT,
            PRIMARY KEY (chat_id, country)
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

# База данных реальных стран (названия в нижнем регистре)
VALID_COUNTRIES = {
        "Алжир", "Ангола", "Бенин", "Ботсвана", "Буркина-Фасо",
        "Бурунди", "Габон", "Гамбия", "Гана", "Гвинея", "Гвинея-Бисау",
        "Джибути", "Египет", "Замбия", "Зимбабве", "Кабо-Верде",
        "Камерун", "Кения", "Коморы", "Республика Конго", "Демократическая Республика Конго",
        "Кот-д'Ивуар", "Лесото", "Либерия", "Ливия", "Маврикий",
        "Мавритания", "Мадагаскар", "Малави", "Мали", "Марокко",
        "Мозамбик", "Намибия", "Нигер", "Нигерия", "Руанда", "Сан-Томе и Принсипи",
        "Сейшелы", "Сенегал", "Сомали", "Судан", "Сьерра-Леоне",
        "Танзания", "Того", "Тунис", "Уганда", "Центральноафриканская Республика",
        "Чад", "Экваториальная Гвинея", "Эритрея", "Эсватини",
        "Эфиопия", "ЮАР", "Южный Судан", "Антигуа и Барбуда",
        "Аргентина", "Багамы", "Барбадос", "Белиз", "Боливия",
        "Бразилия", "Венесуэла", "Гайана", "Гватемала", "Гондурас",
        "Гренада", "Доминика", "Доминиканская Республика", "Канада",
        "Колумбия", "Коста-Рика", "Куба", "Мексика", "Никарагуа",
        "Панама", "Парагвай", "Перу", "Сальвадор", "Сент-Винсент и Гренадины",
        "Сент-Люсия", "Сент-Китс и Невис", "Суринам", "США", "Тринидад и Тобаго",
        "Уругвай", "Чили", "Эквадор", "Ямайка", "Азербайджан",
        "Армения", "Афганистан", "Бангладеш", "Бахрейн", "Бруней",
        "Бутан", "Вьетнам", "Грузия", "Израиль", "Индия", "Индонезия",
        "Иордания", "Ирак", "Иран", "Йемен", "Казахстан", "Камбоджа",
        "Катар", "Кипр", "Киргизия", "Китай", "КНДР", "Кувейт", "Лаос",
        "Ливан", "Малайзия", "Мальдивы", "Монголия", "Мьянма", "Непал",
        "ОАЭ", "Оман", "Пакистан", "Россия", "Саудовская Аравия",
        "Сингапур", "Сирия", "Таджикистан", "Таиланд", "Тимор-Лесте",
        "Туркменистан", "Турция", "Узбекистан", "Филиппины", "Шри-Ланка",
        "Южная Корея", "Япония", "Палестина", "Албания", "Андорра",
        "Австрия", "Беларусь", "Бельгия", "Болгария", "Босния и Герцеговина",
        "Ватикан", "Великобритания", "Венгрия", "Германия", "Греция", "Дания",
        "Ирландия", "Исландия", "Испания", "Италия", "Латвия", "Литва", "Лихтенштейн",
        "Люксембург", "Мальта", "Молдова", "Монако", "Нидерланды",
        "Норвегия", "Польша", "Португалия", "Румыния", "Сан-Марино",
        "Северная Македония", "Сербия", "Словакия", "Словения",
        "Украина", "Финляндия", "Франция", "Хорватия", "Черногория",
        "Чехия", "Швейцария", "Швеция", "Эстония", "Австралия", "Вануату",
        "Кирибати", "Маршалловы Острова", "Микронезия", "Науру",
        "Новая Зеландия", "Палау", "Папуа — Новая Гвинея", "Самоа",
        "Соломоновы Острова", "Тонга", "Тувалу", "Фиджи"
    }

# Функция для вычисления следующей буквы с умной логикой для «Я»
SUPPRESS_LETTERS = {'ь', 'ъ', 'ы', 'й'}

def get_next_letter(chat_id: int, country: str, cursor) -> str:
    country = country.lower().strip()
    
    last_char = None
    for char in reversed(country):
        if char not in SUPPRESS_LETTERS:
            last_char = char
            break
    if not last_char:
        last_char = country[-1]
        
    if last_char == 'я':
        ya_countries = {c for c in VALID_COUNTRIES if c.startswith('я')}
        cursor.execute("SELECT country FROM used_countries WHERE chat_id = ?", (chat_id,))
        used_rows = cursor.fetchall()
        used_set = {row[0] for row in used_rows}
        unused_ya = ya_countries - used_set
        
        if unused_ya:
            return 'я'
        else:
            found_ya = False
            for char in reversed(country):
                if char == 'я' and not found_ya:
                    found_ya = True
                    continue
                if found_ya and char not in SUPPRESS_LETTERS:
                    return char
            return country[-1]
            
    return last_char

dp = Dispatcher()

@dp.message(Command("start_countries", "countries", "cities"))
async def cmd_start_countries(message: Message):
    if message.chat.type == "private":
        await message.answer("Эта игра предназначена для групповых чатов! Добавьте меня в группу.")
        return
    
    chat_id = message.chat.id
    
    conn = sqlite3.connect("countries_game.db")
    cursor = conn.cursor()
    cursor.execute("DELETE FROM game_state WHERE chat_id = ?", (chat_id,))
    cursor.execute("DELETE FROM used_countries WHERE chat_id = ?", (chat_id,))
    cursor.execute("""
        INSERT INTO game_state (chat_id, current_country, last_letter) 
        VALUES (?, NULL, NULL)
    """, (chat_id,))
    conn.commit()
    conn.close()
    
    await message.answer(
        "🗺 **Игра в страны началась!**\n\n"
        "Правила простые:\n"
        "1. Пишите название реальной страны.\n"
        "2. Каждая следующая страна должна начинаться на ту же букву, которой заканчивалась предыдущая (Ь, Ъ, Ы, Й пропускаются).\n"
        "3. Буква **«Я»** работает для стран на эту букву (Япония, Ямайка). Когда обе заканчиваются, игра автоматически берет букву перед ней!\n"
        "4. Одну и ту же страну нельзя назвать повторно в этом чате.\n\n"
        "Любой участник может написать первую страну, чтобы запустить цепочку!"
    )

@dp.message(Command("top", "rating"))
async def cmd_rating(message: Message):
    if message.chat.type == "private":
        return
    
    chat_id = message.chat.id
    conn = sqlite3.connect("countries_game.db")
    cursor = conn.cursor()
    cursor.execute("""
        SELECT username, score FROM players 
        WHERE chat_id = ? ORDER BY score DESC LIMIT 10
    """, (chat_id,))
    top_players = cursor.fetchall()
    conn.close()
    
    if not top_players:
        await message.answer("🏆 В этом чате пока нет участников с очками. Начните игру командой /countries!")
        return
    
    text = "🏆 **Рейтинг игроков в странах:**\n\n"
    for i, (uname, score) in enumerate(top_players, 1):
        name = uname if uname else "Аноним"
        text += f"{i}. {name} — {score} очков\n"
        
    await message.answer(text)

@dp.message(F.text & ~F.text.startswith("/"))
async def handle_country_message(message: Message):
    if message.chat.type == "private":
        return

    chat_id = message.chat.id
    text_clean = message.text.strip().lower()
    
    conn = sqlite3.connect("countries_game.db")
    cursor = conn.cursor()
    
    cursor.execute("SELECT current_country, last_letter FROM game_state WHERE chat_id = ?", (chat_id,))
    state = cursor.fetchone()
    
    if not state:
        conn.close()
        return  
    
    current_country, required_letter = state
    country_name = text_clean.capitalize()
    
    if text_clean not in VALID_COUNTRIES:
        conn.close()
        await message.reply("❌ Такой страны нет в моем словаре! Попробуйте другую.")
        return

    if required_letter is not None:
        if text_clean[0] != required_letter:
            conn.close()
            await message.reply(f"❌ Неправильно! Страна должна начинаться на букву **«{required_letter.upper()}»**.")
            return

    cursor.execute("SELECT 1 FROM used_countries WHERE chat_id = ? AND country = ?", (chat_id, text_clean))
    if cursor.fetchone():
        conn.close()
        await message.reply("⚠️ Эту страну уже называли в данной игре!")
        return

    new_last_letter = get_next_letter(chat_id, text_clean, cursor)

    cursor.execute("INSERT OR IGNORE INTO used_countries (chat_id, country) VALUES (?, ?)", (chat_id, text_clean))
    cursor.execute("UPDATE game_state SET current_country = ?, last_letter = ? WHERE chat_id = ?", 
                   (text_clean, new_last_letter, chat_id))
    
    user = message.from_user
    username = user.username or user.first_name
    cursor.execute("""
        INSERT INTO players (chat_id, user_id, username, score) 
        VALUES (?, ?, ?, 1)
        ON CONFLICT(chat_id, user_id) DO UPDATE SET score = score + 1
    """, (chat_id, user.id, username))
    
    conn.commit()
    conn.close()

    await message.react([types.ReactionTypeEmoji(emoji="👍")])
    await message.reply(
        f"✅ Принято: **{country_name}**!\n"
        f"Следующий игрок называет страну на букву: **«{new_last_letter.upper()}»** 🔠"
    )

async def main():
    logging.basicConfig(level=logging.INFO)
    bot = Bot(token=TOKEN)
    await bot.delete_webhook(drop_pending_updates=True)
    print("Бот запущен...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())