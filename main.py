import os
import sqlite3
import asyncio
import logging
import random
import string
import aiohttp
import html
from aiogram import Bot, Dispatcher, Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, LabeledPrice, PreCheckoutQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest

# --- НАСТРОЙКИ ---
BOT_TOKEN = os.getenv("BOT_TOKEN", "ТВОЙ_ТОКЕН_БОТА")
CRYPTO_BOT_TOKEN = os.getenv("CRYPTO_BOT_TOKEN", "ТВОЙ_ТОКЕН_CRYPTOBOT")
ADMIN_ID = 7727345054
ADMIN_CONTACT = "@nmproda"

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()
router = Router()
logging.basicConfig(level=logging.INFO)

# --- ГЛОБАЛЬНЫЙ ФЛАГ ПАРСИНГА ---
PARSING_ACTIVE = False

# ==============================================================================
# ✨ ПРЕМИУМ ЭМОДЗИ
# ==============================================================================
E_CROWN  = '<tg-emoji emoji-id="5278276646552503661">🏆</tg-emoji>'
E_STORE  = '<tg-emoji emoji-id="5456140674028019486">⚡️</tg-emoji>'
E_SEARCH = '<tg-emoji emoji-id="5199750217586459631">📄</tg-emoji>'
E_MONEY  = '<tg-emoji emoji-id="5373001317042101552">💰</tg-emoji>'
E_CHECK  = '<tg-emoji emoji-id="5206607081334906820">✔️</tg-emoji>'
E_CROSS  = '<tg-emoji emoji-id="5274099962655816924">❗️</tg-emoji>'
E_STAR   = '<tg-emoji emoji-id="5438496463044752972">⭐️</tg-emoji>'
E_FIRE   = '<tg-emoji emoji-id="5801004944211317728">🔥</tg-emoji>'
E_USER   = '<tg-emoji emoji-id="5841276284155467413">👤</tg-emoji>'

