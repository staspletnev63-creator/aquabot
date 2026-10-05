import asyncio
import re
import html
import sqlite3
import os
from aiohttp import web
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import CommandStart
from aiogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton, 
    ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove,
    WebAppInfo
)
from aiogram.enums import ParseMode
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

BOT_TOKEN = "8679249764:AAHW_JtlsSi372LD2GltGfe41cuImhgnZqE"
MANAGER_CHAT_ID = 8046596311  
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

def init_db():
    conn = sqlite3.connect("bot_shop.db")
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS clients (
            user_id INTEGER PRIMARY KEY,
            full_name TEXT,
            phone TEXT,
            username TEXT,
            order_date TEXT
        )
    ''')
    conn.commit()
    conn.close()

init_db()

def save_client_to_db(user_id, full_name, phone, username):
    conn = sqlite3.connect("bot_shop.db")
    cursor = conn.cursor()
    cursor.execute('''
        INSERT OR REPLACE INTO clients (user_id, full_name, phone, username, order_date)
        VALUES (?, ?, ?, ?, datetime('now'))
    ''', (user_id, full_name, phone, username))
    conn.commit()
    conn.close()

class ClientStates(StatesGroup):
    waiting_for_call = State()
    waiting_for_order = State()

main_menu_kb = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="🛒 Каталог товарів (Web App)", web_app=WebAppInfo(url="https://aquafilters.com.ua/"))],
    [InlineKeyboardButton(text="🤖 Підібрати фільтр (Квіз з фото)", callback_data="quiz_start")],
    [InlineKeyboardButton(text="💬 Хочу отримати консультацію", callback_data="btn_consult")],
    [InlineKeyboardButton(text="🔍 Не можу знайти товар", callback_data="req_not_found")],
    [InlineKeyboardButton(text="📞 Зателефонуйте мені", callback_data="btn_call_me")],
    [InlineKeyboardButton(text="📦 Коли відправлять моє замовлення", callback_data="btn_shipping")],
    [InlineKeyboardButton(text="👨‍💻 Підключити менеджера", callback_data="req_manager")]
])

contact_kb = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="📱 Поділитися номером телефону", request_contact=True)]],
    resize_keyboard=True,
    one_time_keyboard=True
)

consult_kb = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="✅ Я вже створив замовлення", callback_data="req_consult_ordered")],
    [InlineKeyboardButton(text="❓ Цікавить консультація перед покупкою", callback_data="req_consult_before")],
    [InlineKeyboardButton(text="👨‍💻 Підключити оператора", callback_data="req_consult_operator")],
    [InlineKeyboardButton(text="🔙 Повернутися в меню", callback_data="btn_back_main")]
])

back_to_menu_kb = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="🔙 Повернутися в меню", callback_data="btn_back_main")]
])

quiz_q1_kb = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="🏢 Для квартири", callback_data="quiz_apt")],
    [InlineKeyboardButton(text="🏡 Для приватного будинку", callback_data="quiz_house")],
    [InlineKeyboardButton(text="🔙 Повернутися в меню", callback_data="btn_back_main")]
])

quiz_apt_kb = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="🚰 Питна вода (під мийку)", callback_data="quiz_res_osmos")],
    [InlineKeyboardButton(text="🚿 Очищення всієї води (магістральні)", callback_data="quiz_res_bb20")],
    [InlineKeyboardButton(text="🔙 Повернутися в меню", callback_data="quiz_start")]
])

quiz_house_kb = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="🟤 Очищення від заліза та запаху", callback_data="quiz_res_iron")],
    [InlineKeyboardButton(text="⚪ Пом'якшення води (від накипу)", callback_data="quiz_res_soft")],
    [InlineKeyboardButton(text="🔙 Повернутися в меню", callback_data="quiz_start")]
])

req_translations = {
    "req_not_found": "Не можу знайти товар",
    "req_manager": "Підключити менеджера",
    "req_consult_ordered": "Консультація: Я вже створив замовлення",
    "req_consult_before": "Консультація: Цікавить перед покупкою",
    "req_consult_operator": "Консультація: Підключити оператора"
}

ai_knowledge = {
    r"(картридж|змінн|замін)": "🤖 <b>Авто-помічник:</b> Зазвичай нижні картриджі потрібно міняти раз на 3-6 місяців, а мембрану — раз на 1.5-2 роки. Менеджер вже підключається!",
    r"(мембран)": "🤖 <b>Авто-помічник:</b> Мембрана зворотного осмосу служить 1.5–3 роки. Оператор допоможе підібрати заміну!",
    r"(накип|жорстк|білий наліт)": "🤖 <b>Авто-помічник:</b> Від накипу ідеально рятує зворотний осмос або система пом'якшення води.",
    r"(тиск|напір|помп|насос)": "🤖 <b>Авто-помічник:</b> Для осмосу бажано від 2.8 атмосфер тиску. Якщо менше — потрібна помпа."
}

@dp.message(CommandStart())
async def start_command(message: types.Message, state: FSMContext):
    await state.clear()
    welcome_text = (
        "✨ <b>Вітаємо у фірмовому магазині aquafilters.com.ua!</b> 💧\n\n"
        "Оберіть потрібний розділ нижче або <b>залиште номер телефону</b> для персональних знижок та консультацій 👇"
    )
    await message.answer(welcome_text, reply_markup=contact_kb)

@dp.message(F.contact)
async def handle_contact(message: types.Message):
    phone = message.contact.phone_number
    user = message.from_user
    client_link = f"@{user.username}" if user.username else f"<a href='tg://user?id={user.id}'>профіль</a>"
    
    save_client_to_db(user.id, user.full_name, phone, user.username)
    
    msg_text = (
        "🆕 <b>Новий клієнт (збережено в базу)!</b>\n"
        f"👤 {user.full_name} ({client_link})\n"
        f"📱 <b>Телефон:</b> {phone}\n"
        f"<tg-spoiler>#id{user.id}</tg-spoiler>"
    )
    await bot.send_message(MANAGER_CHAT_ID, msg_text)
    
    del_msg = await message.answer("🔄 Завантаження каталогу...", reply_markup=ReplyKeyboardRemove())
    await del_msg.delete()
    
    await message.answer(
        "✅ <b>Номер успішно збережено!</b>\n\nТепер вам доступний весь функціонал магазину:",
        reply_markup=main_menu_kb
    )

@dp.callback_query(F.data == "quiz_start")
async def quiz_step_1(callback: types.CallbackQuery):
    await callback.message.edit_text("🎯 <b>Крок 1/2:</b> Куди ви підбираєте фільтр?", reply_markup=quiz_q1_kb)

@dp.callback_query(F.data == "quiz_apt")
async def quiz_step_2_apt(callback: types.CallbackQuery):
    await callback.message.edit_text("🎯 <b>Крок 2/2:</b> Яке ваше головне завдання?", reply_markup=quiz_apt_kb)

@dp.callback_query(F.data == "quiz_house")
async def quiz_step_2_house(callback: types.CallbackQuery):
    await callback.message.edit_text("🎯 <b>Крок 2/2:</b> Яка головна проблема з водою?", reply_markup=quiz_house_kb)

@dp.callback_query(F.data.startswith("quiz_res_"))
async def quiz_results(callback: types.CallbackQuery):
    res_type = callback.data
    await callback.message.delete()
    
    photo_url = "https://aquafilters.com.ua/image/catalog/logo.png"
    text = ""
    
    if res_type == "quiz_res_osmos":
        text = (
            "💧 <b>Система зворотного осмосу</b>\n\n"
            "• Очищення 99.8% (бактерії, віруси, накип)\n"
            "• Мінералізація води\n"
            "• Пийте прямо з крана без кип'ятіння!\n\n"
            "👉 <a href='https://aquafilters.com.ua/index.php?route=product/category&path=106_109'>Переглянути моделі на сайті</a>"
        )
    elif res_type == "quiz_res_bb20":
        text = (
            "🚿 <b>Магістральний фільтр Big Blue 20</b>\n\n"
            "• Захист техніки, пралок та бойлерів від іржі\n"
            "• Висока пропускна здатність\n\n"
            "👉 <a href='https://aquafilters.com.ua/'>Переглянути магістральні фільтри</a>"
        )
    elif res_type == "quiz_res_iron":
        text = (
            "🟤 <b>Система комплексного очищення від заліза</b>\n\n"
            "• Видалення металевого присмаку та рудих плям\n"
            "• Автоматичний керуючий клапан\n\n"
            "👉 <a href='https://aquafilters.com.ua/'>Переглянути системи</a>"
        )
    elif res_type == "quiz_res_soft":
        text = (
            "⚪ <b>Пом'якшувач води кабінетного типу</b>\n\n"
            "• Повне позбавлення від жорсткості та нальоту\n"
            "• М'яка шкіра та захист сантехніки\n\n"
            "👉 <a href='https://aquafilters.com.ua/'>Переглянути пом'якшувачі</a>"
        )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🛒 Купити в 1 клік (покликати менеджера)", callback_data="req_manager")],
        [InlineKeyboardButton(text="🔙 Повернутися в меню", callback_data="btn_back_main")]
    ])
    
    await bot.send_photo(chat_id=callback.message.chat.id, photo=photo_url, caption=text, reply_markup=kb)

@dp.callback_query(F.data == "btn_consult")
async def nav_consult(callback: types.CallbackQuery):
    await callback.message.edit_text("💬 <b>Оберіть тему консультації:</b>", reply_markup=consult_kb)

@dp.callback_query(F.data == "btn_back_main")
async def nav_back(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    try:
        await callback.message.edit_text("Головне меню магазину:", reply_markup=main_menu_kb)
    except:
        await callback.message.answer("Головне меню магазину:", reply_markup=main_menu_kb)

@dp.callback_query(F.data == "btn_call_me")
async def ask_call_details(callback: types.CallbackQuery, state: FSMContext):
    text = (
        "📞 <b>Залиште ваше імʼя і номер телефону</b>\n"
        "<i>(наприклад: Станіслав, 099 123 45 67)</i>:"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Повернутися в меню", callback_data="btn_back_main")]
    ])
    await callback.message.edit_text(text, reply_markup=kb)
    await state.set_state(ClientStates.waiting_for_call)

@dp.message(ClientStates.waiting_for_call)
async def process_call_details(message: types.Message, state: FSMContext):
    user = message.from_user
    client_link = f"@{user.username}" if user.username else f"<a href='tg://user?id={user.id}'>профіль</a>"
    msg_text = (
        "🚨 <b>Передзвонити!</b>\n"
        f"👤 {user.full_name} ({client_link})\n"
        f"📝 {html.escape(message.text)}\n"
        f"<tg-spoiler>#id{user.id}</tg-spoiler>"
    )
    await bot.send_message(MANAGER_CHAT_ID, msg_text)
    await message.answer("✅ <b>Дякуємо!</b> Менеджер зв'яжеться з вами найближчим часом.", reply_markup=main_menu_kb)
    await state.clear()

@dp.callback_query(F.data == "btn_shipping")
async def ask_order_number(callback: types.CallbackQuery, state: FSMContext):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Повернутися в меню", callback_data="btn_back_main")]
    ])
    await callback.message.edit_text("📦 <b>Напишіть номер вашого замовлення:</b>", reply_markup=kb)
    await state.set_state(ClientStates.waiting_for_order)

@dp.message(ClientStates.waiting_for_order)
async def process_order_details(message: types.Message, state: FSMContext):
    user = message.from_user
    client_link = f"@{user.username}" if user.username else f"<a href='tg://user?id={user.id}'>профіль</a>"
    msg_text = (
        "🚨 <b>Статус замовлення!</b>\n"
        f"👤 {user.full_name} ({client_link})\n"
        f"📦 №: {html.escape(message.text)}\n"
        f"<tg-spoiler>#id{user.id}</tg-spoiler>"
    )
    await bot.send_message(MANAGER_CHAT_ID, msg_text)
    await message.answer("✅ <b>Прийнято!</b> Оператор перевіряє посилку та відповість тут.", reply_markup=main_menu_kb)
    await state.clear()

@dp.callback_query(F.data.startswith("req_"))
async def handle_instant_requests(callback: types.CallbackQuery):
    await callback.answer()
    choice = req_translations.get(callback.data, "Запит")
    user = callback.from_user
    client_link = f"@{user.username}" if user.username else f"<a href='tg://user?id={user.id}'>профіль</a>"
    msg_text = (
        f"🚨 <b>Запит:</b> {choice}\n"
        f"👤 {user.full_name} ({client_link})\n"
        f"<tg-spoiler>#id{user.id}</tg-spoiler>"
    )
    await bot.send_message(MANAGER_CHAT_ID, msg_text)
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Повернутися в меню", callback_data="btn_back_main")]
    ])
    await callback.message.edit_text(f"✅ Запит надіслано! Оператор уже підключається.", reply_markup=kb)

@dp.message(F.chat.id != MANAGER_CHAT_ID)
async def handle_client_message(message: types.Message):
    user = message.from_user
    client_link = f"@{user.username}" if user.username else f"<a href='tg://user?id={user.id}'>профіль</a>"
    escaped_text = html.escape(message.text) if message.text else "<Медіафайл>"
    
    msg_text = (
        "💬 <b>Повідомлення:</b>\n"
        f"👤 {user.full_name} ({client_link})\n"
        "---\n"
        f"{escaped_text}\n"
        "---\n"
        "<i>Reply для відповіді.</i>\n"
        f"<tg-spoiler>#id{user.id}</tg-spoiler>"
    )
    info_msg = await bot.send_message(MANAGER_CHAT_ID, msg_text)
    if not message.text:
        await bot.copy_message(MANAGER_CHAT_ID, message.chat.id, message.message_id, reply_to_message_id=info_msg.message_id)

    if message.text:
        lower_text = message.text.lower()
        for pattern, answer in ai_knowledge.items():
            if re.search(pattern, lower_text):
                await message.answer(answer, reply_markup=back_to_menu_kb)
                break

@dp.message(F.chat.id == MANAGER_CHAT_ID, F.reply_to_message)
async def manager_reply(message: types.Message):
    reply_msg = message.reply_to_message
    original_text = reply_msg.text or reply_msg.caption or ""
    if reply_msg.quote and reply_msg.quote.text:
        original_text += "\n" + reply_msg.quote.text
        
    match = re.search(r'#id(\d+)', original_text)
    if match:
        client_id = int(match.group(1))
        try:
            if message.text:
                await bot.send_message(
                    client_id, 
                    f"💬 <b>Відповідь менеджера:</b>\n\n{html.escape(message.text)}", 
                    reply_markup=back_to_menu_kb
                )
            else:
                await bot.copy_message(client_id, message.chat.id, message.message_id)
                await bot.send_message(
                    client_id, 
                    "Оберіть дію:", 
                    reply_markup=back_to_menu_kb
                )
            
            await message.reply("✅ <i>Надіслано клієнту разом із кнопкою меню!</i>")
        except Exception as e:
            await message.reply(f"❌ <b>Помилка:</b> {e}")
    else:
        await message.reply("❌ <b>Помилка:</b> Не вдалося знайти ID кліента. Зробіть Reply на повідомлення сповіщення про клієнта.")

async def handle_ping(request):
    return web.Response(text="Bot is running!")

async def web_server():
    app = web.Application()
    app.router.add_get('/', handle_ping)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 10000))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()

async def main():
    print("Бот shop_render запущен на Render...")
    asyncio.create_task(web_server())
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
