import asyncio
import html
import logging
import secrets

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer
from aiogram.enums import ChatType
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    CallbackQuery, ChatMemberUpdated, InlineKeyboardButton, InlineKeyboardMarkup,
    LabeledPrice, Message, PreCheckoutQuery, ReactionTypeEmoji,
)

from app import db
from app.ai import answer, summarize_history
from app.config import settings
from app.i18n import tr
from app.utils import insult_hit, pick_reaction, split_chunks, strip_html, to_small_caps

logging.basicConfig(level=logging.INFO)
dp = Dispatcher(storage=MemoryStorage())

BOT_USERNAME = ""


def esc(value) -> str:
    """Escape user-provided text before embedding it into HTML messages."""
    return html.escape(str(value or ""), quote=False)


def btn(lang: str, key: str, callback: str) -> InlineKeyboardButton:
    text = tr(lang, key)
    if lang == "en":
        text = to_small_caps(text)
    return InlineKeyboardButton(text=text, callback_data=callback)


def menu(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [btn(lang, "language", "language"), btn(lang, "model", "model")],
        [btn(lang, "help", "help"), btn(lang, "support", "support")],
        [btn(lang, "plans", "plans")],
    ])


def language_menu(lang: str) -> InlineKeyboardMarkup:
    en_label = to_small_caps("English") if lang == "en" else "English"
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="فارسی", callback_data="lang:fa"),
        InlineKeyboardButton(text=en_label, callback_data="lang:en"),
    ]])


def model_menu(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [btn(lang, "model_name", "model:vibel-1.0")],
        [btn(lang, "back", "home")],
    ])


def back_menu(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[btn(lang, "back", "home")]])


async def lang_of(user_id: int) -> str:
    return await db.get_language(user_id)


class Typing:
    """Keeps the "typing..." indicator alive while the AI is generating."""

    def __init__(self, bot: Bot, chat_id: int):
        self._bot = bot
        self._chat_id = chat_id
        self._task = None

    async def __aenter__(self):
        # Send one indicator immediately, then keep it alive while generating.
        try:
            await self._bot.send_chat_action(chat_id=self._chat_id, action="typing")
        except Exception:
            return
        self._task = asyncio.create_task(self._loop())

    async def __aexit__(self, *exc_info):
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._task = None

    async def _loop(self):
        while True:
            try:
                await self._bot.send_chat_action(chat_id=self._chat_id, action="typing")
            except Exception:
                return  # Indicator is optional on the gateway; stop silently.
            await asyncio.sleep(4)


async def react(message: Message):
    """React to the user's message based on a quick sentiment analysis."""
    try:
        await message.bot.set_message_reaction(
            chat_id=message.chat.id,
            message_id=message.message_id,
            reaction=[ReactionTypeEmoji(emoji=pick_reaction(message.text or ""))],
            is_big=False,
        )
    except Exception:
        pass  # Reactions may be unsupported on the gateway; ignore silently.


async def send_chunked(message: Message, text: str):
    """Send AI output as HTML with a safe plain-text fallback per chunk."""
    is_private = message.chat.type == ChatType.PRIVATE
    for chunk in split_chunks(text):
        sender = message.answer if is_private else message.reply
        try:
            await sender(chunk)
        except Exception:
            try:
                await message.answer(html.escape(strip_html(chunk)))
            except Exception:
                logging.exception("Failed to deliver a message chunk")


def admin_kb(stars: bool, limit: int) -> InlineKeyboardMarkup:
    limit_label = "نامحدود" if limit == 0 else str(limit)
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="آمار کامل", callback_data="adm:stats"),
         InlineKeyboardButton(text="پخش پیام", callback_data="adm:bcast")],
        [InlineKeyboardButton(text=f"محدودیت روزانه: {limit_label}", callback_data="adm:limit")],
        [InlineKeyboardButton(text=f"خرید پرمیوم: {'روشن' if stars else 'خاموش'}", callback_data="adm:stars")],
        [InlineKeyboardButton(text="اعطای اشتراک", callback_data="adm:grant"),
         InlineKeyboardButton(text="لغو اشتراک", callback_data="adm:revoke")],
        [InlineKeyboardButton(text="اخطارها", callback_data="adm:warnings"),
         InlineKeyboardButton(text="پاک‌کردن اخطار", callback_data="adm:clearwarn")],
        [InlineKeyboardButton(text="بن کاربر", callback_data="adm:ban"),
         InlineKeyboardButton(text="رفع بن", callback_data="adm:unban")],
        [InlineKeyboardButton(text="بستن پنل", callback_data="adm:close")],
    ])