# ==============================================================================
# 🗄 БАЗА ДАННЫХ
# ==============================================================================
DB_FILE = "usernames.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS usernames (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            status TEXT DEFAULT 'FREE',
            price INTEGER DEFAULT 0
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            username TEXT,
            price INTEGER
        )
    """)
    conn.commit()
    conn.close()

def is_admin(user_id: int) -> bool:
    return user_id == ADMIN_ID

class AdminState(StatesGroup):
    waiting_for_price = State()

class UserState(StatesGroup):
    waiting_for_search = State()

# ==============================================================================
# 🛠 ГЕНЕРАТОР И ПАРСЕР
# ==============================================================================
def generate_random_username():
    """Генерирует случайный ник от 5 до 10 символов. Первый символ - буква или цифра."""
    length = random.randint(5, 10)
    # Первый символ: только строчные буквы и цифры
    first_char = random.choice(string.ascii_lowercase + string.digits)
    # Остальные символы: буквы, цифры и нижнее подчеркивание
    rest_chars = ''.join(random.choices(string.ascii_lowercase + string.digits + '_', k=length - 1))
    return first_char + rest_chars

async def parse_usernames_task(message: Message):
    global PARSING_ACTIVE
    PARSING_ACTIVE = True
    
    await message.answer(f"{E_FIRE} Парсер запущен. Бот ищет рандомные ники...")
    found_count = 0
    
    while PARSING_ACTIVE:
        uname = generate_random_username()
        
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM usernames WHERE username = ?", (uname,))
        if cursor.fetchone():
            conn.close()
            continue
        
        try:
            # Если ошибки нет, значит ник занят
            await bot.get_chat(f"@{uname}")
        except TelegramBadRequest as e:
            error_text = str(e).lower()
            # Если ник свободен, Telegram выдаст "username not occupied"
            if "username not occupied" in error_text:
                cursor.execute("INSERT INTO usernames (username, status) VALUES (?, 'FREE')", (uname,))
                conn.commit()
                found_count += 1
                
                kb = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="💰 Выставить на витрину", callback_data=f"reserve_{uname}", style="success")]
                ])
                await message.answer(f"{E_CHECK} Найден свободный ник: <code>@{uname}</code>", reply_markup=kb, parse_mode="HTML")
            # Если "chat not found", значит ник либо занят (скрыт), либо не существует. Игнорируем.
        except Exception as e:
            logging.error(f"Ошибка: {e}")
        finally:
            conn.close()
        
        await asyncio.sleep(1.5) 

    await message.answer(f"{E_FIRE} Парсинг остановлен. Найдено новых ников: {found_count}", parse_mode="HTML")

# ==============================================================================
# 👤 ПОЛЬЗОВАТЕЛЬСКАЯ ЧАСТЬ
# ==============================================================================
@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🛒 Витрина (в наличии)", callback_data="show_store", style="success")],
        [InlineKeyboardButton(text="🔍 Поиск свободных", callback_data="search_free", style="primary")]
    ])
    
    text = (
        f"👋 <b>Добро пожаловать в магазин редких юзернеймов!</b>\n\n"
        f"{E_STORE} Здесь ты можешь купить уникальные, свободные никнеймы для своего аккаунта.\n"
        f"{E_CHECK} Все ники в наличии уже зарезервированы админом, тебе не придется беспокоиться, что их украдут.\n\n"
        f"Выбери действие на кнопках ниже:"
    )
    if is_admin(message.from_user.id):
        kb.inline_keyboard.append([InlineKeyboardButton(text="👑 Админ-панель", callback_data="admin_panel", style="danger")])
    
    await message.answer(text, reply_markup=kb, parse_mode="HTML")

@router.callback_query(F.data == "show_store")
async def show_store(callback: CallbackQuery):
    await callback.answer()
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT username, price FROM usernames WHERE status = 'RESERVED' LIMIT 20")
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        await callback.message.edit_text(f"{E_CROSS} Витрина пока пуста. Заходите позже!", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main", style="danger")]]), parse_mode="HTML")
        return

    text = f"{E_STORE} <b>Доступные юзернеймы:</b>\n\n"
    kb = []
    for username, price in rows:
        text += f"• <code>@{username}</code> — {price} ⭐️\n"
        kb.append([InlineKeyboardButton(text=f"Купить @{username} за {price} ⭐️", callback_data=f"buy_{username}_{price}", style="success")])
    
    kb.append([InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main", style="danger")])
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="HTML")

@router.callback_query(F.data == "back_to_main")
async def back_to_main(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await cmd_start(callback.message, state)
    await callback.answer()

@router.callback_query(F.data.startswith("buy_"))
async def buy_username(callback: CallbackQuery):
    data = callback.data.split("_")
    username = data[1]
    price = int(data[2])

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"Оплатить {price} ⭐️ (Stars)", callback_data=f"pay_stars_{username}_{price}", style="primary")],
        [InlineKeyboardButton(text=f"Оплатить CryptoBot ($)", callback_data=f"pay_crypto_{username}_{price}", style="success")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="show_store", style="danger")]
    ])
    
    await callback.message.edit_text(f"💳 Выберите способ оплаты для <code>@{username}</code>:", reply_markup=kb, parse_mode="HTML")
    await callback.answer()

@router.callback_query(F.data.startswith("pay_stars_"))
async def pay_stars(callback: CallbackQuery):
    _, _, username, price = callback.data.split("_")
    price = int(price)

    await bot.send_invoice(
        chat_id=callback.message.chat.id,
        title=f"Покупка @{username}",
        description=f"Уникальный юзернейм для вашего аккаунта.",
        payload=f"username_{username}",
        provider_token="",
        currency="XTR",
        prices=[LabeledPrice(label=f"@{username}", amount=price)]
    )
    await callback.answer()

@router.pre_checkout_query()
async def process_pre_checkout(pre_checkout_query: PreCheckoutQuery):
    await pre_checkout_query.answer(ok=True)

@router.message(F.successful_payment)
async def process_successful_payment(message: Message):
    payload = message.successful_payment.invoice_payload
    if payload.startswith("username_"):
        username = payload.replace("username_", "")
        process_purchase(message.from_user.id, message.from_user.first_name, message.from_user.username, username, message.successful_payment.total_amount, "Stars")

@router.callback_query(F.data.startswith("pay_crypto_"))
async def pay_crypto(callback: CallbackQuery):
    _, _, username, price_stars = callback.data.split("_")
    price_stars = int(price_stars)
    
    usd_price = round(price_stars * 0.02, 2)
    if usd_price < 0.1: usd_price = 0.1

    url = "https://pay.crypt.bot/api/createInvoice"
    headers = {"Crypto-Pay-API-Token": CRYPTO_BOT_TOKEN}
    payload = f"crypto_buy_{username}"
    data = {
        "currency_type": "fiat",
        "fiat": "USD",
        "amount": str(usd_price),
        "payload": payload,
        "description": f"Покупка юзернейма @{username}"
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=data, headers=headers) as resp:
                res = await resp.json()
                if not res.get("ok"):
                    await callback.answer("Ошибка создания счета!", show_alert=True)
                    return
                inv = res["result"]
    except Exception as e:
        logging.error(f"CryptoBot error: {e}")
        await callback.answer("Ошибка связи с CryptoBot!", show_alert=True)
        return

    invoice_id = inv["invoice_id"]
    pay_url = inv["bot_invoice_url"]

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 Перейти к оплате", url=pay_url, style="success")],
        [InlineKeyboardButton(text="🔄 Проверить оплату", callback_data=f"check_crypto_{invoice_id}_{username}", style="primary")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="show_store", style="danger")]
    ])
    
    await callback.message.edit_text(
        f"{E_MONEY} <b>Счет на покупку @{username}</b>\n\n"
        f"К оплате: <b>{usd_price}$</b>\n"
        f"После оплаты нажмите кнопку «Проверить оплату».", 
        reply_markup=kb, parse_mode="HTML"
    )
    await callback.answer()

@router.callback_query(F.data.startswith("check_crypto_"))
async def check_crypto(callback: CallbackQuery):
    _, _, invoice_id, username = callback.data.split("_")
    
    url = f"https://pay.crypt.bot/api/getInvoices?invoice_ids={invoice_id}"
    headers = {"Crypto-Pay-API-Token": CRYPTO_BOT_TOKEN}

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as resp:
                res = await resp.json()
                if res.get("ok") and res.get("result", {}).get("items"):
                    item = res["result"]["items"][0]
                    if item.get("status") == "paid":
                        conn = sqlite3.connect(DB_FILE)
                        cursor = conn.cursor()
                        cursor.execute("SELECT status FROM usernames WHERE username = ?", (username,))
                        row = cursor.fetchone()
                        conn.close()
                        
                        if row and row[0] == 'RESERVED':
                            price_usd = float(item.get("amount", 0))
                            process_purchase(callback.from_user.id, callback.from_user.first_name, callback.from_user.username, username, f"{price_usd}$", "CryptoBot")
                            await callback.answer("Оплата подтверждена!", show_alert=True)
                            return
                        else:
                            await callback.answer("Этот ник уже продан!", show_alert=True)
                            return
    except Exception as e:
        logging.error(f"Error checking invoice: {e}")

    await callback.answer("⏳ Оплата еще не поступила. Завершите перевод.", show_alert=True)

def process_purchase(user_id, first_name, username, bought_username, amount, method):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("UPDATE usernames SET status = 'SOLD' WHERE username = ?", (bought_username,))
    cursor.execute("INSERT INTO orders (user_id, username, price) VALUES (?, ?, ?)", (user_id, bought_username, amount if isinstance(amount, str) else int(amount)))
    conn.commit()
    conn.close()

    admin_text = (
        f"{E_MONEY} <b>НОВАЯ ПОКУПКА!</b>\n\n"
        f"{E_USER} Покупатель: {first_name} (@{username})\n"
        f"🆔 ID: <code>{user_id}</code>\n"
        f"🔗 Ник: <code>@{bought_username}</code>\n"
        f"💵 Сумма: {amount} ({method})\n\n"
        f"<i>Свяжитесь с покупателем, чтобы передать ник.</i>"
    )
    asyncio.create_task(bot.send_message(ADMIN_ID, admin_text, parse_mode="HTML"))

# ==============================================================================
# 👑 АДМИН-ПАНЕЛЬ
# ==============================================================================
@router.callback_query(F.data == "admin_panel")
async def admin_panel(callback: CallbackQuery):
    if not is_admin(callback.from_user.id): return
    await callback.answer()
    
    global PARSING_ACTIVE
    
    kb = []
    if PARSING_ACTIVE:
        kb.append([InlineKeyboardButton(text="🛑 Остановить парсинг", callback_data="admin_stop_parse", style="danger")])
    else:
        kb.append([InlineKeyboardButton(text="🔄 Запустить парсер", callback_data="admin_parse", style="primary")])
        
    kb.append([InlineKeyboardButton(text="📦 Свободные (не выставлены)", callback_data="admin_free_list", style="success")])
    kb.append([InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main", style="danger")])
    
    await callback.message.edit_text(f"{E_CROWN} <b>Админ-панель</b>\n\nУправляйте парсером и витриной:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="HTML")

@router.callback_query(F.data == "admin_parse")
async def admin_parse(callback: CallbackQuery):
    if not is_admin(callback.from_user.id): return
    await callback.answer("Парсер запущен в фоне!")
    asyncio.create_task(parse_usernames_task(callback.message))
    await admin_panel(callback)

@router.callback_query(F.data == "admin_stop_parse")
async def admin_stop_parse(callback: CallbackQuery):
    global PARSING_ACTIVE
    if not is_admin(callback.from_user.id): return
    PARSING_ACTIVE = False
    await callback.answer("Команда на остановку отправлена!", show_alert=True)
    await admin_panel(callback)

@router.callback_query(F.data == "admin_free_list")
async def admin_free_list(callback: CallbackQuery):
    if not is_admin(callback.from_user.id): return
    await callback.answer()
    
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT username FROM usernames WHERE status = 'FREE' LIMIT 20")
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        await callback.message.edit_text("📦 Нет свободных ников в базе. Запустите парсер.", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data="admin_panel", style="danger")]]), parse_mode="HTML")
        return

    text = "📦 <b>Свободные ники в базе (нажмите, чтобы выставить):</b>\n\n"
    kb = []
    for row in rows:
        uname = row[0]
        kb.append([InlineKeyboardButton(text=f"@{uname}", callback_data=f"reserve_{uname}", style="primary")])
    
    kb.append([InlineKeyboardButton(text="🔙 Назад", callback_data="admin_panel", style="danger")])
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="HTML")

@router.callback_query(F.data.startswith("reserve_"))
async def reserve_username(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id): return
    uname = callback.data.replace("reserve_", "")
    
    await state.set_state(AdminState.waiting_for_price)
    await state.update_data(reserve_uname=uname)
    
    await callback.message.edit_text(
        f"💰 <b>Установка цены для @{uname}</b>\n\n"
        f"Введите цену в Звездах (только число):",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="admin_panel", style="danger")]]),
        parse_mode="HTML"
    )
    await callback.answer()

@router.message(AdminState.waiting_for_price)
async def process_price(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id): return
    if not message.text.isdigit():
        await message.answer(f"{E_CROSS} Введите только число!", parse_mode="HTML")
        return
        
    price = int(message.text)
    data = await state.get_data()
    uname = data.get("reserve_uname")
    await state.clear()

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("UPDATE usernames SET status = 'RESERVED', price = ? WHERE username = ?", (price, uname))
    conn.commit()
    conn.close()

    await message.answer(
        f"{E_CHECK} Ник <code>@{uname}</code> выставлен на витрину за <b>{price} ⭐️</b>!\n\n"
        f"<i>Не забудьте зарегистрировать его на свой аккаунт!</i>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="👑 В админку", callback_data="admin_panel", style="primary")]]),
        parse_mode="HTML"
    )

# ==============================================================================
# 🚀 ЗАПУСК
# ==============================================================================
async def main():
    init_db()
    dp.include_router(router)
    await bot.delete_webhook(drop_pending_updates=True)
    print("🚀 Бот-магазин юзернеймов запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
