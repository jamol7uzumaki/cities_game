import asyncio
from datetime import date
import logging
import os
import sqlite3
from aiohttp import web
from aiogram import Bot, Dispatcher, F
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.types import Message

# Настройка логов
logging.basicConfig(level=logging.INFO)

# ТОКЕН БОТА (тянется из переменных окружения Render)
BOT_TOKEN = os.getenv("BOT_TOKEN", "9008129962:AAF6Ubj8ABuRkfB1mdWoLlGlUrjWFUz86rA")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# ------------------------------------------------------------------
# 1. СЛОВАРЬ СТРАН (Все строго в нижнем регистре!)
# ------------------------------------------------------------------
VALID_COUNTRIES = {
    "австралия", "австрия", "азербайджан", "албания", "алжир", "ангола",
    "андорра", "антигуа и барбуда", "аргентина", "армения", "афганистан",
    "багамы", "бангладеш", "барбадос", "бахрейн", "беларусь", "белиз", "бельгия",
    "бенин", "болгария", "боливия", "босния и герцеговина", "ботсвана", "бразилия",
    "бруней", "буркина-фасо", "бурунди", "бутан", "вануату", "ватикан", "великобритания",
    "венгрия", "венесуэла", "вьетнам", "габон", "гаити", "гайана", "гамбия",
    "гана", "гватемала", "гвинея", "гвинея-бисау", "германия", "гондурас",
    "гренада", "греция", "грузия", "дания", "джибути", "доминика", "доминиканская республика",
    "египет", "замбия", "зимбабве", "израиль", "индия", "индонезия", "иордания",
    "ирак", "иран", "ирландия", "исландия", "испания", "италия", "йемен",
    "кабо-верде", "казахстан", "камбоджа", "камерун", "канада", "катар",
    "кения", "кипр", "кирибати", "китай", "колумбия", "коморы", "конго",
    "корея", "косово", "коста-рика", "кот-д'ивуар", "куба", "кувейт", "кыргызстан",
    "лаос", "латвия", "лесото", "либерия", "ливан", "ливия", "литва", "лихтенштейн",
    "люксембург", "маврикий", "мавритания", "мадагаскар", "малави", "малайзия",
    "мальдивы", "мальта", "марокко", "маршалловы острова", "мексика", "микронезия",
    "мозамбик", "молдова", "монако", "монголия", "мьянма", "намибия", "науру",
    "непал", "нигер", "нигерия", "нидерланды", "никарагуа", "новая зеландия",
    "норвегия", "объединенные арабские эмираты", "оман", "пакистан", "палау",
    "палестина", "панама", "папуа — нова гвинея", "парагвай", "перу", "польша",
    "португалия", "российская федерация", "руанда", "румыния", "сальвадор",
    "самоа", "сан-марино", "сан-томе и принсипи", "саудовская аравия", "северная македония",
    "сейшелы", "сенегал", "сербия", "сингпур", "сирия", "словакия", "словения",
    "соединенное королевство", "соединенные штаты америки", "соломоновы острова",
    "сомали", "судан", "суринам", "сьерра-леоне", "таджикистан", "таиланд",
    "танзания", "тимор-лешти", "того", "тонга", "тринидад и тобаго", "тувалу",
    "тунис", "туркменистан", "турция", "уганда", "узбекистан", "украина", "уругвай",
    "фиджи", "филиппины", "финляндия", "франция", "хорватия", "центральноафриканская республика",
    "чад", "черногория", "чехия", "чили", "швейцария", "швеция", "шри-ланка",
    "эквадор", "экваториальная гвинея", "эритрея", "эстония", "эфиопия",
    "южная африка", "южный судан", "ямайка", "япония"
}


# ------------------------------------------------------------------
# 2. ИНИЦИАЛИЗАЦИЯ БАЗЫ ДАННЫХ
# ------------------------------------------------------------------
def init_db():
  conn = sqlite3.connect("bot_database.db")
  cursor = conn.cursor()

  cursor.execute("""
        CREATE TABLE IF NOT EXISTS game_state (
            chat_id INTEGER PRIMARY KEY,
            current_letter TEXT,
            last_country TEXT
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
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            countries_count INTEGER DEFAULT 0,
            fish INTEGER DEFAULT 0,
            last_date TEXT
        )
    """)

  conn.commit()
  conn.close()


init_db()