def limit_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="نامحدود", callback_data="adm:limit:0"),
         InlineKeyboardButton(text="۲۰", callback_data="adm:limit:20")],
        [InlineKeyboardButton(text="۵۰", callback_data="adm:limit:50"),
         InlineKeyboardButton(text="۱۰۰", callback_data="adm:limit:100")],
        [InlineKeyboardButton(text="بازگشت", callback_data="adm:panel")],
    ])


async def panel_text() -> str:
    users, subs = await db.stats()
    total, today = await db.message_stats()
    warnings = await db.warning_total()
    banned = await db.banned_total()
    limit = await db.get_daily_limit()
    stars = await db.stars_enabled()
    return (
        "پنل مدیریت وایب‌چت\n\n"
        f"کاربران: {users}\n"
        f"اشتراک فعال: {subs}\n"
        f"کل پیام‌ها: {total} (امروز: {today})\n"
        f"اخطارها: {warnings} | بن‌شده‌ها: {banned}\n"
        f"محدودیت روزانه: {'نامحدود' if limit == 0 else limit}\n"
        f"خرید پرمیوم: {'روشن' if stars else 'خاموش'}"
    )


async def is_owner(user_id: int) -> bool:
    return bool(settings.owner_id) and user_id == settings.owner_id


class AdminStates(StatesGroup):
    broadcast = State()
    grant = State()
    revoke = State()
    ban = State()
    unban = State()
    clearwarn = State()


@dp.my_chat_member()
async def on_my_chat_member(cm: ChatMemberUpdated, bot: Bot):
    """Greet when the bot is added to a group."""
    if cm.chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
        return
    old_status = cm.old_chat_member.status if cm.old_chat_member else "left"
    new_status = cm.new_chat_member.status if cm.new_chat_member else "left"
    if new_status in {"member", "administrator"} and old_status in {"left", "kicked"}:
        try:
            await bot.send_message(cm.chat.id, tr("fa", "group_greet"))
        except Exception:
            logging.exception("Could not greet the group")


@dp.message(CommandStart())
async def start(message: Message):
    await db.ensure_user(message.from_user.id, message.from_user.username)
    lang = await lang_of(message.from_user.id)
    name = message.from_user.first_name or "دوست من"
    await message.answer(tr(lang, "welcome", name=esc(name)), reply_markup=menu(lang))


@dp.message(Command("myid"))
async def my_id_cmd(message: Message):
    lang = await lang_of(message.from_user.id)
    label = "شناسه عددی شما" if lang == "fa" else "Your numeric user ID"
    username = f"@{message.from_user.username}" if message.from_user.username else "—"
    await message.answer(f"{label}: <code>{message.from_user.id}</code>\nusername: {esc(username)}")


@dp.message(Command("help"))
async def help_cmd(message: Message):
    lang = await lang_of(message.from_user.id)
    await message.answer(tr(lang, "help_text"), reply_markup=back_menu(lang))


@dp.message(Command("language"))
async def language_cmd(message: Message):
    lang = await lang_of(message.from_user.id)
    await message.answer(tr(lang, "choose_lang"), reply_markup=language_menu(lang))


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
    if not await db.stars_enabled():
        await message.answer(tr(lang, "payment_disabled"))
        return
    text = tr(lang, "plans_text", price=settings.pro_price_stars, days=settings.pro_duration_days)
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [btn(lang, "buy_now", "buy:pro")],
        [btn(lang, "back", "home")],
    ])
    await message.answer(text, reply_markup=keyboard)


