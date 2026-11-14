import asyncio
import logging
import secrets
from aiogram import Bot, Dispatcher, F
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton,
    LabeledPrice, PreCheckoutQuery
)
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from app.config import settings
from app import db
from app.ai import answer
from app.i18n import tr

logging.basicConfig(level=logging.INFO)
dp = Dispatcher()

def menu(lang: str):
    labels = [
        (tr(lang, "chat"), "chat"),
        (tr(lang, "plans"), "plans"),
        (tr(lang, "memory"), "memory"),
        (tr(lang, "language"), "language"),
        (tr(lang, "help"), "help"),
    ]
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=labels[0][0], callback_data="chat"),
         InlineKeyboardButton(text=labels[1][0], callback_data="plans")],
        [InlineKeyboardButton(text=labels[2][0], callback_data="memory"),
         InlineKeyboardButton(text=labels[3][0], callback_data="language")],
        [InlineKeyboardButton(text=labels[4][0], callback_data="help")],
    ])

def language_menu():
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="فارسی", callback_data="lang:fa"),
        InlineKeyboardButton(text="English", callback_data="lang:en")
    ]])

def back_menu(lang: str):
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=tr(lang, "back"), callback_data="home")
    ]])

async def lang_of(user_id: int):
    return await db.get_language(user_id)

@dp.message(CommandStart())
async def start(message: Message):
    await db.ensure_user(message.from_user.id, message.from_user.username)
    lang = await lang_of(message.from_user.id)
    await message.answer(tr(lang, "welcome"), reply_markup=menu(lang))

@dp.message(Command("myid"))
async def my_id_cmd(message: Message):
    lang = await lang_of(message.from_user.id)
    label = "شناسه عددی شما" if lang == "fa" else "Your numeric user ID"
    await message.answer(f"{label}: <code>{message.from_user.id}</code>")

@dp.message(Command("help"))
async def help_cmd(message: Message):
    lang = await lang_of(message.from_user.id)
    await message.answer(tr(lang, "help_text"), reply_markup=back_menu(lang))

@dp.message(Command("language"))
async def language_cmd(message: Message):
    lang = await lang_of(message.from_user.id)
    await message.answer(tr(lang, "choose_lang"), reply_markup=language_menu())

@dp.message(Command("reset"))
async def reset_cmd(message: Message):
    await db.clear_history(message.from_user.id)
    lang = await lang_of(message.from_user.id)
    await message.answer(tr(lang, "memory_cleared"), reply_markup=menu(lang))

@dp.message(Command("plans"))
async def plans_cmd(message: Message):
    lang = await lang_of(message.from_user.id)
    await show_plans(message, lang)

async def show_plans(message: Message, lang: str):
    if not settings.enable_stars:
        await message.answer(tr(lang, "payment_disabled"))
        return
    text = tr(lang, "plans_text", price=settings.pro_price_stars)
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=("خرید اشتراک" if lang == "fa" else "Buy Pro"), callback_data="buy:pro")
    ], [InlineKeyboardButton(text=tr(lang, "back"), callback_data="home")]])
    await message.answer(text, reply_markup=keyboard)

@dp.callback_query(F.data == "home")
async def home_cb(query: CallbackQuery):
    lang = await lang_of(query.from_user.id)
    await query.message.edit_text(tr(lang, "welcome"), reply_markup=menu(lang))
    await query.answer()

@dp.callback_query(F.data == "chat")
async def chat_cb(query: CallbackQuery):
    lang = await lang_of(query.from_user.id)
    prompt = "حالا پیام خود را ارسال کنید." if lang == "fa" else "Send your message now."
    await query.message.answer(prompt)
    await query.answer()

@dp.callback_query(F.data == "plans")
async def plans_cb(query: CallbackQuery):
    lang = await lang_of(query.from_user.id)
    await show_plans(query.message, lang)
    await query.answer()

@dp.callback_query(F.data == "language")
async def language_cb(query: CallbackQuery):
    lang = await lang_of(query.from_user.id)
    await query.message.answer(tr(lang, "choose_lang"), reply_markup=language_menu())
    await query.answer()

@dp.callback_query(F.data.startswith("lang:"))
async def set_lang_cb(query: CallbackQuery):
    lang = query.data.split(":", 1)[1]
    await db.set_language(query.from_user.id, lang)
    await query.message.answer(tr(lang, "lang_saved"), reply_markup=menu(lang))
    await query.answer()

@dp.callback_query(F.data == "memory")
async def memory_cb(query: CallbackQuery):
    lang = await lang_of(query.from_user.id)
    text = ("حافظه گفتگو برای پاسخ‌های مرتبط استفاده می‌شود. برای پاک‌کردن آن دستور /reset را بفرستید."
            if lang == "fa" else "Chat history is used for context. Send /reset to clear it.")
    await query.message.answer(text, reply_markup=back_menu(lang))
    await query.answer()