# ------------------------------------------------------------------
# 3. ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ------------------------------------------------------------------
def get_seal_rank(count: int):
  if count >= 300:
    return "👑 Морской владыка (Великий Тюлень)", 5
  elif count >= 150:
    return "⚡ Альфа-тюлень", 4
  elif count >= 50:
    return "🐟 Голодный тюлень", 3
  elif count >= 11:
    return "🐾 Пышный тюлень", 2
  else:
    return "🥚 Лежачий тюленёнок", 1


def get_next_valid_letter(country_name: str, chat_id: int, cursor) -> str:
  """Определяет следующую букву по правилам, включая логику исчерпания буквы 'Я'."""
  ignored = {"ь", "ъ", "ы", "й"}
  name_lower = country_name.lower()

  # Находим базовую последнюю букву (игнорируя Ь, Ъ, Ы, Й)
  candidate = None
  for char in reversed(name_lower):
    if char not in ignored and char.isalpha():
      candidate = char.upper()
      break

  if not candidate:
    candidate = country_name[-1].upper()

  # ПРАВИЛО 3: Если выпала буква «Я», проверяем, остались ли еще неиспользованные страны на «Я»
  if candidate == "Я":
    cursor.execute(
        "SELECT country FROM used_countries WHERE chat_id = ?", (chat_id,)
    )
    used = {row[0] for row in cursor.fetchall()}
    yan_countries = {c for c in VALID_COUNTRIES if c.startswith("я")}
    unused_yan = yan_countries - used

    # Если все страны на «Я» (Япония, Ямайка и т.д.) уже закончились в этом чате:
    if not unused_yan:
      # Берем букву перед «Я» в текущем слове
      stripped = name_lower.rstrip("я")
      for char in reversed(stripped):
        if char not in ignored and char.isalpha():
          return char.upper()

  return candidate


# ------------------------------------------------------------------
# 4. КОМАНДЫ
# ------------------------------------------------------------------
@dp.message(Command("start"))
@dp.message(Command("help"))
async def cmd_start(message: Message):
  await message.answer(
      "🦭 **Привет! Я бот для игры в Страны!**\n\n"
      "🔹 Добавь меня в чат и напиши `/countries`, чтобы начать игру.\n"
      "🔹 Напиши `/profile` в ЛС, чтобы узнать свой тюлений ранг и сколько рыбы"
      " ты собрал!",
      parse_mode=ParseMode.MARKDOWN,
  )


@dp.message(Command("profile"))
async def cmd_profile(message: Message):
  user_id = message.from_user.id

  conn = sqlite3.connect("bot_database.db")
  cursor = conn.cursor()
  cursor.execute(
      "SELECT countries_count, fish FROM users WHERE user_id = ?", (user_id,)
  )
  user_data = cursor.fetchone()
  conn.close()

  if not user_data or user_data[0] == 0:
    await message.answer(
        "🦭 У тебя еще нет статистики! Назови хотя бы одну страну в игровом"
        " чате, чтобы зарегистрировать своего тюленя."
    )
    return

  countries_count, fish = user_data
  rank_title, _ = get_seal_rank(countries_count)

  profile_text = (
      f"🦭 **Профиль тюленя: {message.from_user.first_name}**\n\n"
      f"🎖 **Ранг:** {rank_title}\n"
      f"🐟 **Собрано рыбы:** {fish}\n"
      f"🌍 **Всего названо стран:** {countries_count}\n\n"
      f"_«Этот тюлень уверенно покоряет географическую карту мира!»_"
  )
  await message.answer(profile_text, parse_mode=ParseMode.MARKDOWN)


@dp.message(Command("countries"))
async def cmd_countries(message: Message):
  chat_id = message.chat.id

  conn = sqlite3.connect("bot_database.db")
  cursor = conn.cursor()

  cursor.execute(
      "INSERT OR REPLACE INTO game_state (chat_id, current_letter,"
      " last_country) VALUES (?, NULL, NULL)",
      (chat_id,),
  )
  cursor.execute("DELETE FROM used_countries WHERE chat_id = ?", (chat_id,))
  conn.commit()
  conn.close()

  rules_text = (
      "🗺 **Игра в страны началась!**\n\n"
      "Правила простые:\n"
      "1. Пишите название реальной страны.\n"
      "2. Каждая следующая страна должна начинаться на ту же букву, которой"
      " заканчивалась предыдущая (Ь, Ъ, Ы, Й пропускаются).\n"
      "3. Буква «Я» работает для стран на эту букву (Япония, Ямайка)."
      " Когда они заканчиваются, игра автоматически берет букву перед ней!\n"
      "4. Одну и ту же страну нельзя назвать повторно в этом чате.\n\n"
      "Любой участник может написать первую страну, чтобы запустить цепочку!"
  )
  await message.answer(rules_text, parse_mode=ParseMode.MARKDOWN)