@dp.message(Command("paysupport"))
async def paysupport(message: Message):
    lang = await lang_of(message.from_user.id)
    await message.answer(tr(lang, "payment_support"))
    if settings.owner_id:
        await message.bot.send_message(settings.owner_id,
            f"Payment support request from user {message.from_user.id}: {message.text or '/paysupport'}")


@dp.message(Command("admin"))
async def admin_cmd(message: Message):
    if not await is_owner(message.from_user.id):
        return
    await message.answer(await panel_text(), reply_markup=admin_kb(await db.stars_enabled(),
                                                                      await db.get_daily_limit()))


@dp.message(Command("stats"))
async def stats_cmd(message: Message):
    if not await is_owner(message.from_user.id):
        lang = await lang_of(message.from_user.id)
        await message.answer(tr(lang, "admin_only"))
        return
    users, subs = await db.stats()
    await message.answer(tr("fa", "stats", users=users, subs=subs))


@dp.message(Command("quota"))
async def quota_cmd(message: Message):
    if not await is_owner(message.from_user.id):
        lang = await lang_of(message.from_user.id)
        await message.answer(tr(lang, "admin_only"))
        return
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) == 1:
        limit = await db.get_daily_limit()
        await message.answer(tr("fa", "quota_status", limit=("نامحدود" if limit == 0 else limit)))
        return
    value = parts[1].strip().lower()
    if value in {"off", "نامحدود", "0"}:
        await db.set_daily_limit(0)
        await message.answer("محدودیت روزانه غیرفعال شد.")
        return
    try:
        limit = int(value)
        if limit < 1 or limit > 100000:
            raise ValueError
    except ValueError:
        await message.answer(tr("fa", "quota_usage"))
        return
    await db.set_daily_limit(limit)
    await message.answer(f"محدودیت روزانه روی {limit} پیام تنظیم شد.")


