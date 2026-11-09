import asyncio
from datetime import date
import logging
import os
from aiohttp import web
from aiogram import Bot, Dispatcher, F
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.types import Message
import asyncpg

# Настройка логов
logging.basicConfig(level=logging.INFO)

# ТОКЕН БОТА И DATABASE_URL (подтягиваются из переменных окружения Render)
BOT_TOKEN = os.getenv("BOT_TOKEN", "9008129962:AAE4CDcurhzo3PnYLn__w6pjiKzUwKx_sUw")
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://neondb_owner:npg_mqBb0pvYCE3V@ep-bitter-dew-b9yq2udd-pooler.c-7.eu-central-1.aws.neon.tech/neondb?sslmode=require")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
db_pool = None

# ------------------------------------------------------------------
# 1. СЛОВАРЬ СТРАН
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
# 2. ИНИЦИАЛИЗАЦИЯ БАЗЫ ДАННЫХ (PostgreSQL)
# ------------------------------------------------------------------
async def init_db():
  global db_pool
  if not DATABASE_URL:
    raise ValueError("Не задана переменная окружения DATABASE_URL!")

  # Очищаем параметр channel_binding если он есть, чтобы asyncpg не ругался
  clean_url = DATABASE_URL.split("&")[0].split("?")[0]
  if "?" in DATABASE_URL and "sslmode" in DATABASE_URL:
    # Сохраняем sslmode если нужно
    pass

  db_pool = await asyncpg.create_pool(dsn=DATABASE_URL, ssl="require")

  async with db_pool.acquire() as conn:
    await conn.execute("""
            CREATE TABLE IF NOT EXISTS game_state (
                chat_id BIGINT PRIMARY KEY,
                current_letter TEXT,
                last_country TEXT
            );
            CREATE TABLE IF NOT EXISTS used_countries (
                chat_id BIGINT,
                country TEXT,
                PRIMARY KEY (chat_id, country)
            );
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY,
                username TEXT,
                countries_count INT DEFAULT 0,
                fish INT DEFAULT 0,
                last_date TEXT
            );
        """)
  logging.info("Успешное подключение к PostgreSQL на Neon!")


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


async def get_next_valid_letter(
    country_name: str, chat_id: int, conn
) -> str:
  ignored = {"ь", "ъ", "ы", "й"}
  name_lower = country_name.lower()

  candidate = None
  for char in reversed(name_lower):
    if char not in ignored and char.isalpha():
      candidate = char.upper()
      break

  if not candidate:
    candidate = country_name[-1].upper()

  if candidate == "Я":
    rows = await conn.fetch(
        "SELECT country FROM used_countries WHERE chat_id = $1", chat_id
    )
    used = {r["country"] for r in rows}
    yan_countries = {c for c in VALID_COUNTRIES if c.startswith("я")}
    unused_yan = yan_countries - used

    if not unused_yan:
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

  async with db_pool.acquire() as conn:
    user_data = await conn.fetchrow(
        "SELECT countries_count, fish FROM users WHERE user_id = $1", user_id
    )

  if not user_data or user_data["countries_count"] == 0:
    await message.answer(
        "🦭 У тебя еще нет статистики! Назови хотя бы одну страну в игровом"
        " чате, чтобы зарегистрировать своего тюленя."
    )
    return

  countries_count = user_data["countries_count"]
  fish = user_data["fish"]
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

  async with db_pool.acquire() as conn:
    await conn.execute(
        """
            INSERT INTO game_state (chat_id, current_letter, last_country) 
            VALUES ($1, NULL, NULL)
            ON CONFLICT (chat_id) DO UPDATE 
            SET current_letter = NULL, last_country = NULL
        """,
        chat_id,
    )
    await conn.execute(
        "DELETE FROM used_countries WHERE chat_id = $1", chat_id
    )

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

  async with db_pool.acquire() as conn:
    state = await conn.fetchrow(
        "SELECT current_letter, last_country FROM game_state WHERE chat_id ="
        " $1",
        chat_id,
    )

    if not state:
      return

    current_letter = state["current_letter"]

    if current_letter and not text_clean.startswith(current_letter.lower()):
      await message.reply(
          f"❌ Страна должна начинаться на букву **«{current_letter}»**!",
          parse_mode=ParseMode.MARKDOWN,
      )
      return

    used_check = await conn.fetchrow(
        "SELECT 1 FROM used_countries WHERE chat_id = $1 AND country = $2",
        chat_id,
        text_clean,
    )
    if used_check:
      await message.reply(
          "❌ Эта страна уже была названа в этом чате! Назовите другую."
      )
      return

    await conn.execute(
        "INSERT INTO used_countries (chat_id, country) VALUES ($1, $2)",
        chat_id,
        text_clean,
    )

    next_letter = await get_next_valid_letter(text_clean, chat_id, conn)
    formatted_country = text_clean.capitalize()

    await conn.execute(
        "UPDATE game_state SET current_letter = $1, last_country = $2 WHERE"
        " chat_id = $3",
        next_letter,
        formatted_country,
        chat_id,
    )

    # Обновляем профиль игрока
    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name
    today_str = str(date.today())

    user_data = await conn.fetchrow(
        "SELECT countries_count, fish FROM users WHERE user_id = $1", user_id
    )

    if not user_data:
      new_count = 1
      new_fish = 1
      await conn.execute(
          "INSERT INTO users (user_id, username, countries_count, fish,"
          " last_date) VALUES ($1, $2, 1, 1, $3)",
          user_id,
          username,
          today_str,
      )
    else:
      new_count = user_data["countries_count"] + 1
      new_fish = user_data["fish"] + 1
      await conn.execute(
          "UPDATE users SET countries_count = $1, fish = $2, username = $3"
          " WHERE user_id = $4",
          new_count,
          new_fish,
          username,
          user_id,
      )

  rank_title, _ = get_seal_rank(new_count)

  await message.reply(
      f"✅ Принято: **{formatted_country}**!\n"
      f"🐟 +1 рыбка в копилку (Всего: {new_fish})\n"
      f"🦭 Ранг: *{rank_title}*\n\n"
      f"Следующий игрок называет страну на букву: **«{next_letter}»** 🔠",
      parse_mode=ParseMode.MARKDOWN,
  )


# ------------------------------------------------------------------
# 6. ВЕБ-СЕРВЕР ДЛЯ RENDER И ЗАПУСК
# ------------------------------------------------------------------
async def handle_ping(request):
  return web.Response(text="Bot is running!")


async def main():
  await init_db()

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