# ------------------------------------------------------------------
# 5. ОСНОВНОЙ ХЕНДЛЕР ХОДОВ ИГРЫ
# ------------------------------------------------------------------
@dp.message(F.text & ~F.text.startswith("/"))
async def handle_country_message(message: Message):
  if message.chat.type == "private":
    return

  chat_id = message.chat.id
  text_clean = message.text.strip().lower()

  if text_clean not in VALID_COUNTRIES:
    return

  conn = sqlite3.connect("bot_database.db")
  cursor = conn.cursor()

  cursor.execute(
      "SELECT current_letter, last_country FROM game_state WHERE chat_id = ?",
      (chat_id,),
  )
  state = cursor.fetchone()

  if not state:
    conn.close()
    return

  current_letter, last_country = state

  if current_letter and not text_clean.startswith(current_letter.lower()):
    conn.close()
    await message.reply(
        f"❌ Страна должна начинаться на букву **«{current_letter}»**!",
        parse_mode=ParseMode.MARKDOWN,
    )
    return

  cursor.execute(
      "SELECT 1 FROM used_countries WHERE chat_id = ? AND country = ?",
      (chat_id, text_clean),
  )
  if cursor.fetchone():
    conn.close()
    await message.reply(
        "❌ Эта страна уже была названа в этом чате! Назовите другую."
    )
    return

  cursor.execute(
      "INSERT INTO used_countries (chat_id, country) VALUES (?, ?)",
      (chat_id, text_clean),
  )

  # Определяем следующую букву с учетом правила «Я»
  next_letter = get_next_valid_letter(text_clean, chat_id, cursor)
  formatted_country = text_clean.capitalize()

  cursor.execute(
      "UPDATE game_state SET current_letter = ?, last_country = ? WHERE chat_id"
      " = ?",
      (next_letter, formatted_country, chat_id),
  )

  # --- ОБНОВЛЯЕМ ПРОФИЛЬ И ТЮЛЕНЬИ ОЧКИ ИГРОКА ---
  user_id = message.from_user.id
  username = message.from_user.username or message.from_user.first_name
  today_str = str(date.today())

  cursor.execute(
      "SELECT countries_count, fish FROM users WHERE user_id = ?", (user_id,)
  )
  user_data = cursor.fetchone()

  if not user_data:
    new_count = 1
    new_fish = 1
    cursor.execute(
        "INSERT INTO users (user_id, username, countries_count, fish,"
        " last_date) VALUES (?, ?, 1, 1, ?)",
        (user_id, username, today_str),
    )
  else:
    new_count = user_data[0] + 1
    new_fish = user_data[1] + 1
    cursor.execute(
        "UPDATE users SET countries_count = ?, fish = ?, username = ? WHERE"
        " user_id = ?",
        (new_count, new_fish, username, user_id),
    )

  conn.commit()
  conn.close()

  rank_title, _ = get_seal_rank(new_count)

  await message.reply(
      f"✅ Принято: **{formatted_country}**!\n"
      f"🐟 +1 рыбка в копилку (Всего: {new_fish})\n"
      f"🦭 Ранг: *{rank_title}*\n\n"
      f"Следующий игрок называет страну на букву: **«{next_letter}»** 🔠",
      parse_mode=ParseMode.MARKDOWN,
  )


# ------------------------------------------------------------------
# 6. ВЕБ-СЕРВЕР ДЛЯ RENDER И ЗАПУСК ПОЛЛИНГА
# ------------------------------------------------------------------
async def handle_ping(request):
  return web.Response(text="Bot is running!")


async def main():
  app = web.Application()
  app.router.add_get("/", handle_ping)

  port = int(os.environ.get("PORT", 8080))
  runner = web.AppRunner(app)
  await runner.setup()
  site = web.TCPSite(runner, "0.0.0.0", port)
  await site.start()
  logging.info(f"Веб-сервер успешно запущен на порту {port}")

  await dp.start_polling(bot)


if __name__ == "__main__":
  asyncio.run(main())