@dp.message(Command("cancel"))
async def cancel_cmd(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("انصراف داده شد.")


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


@dp.callback_query(F.data == "home")
async def home_cb(query: CallbackQuery):
    lang = await lang_of(query.from_user.id)
    name = query.from_user.first_name or "دوست من"
    await query.message.edit_text(tr(lang, "welcome", name=esc(name)), reply_markup=menu(lang))
    await query.answer()


@dp.callback_query(F.data == "language")
async def language_cb(query: CallbackQuery):
    lang = await lang_of(query.from_user.id)
    await query.message.answer(tr(lang, "choose_lang"), reply_markup=language_menu(lang))
    await query.answer()


@dp.callback_query(F.data == "model")
async def model_cb(query: CallbackQuery):
    lang = await lang_of(query.from_user.id)
    await query.message.answer(tr(lang, "model_choose"), reply_markup=model_menu(lang))
    await query.answer()


@dp.callback_query(F.data == "model:vibel-1.0")
async def select_model_cb(query: CallbackQuery):
    await query.answer("VibeL 1.0")


@dp.callback_query(F.data == "support")
async def support_cb(query: CallbackQuery):
    lang = await lang_of(query.from_user.id)
    await query.message.answer(tr(lang, "support_text"), reply_markup=back_menu(lang))
    await query.answer()


@dp.callback_query(F.data == "plans")
async def plans_cb(query: CallbackQuery):
    lang = await lang_of(query.from_user.id)
    await show_plans(query.message, lang)
    await query.answer()


@dp.callback_query(F.data == "help")
async def help_cb(query: CallbackQuery):
    lang = await lang_of(query.from_user.id)
    await query.message.answer(tr(lang, "help_text"), reply_markup=back_menu(lang))
    await query.answer()


@dp.callback_query(F.data.startswith("lang:"))
async def set_lang_cb(query: CallbackQuery):
    lang = query.data.split(":", 1)[1]
    await db.set_language(query.from_user.id, lang)
    await query.message.answer(tr(lang, "lang_saved"), reply_markup=menu(lang))
    await query.answer()


@dp.callback_query(F.data == "buy:pro")
async def buy_pro(query: CallbackQuery, bot: Bot):
    lang = await lang_of(query.from_user.id)
    if not await db.stars_enabled():
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


@dp.callback_query(F.data.startswith("adm:"))
async def admin_callbacks(query: CallbackQuery, state: FSMContext):
    if not await is_owner(query.from_user.id):
        await query.answer("دسترسی ندارید.", show_alert=True)
        return
    action = query.data.split(":", 1)[1]

    if action == "stats":
        users, subs = await db.stats()
        total, today = await db.message_stats()
        warnings = await db.warning_total()
        banned = await db.banned_total()
        await query.message.answer(
            f"آمار کامل\n\nکاربران: {users}\nاشتراک فعال: {subs}\n"
            f"کل پیام‌ها: {total}\nپیام‌های امروز: {today}\n"
            f"اخطارها: {warnings}\nبن‌شده‌ها: {banned}")
        await query.answer()
    elif action == "bcast":
        await state.set_state(AdminStates.broadcast)
        await query.message.answer("متن پیام برای پخش به همه کاربران را بفرست. برای انصراف /cancel")
        await query.answer()
    elif action == "limit":
        await query.message.answer("محدودیت روزانه را انتخاب کنید:", reply_markup=limit_menu())
        await query.answer()
    elif action.startswith("limit:"):
        try:
            value = int(action.split(":", 1)[1])
        except ValueError:
            await query.answer()
            return
        await db.set_daily_limit(value)
        await refresh_panel(query)
        await query.answer("ذخیره شد.")
    elif action == "stars":
        await db.set_stars_enabled(not await db.stars_enabled())
        await refresh_panel(query)
        await query.answer("تغییر کرد.")
    elif action == "panel":
        await refresh_panel(query)
        await query.answer()
    elif action == "grant":
        await state.set_state(AdminStates.grant)
        await query.message.answer("شناسه عددی کاربر و تعداد روز را بفرست (مثال: 123456789 30). برای انصراف /cancel")
        await query.answer()
    elif action == "revoke":
        await state.set_state(AdminStates.revoke)
        await query.message.answer("شناسه عددی کاربر را بفرست تا اشتراکش لغو شود. برای انصراف /cancel")
        await query.answer()
    elif action == "warnings":
        rows = await db.recent_warnings(10)
        if rows:
            listing = "\n".join(
                f"{row[0]} — اخطار {row[1]} — {(row[2] or '')[:60]} — {row[3][:16]}"
                for row in rows
            )
            text = "اخطارهای اخیر:\n\n" + listing
        else:
            text = "هیچ اخطاری ثبت نشده است."
        await query.message.answer(text[:4000])
        await query.answer()
    elif action == "clearwarn":
        await state.set_state(AdminStates.clearwarn)
        await query.message.answer("شناسه عددی کاربر را بفرست تا اخطارهایش پاک شود. برای انصراف /cancel")
        await query.answer()
    elif action == "ban":
        await state.set_state(AdminStates.ban)
        await query.message.answer("شناسه عددی کاربر را بفرست تا بن شود. برای انصراف /cancel")
        await query.answer()
    elif action == "unban":
        await state.set_state(AdminStates.unban)
        await query.message.answer("شناسه عددی کاربر را بفرست تا رفع بن شود. برای انصراف /cancel")
        await query.answer()
    elif action == "close":
        await state.clear()
        try:
            await query.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass
        await query.answer("پنل بسته شد.")
    else:
        await query.answer()


async def refresh_panel(query: CallbackQuery):
    try:
        await query.message.edit_text(
            await panel_text(),
            reply_markup=admin_kb(await db.stars_enabled(), await db.get_daily_limit()),
        )
    except Exception:
        await query.message.answer(
            await panel_text(),
            reply_markup=admin_kb(await db.stars_enabled(), await db.get_daily_limit()),
        )


@dp.message(AdminStates.broadcast, F.text)
async def admin_broadcast_input(message: Message, state: FSMContext, bot: Bot):
    await state.clear()
    text = message.text[:4000]
    ids = await db.all_user_ids()
    ok = fail = 0
    status = await message.answer("در حال پخش پیام...")
    for uid in ids:
        try:
            await bot.send_message(uid, text)
            ok += 1
        except Exception:
            try:
                await bot.send_message(uid, html.escape(strip_html(text)))
                ok += 1
            except Exception:
                fail += 1
        await asyncio.sleep(0.05)
    try:
        await status.edit_text(f"پخش پیام انجام شد.\nموفق: {ok}\nناموفق: {fail}")
    except Exception:
        pass


@dp.message(AdminStates.grant, F.text)
async def admin_grant_input(message: Message, state: FSMContext):
    await state.clear()
    parts = (message.text or "").split()
    try:
        uid = int(parts[0])
        days = int(parts[1]) if len(parts) > 1 else settings.pro_duration_days
        if days < 1 or days > 3650:
            raise ValueError
    except (ValueError, IndexError):
        await message.answer("قالب درست نیست. مثال: 123456789 30")
        return
    await db.activate_pro(uid, "manual", days)
    await message.answer(f"اشتراک پرمیوم برای کاربر {uid} به مدت {days} روز فعال شد.")


@dp.message(AdminStates.revoke, F.text)
async def admin_revoke_input(message: Message, state: FSMContext):
    await state.clear()
    try:
        uid = int((message.text or "").strip())
    except ValueError:
        await message.answer("شناسه عددی معتبر نیست.")
        return
    removed = await db.revoke_pro(uid)
    await message.answer("اشتراک لغو شد." if removed else "اشتراک فعالی برای این کاربر پیدا نشد.")


@dp.message(AdminStates.ban, F.text)
async def admin_ban_input(message: Message, state: FSMContext):
    await state.clear()
    try:
        uid = int((message.text or "").strip())
    except ValueError:
        await message.answer("شناسه عددی معتبر نیست.")
        return
    await db.ban_user(uid)
    await message.answer(f"کاربر {uid} بن شد؛ از این پس پاسخی از ربات دریافت نمی‌کند.")


@dp.message(AdminStates.unban, F.text)
async def admin_unban_input(message: Message, state: FSMContext):
    await state.clear()
    try:
        uid = int((message.text or "").strip())
    except ValueError:
        await message.answer("شناسه عددی معتبر نیست.")
        return
    removed = await db.unban_user(uid)
    await message.answer("رفع بن انجام شد." if removed else "این کاربر بن نشده بود.")


@dp.message(AdminStates.clearwarn, F.text)
async def admin_clearwarn_input(message: Message, state: FSMContext):
    await state.clear()
    try:
        uid = int((message.text or "").strip())
    except ValueError:
        await message.answer("شناسه عددی معتبر نیست.")
        return
    removed = await db.clear_warnings(uid)
    await message.answer("اخطارها پاک شد." if removed else "اخطاری برای این کاربر ثبت نشده بود.")


async def handle_insult(message: Message):
    count = await db.add_warning(message.from_user.id, (message.text or "")[:300])
    lang = await lang_of(message.from_user.id)
    try:
        await message.reply(tr(lang, "warning_text", count=count))
    except Exception:
        logging.exception("Could not send the warning message")
    if count >= 3 and settings.owner_id:
        try:
            await message.bot.send_message(
                settings.owner_id,
                f"کاربر {message.from_user.id} ({message.from_user.full_name}) اخطار شماره {count} گرفت.\n"
                f"متن پیام: {(message.text or '')[:200]}",
            )
        except Exception:
            pass


async def build_context(message: Message, is_private: bool, pro: bool) -> str:
    user = message.from_user
    username = f"@{user.username}" if user.username else "بدون username"
    parts = [
        f"نام نمایشی کاربر: {user.full_name}",
        f"username کاربر: {username}",
        f"شناسه عددی کاربر: {user.id}",
        f"سطح کاربر: {'پرمیوم' if pro else 'عادی'}",
        f"نوع گفتگو: {'خصوصی' if is_private else 'گروهی'}",
    ]
    if not is_private:
        parts.append(f"نام گروه: {message.chat.title or 'نامشخص'}")
    reply = message.reply_to_message
    if reply:
        if reply.from_user and reply.from_user.id != message.bot.id:
            reply_name = reply.from_user.full_name
            reply_username = f"@{reply.from_user.username}" if reply.from_user.username else None
            info = f"کاربری که به پیام او ریپلای شده: {reply_name} | شناسه: {reply.from_user.id}"
            if reply_username:
                info += f" | username: {reply_username}"
            parts.append(info)
            if not reply_username:
                parts.append(
                    "این کاربر username ندارد؛ اگر لازم شد او را منشن کنی، دقیقاً از این قالب استفاده کن: "
                    f'<a href="tg://user?id={reply.from_user.id}">{reply_name}</a>'
                )
        if reply.text:
            parts.append("متن پیام ریپلای‌شده: " + reply.text[:1500])
    saved_summary = await db.get_summary(user.id)
    if saved_summary:
        parts.append("خلاصه حافظه قبلی گفتگو: " + saved_summary)
    return "؛ ".join(parts)


@dp.message(F.text & ~F.text.startswith("/"))
async def chat_message(message: Message):
    if not message.from_user or message.from_user.id == message.bot.id:
        return
    uid = message.from_user.id
    text = message.text or ""

    is_private = message.chat.type == ChatType.PRIVATE
    is_reply_to_bot = bool(
        message.reply_to_message
        and message.reply_to_message.from_user
        and message.reply_to_message.from_user.id == message.bot.id
    )
    is_mentioned = bool(BOT_USERNAME and f"@{BOT_USERNAME.lower()}" in text.lower())

    # Automatic warning for insults against the creators/Vibegram, also in groups.
    if not await is_owner(uid) and insult_hit(text):
        await handle_insult(message)
        return

    # In groups, respond only when explicitly addressed.
    if not is_private and not (is_reply_to_bot or is_mentioned):
        return

    if await db.is_banned(uid):
        return

    await db.ensure_user(uid, message.from_user.username)
    lang = await lang_of(uid)
    pro = await is_owner(uid) or await db.is_pro(uid)
    daily_limit = await db.get_daily_limit()
    if not pro and daily_limit > 0 and not await db.consume_free_quota(uid):
        await message.answer(tr(lang, "free_limit"), reply_markup=menu(lang))
        return

    history_limit = 50 if pro else 20
    summary_threshold = 100 if pro else 40
    history = await db.get_history(uid, limit=history_limit)
    history.append({"role": "user", "content": text[:12000]})
    context = await build_context(message, is_private, pro)

    try:
        async with Typing(message.bot, message.chat.id):
            response = await answer(history, context=context)
    except RuntimeError as exc:
        logging.warning("AI unavailable: %s", exc)
        await message.answer(tr(lang, "no_ai"))
        return
    except Exception:
        logging.exception("AI request failed")
        await message.answer(tr(lang, "ai_error"))
        return

    await react(message)
    await send_chunked(message, response)

    await db.add_exchange(uid, text[:12000], response[:12000])
    saved_summary = await db.get_summary(uid)
    old_rows = await db.get_compaction_batch(uid, history_limit, summary_threshold)
    if old_rows:
        old_messages = [{"role": row[1], "content": row[2]} for row in old_rows]
        try:
            new_summary = await summarize_history(saved_summary, old_messages)
            await db.save_summary_and_delete(uid, new_summary, [row[0] for row in old_rows])
        except Exception:
            logging.exception("Could not compact conversation memory")


async def main():
    if not settings.bot_token:
        raise RuntimeError("VIBE_BOT_TOKEN is required")
    if not settings.owner_id:
        logging.warning("OWNER_ID is not set; the admin panel is disabled until you set it.")
    await db.init_db()
    session = AiohttpSession(api=TelegramAPIServer.from_base(settings.api_base))
    bot = Bot(token=settings.bot_token, session=session,
              default=DefaultBotProperties(parse_mode="HTML"))
    global BOT_USERNAME
    me = await bot.get_me()
    BOT_USERNAME = me.username or ""
    logging.info("VibeChat started as @%s", me.username)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