@dp.callback_query(F.data == "help")
async def help_cb(query: CallbackQuery):
    lang = await lang_of(query.from_user.id)
    await query.message.answer(tr(lang, "help_text"), reply_markup=back_menu(lang))
    await query.answer()

@dp.callback_query(F.data == "buy:pro")
async def buy_pro(query: CallbackQuery, bot: Bot):
    lang = await lang_of(query.from_user.id)
    if not settings.enable_stars:
        await query.answer(tr(lang, "payment_disabled"), show_alert=True)
        return
    payload = f"pro:{query.from_user.id}:{secrets.token_urlsafe(8)}"
    try:
        await bot.send_invoice(
            chat_id=query.from_user.id,
            title="VibeChat Pro",
            description=f"VibeChat Pro for {settings.pro_duration_days} days",
            payload=payload,
            provider_token="",
            currency="XTR",
            prices=[LabeledPrice(label="VibeChat Pro", amount=settings.pro_price_stars)],
        )
        await query.answer()
    except Exception:
        logging.exception("Invoice creation failed")
        await query.answer(tr(lang, "invoice_error"), show_alert=True)

@dp.pre_checkout_query()
async def pre_checkout(query: PreCheckoutQuery):
    try:
        parts = query.invoice_payload.split(":")
        valid = len(parts) == 3 and parts[0] == "pro" and int(parts[1]) == query.from_user.id
        valid = valid and query.currency == "XTR" and query.total_amount == settings.pro_price_stars
    except Exception:
        valid = False
    await query.answer(ok=valid, error_message=None if valid else "Invalid or expired order.")

@dp.message(F.successful_payment)
async def successful_payment(message: Message):
    payment = message.successful_payment
    payload = payment.invoice_payload
    try:
        parts = payload.split(":")
        valid = len(parts) == 3 and parts[0] == "pro" and int(parts[1]) == message.from_user.id
        valid = valid and payment.currency == "XTR" and payment.total_amount == settings.pro_price_stars
        if not valid:
            logging.error("Payment payload validation failed for user %s", message.from_user.id)
            return
        charge_id = payment.telegram_payment_charge_id
        if await db.payment_exists(charge_id):
            return
        await db.record_payment(charge_id, message.from_user.id, payload, payment.total_amount, payment.currency)
        await db.activate_pro(message.from_user.id, charge_id, settings.pro_duration_days)
        lang = await lang_of(message.from_user.id)
        await message.answer(tr(lang, "payment_ok"), reply_markup=menu(lang))
    except Exception:
        logging.exception("Could not process successful payment")

@dp.message(Command("paysupport"))
async def paysupport(message: Message):
    lang = await lang_of(message.from_user.id)
    await message.answer(tr(lang, "payment_support"))
    if settings.owner_id:
        await message.bot.send_message(settings.owner_id,
            f"Payment support request from user {message.from_user.id}: {message.text or '/paysupport'}")

@dp.message(Command("stats"))
async def stats_cmd(message: Message):
    if not settings.owner_id or message.from_user.id != settings.owner_id:
        lang = await lang_of(message.from_user.id)
        await message.answer(tr(lang, "admin_only"))
        return
    users, subs = await db.stats()
    await message.answer(f"Registered users: {users}\nActive subscriptions: {subs}")

@dp.message(F.text & ~F.text.startswith("/"))
async def chat_message(message: Message):
    await db.ensure_user(message.from_user.id, message.from_user.username)
    lang = await lang_of(message.from_user.id)
    pro = await db.is_pro(message.from_user.id)
    if not pro and not await db.consume_free_quota(message.from_user.id):
        await message.answer(tr(lang, "free_limit"), reply_markup=menu(lang))
        return
    history = await db.get_history(message.from_user.id)
    history.append({"role": "user", "content": message.text[:12000]})
    try:
        response = await answer(history)
        await db.add_exchange(message.from_user.id, message.text[:12000], response[:12000])
        # Telegram message length limit: split conservatively.
        for i in range(0, len(response), 3900):
            await message.answer(response[i:i+3900])
    except RuntimeError as exc:
        logging.warning("AI unavailable: %s", exc)
        await message.answer(tr(lang, "no_ai"))
    except Exception:
        logging.exception("AI request failed")
        await message.answer(tr(lang, "ai_error"))

async def main():
    if not settings.bot_token:
        raise RuntimeError("VIBE_BOT_TOKEN is required")
    await db.init_db()
    session = AiohttpSession(api=TelegramAPIServer.from_base(settings.api_base))
    bot = Bot(token=settings.bot_token, session=session,
              default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    me = await bot.get_me()
    logging.info("VibeChat started as @%s", me.username)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
