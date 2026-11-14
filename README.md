# VibeChatBot 1.2 — Vibe Ai Update

Bilingual (Persian/English) AI assistant for Vibegram, using the Vibe Bot API gateway.
Bot username: `@VibeChatBot` — created via https://botfather.vibegram.chat/

## What is new in 1.2

- **New Vibe role (VibeL 1.0):** public identity وایب / Vibe / Vibe Ai, model `VibeL 1.0` only, made by VibeChat (`@VibeChat`), creator Pouya (`@ThePouYa` support), Vibegram owner Shayan Heydari. The bot never reveals the underlying provider and never names any other company. Good behaviour is met warmly, bad behaviour gets a sharp human-like answer back (no profanity, no family insults).
- **Exact start screen:** welcome text with glass buttons: Change language | Change model / Help | Support / Buy Premium. The premium button appears last in its own row.
- **English buttons in sᴍᴀʟʟᴄᴀᴘS** (`ᴄʜᴀɴɢᴇ ʟᴀɴɢᴜᴀɢᴇ`, `ʜᴇʟᴘ`, `sᴜᴘᴘᴏʀᴛ`, `ʙᴜʏ ᴘʀᴇᴍɪᴜᴍ`, `✓ ᴠɪʙᴇʟ 1.0`).
- **Admin panel** (`/admin`, owner only): full stats, broadcast to all users, daily-limit switch (unlimited / 20 / 50 / 100), runtime Premium purchase on/off toggle (no restart needed), manual grant/revoke of subscriptions, warning list and per-user warning reset, ban/unban by numeric ID.
- **Automatic warnings:** insults against the bot, its creators or Vibegram are detected and the user automatically receives a formal warning; from the 3rd warning the owner is notified. Works in private chats and in groups the bot can read.
- **Smart reactions:** the bot analyses the user's message (thanks, love, fun, sadness, doubt, greeting, question, praise) and reacts with a matching emoji via `setMessageReaction`. If the gateway does not support reactions, it is skipped silently.
- **Typing indicator:** the "typing..." chat action runs while the AI generates, so chats feel like Mira/ChatGPT-style conversations.
- **Group awareness:** when added to a group the bot sends a short greeting; it replies when mentioned or when someone replies to it; when the user replies to another person, the replied-to user's name, username and numeric ID are given to the model so Vibe can mention them correctly (HTML mention fallback for users without a username).
- **Crash-proof sending:** every AI reply is sent as HTML with a plain-text fallback per chunk, so malformed model markup can never break a reply; user names are HTML-escaped.
- **Memory:** free users keep 20 recent messages + a rolling summary after 40 stored; Premium keeps 50 + 100. `/reset` clears both. Default daily limit is unlimited; the owner can set one at runtime from the panel or `/quota`.
- **Help rewritten:** only the essential commands remain (`/start`, `/help`, `/reset`, `/myid`); extra commands were removed from help.

## Included in this starter

- Vibe Bot API base URL configuration (the documented aiogram base is `https://api.vibegram.chat`, without `/bot`)
- Long polling using aiogram 3
- Persian and English interface with inline-button main menu
- Gemini then Groq fallback through OpenAI-compatible chat completions
- Per-user conversation history and rolling summary in SQLite
- Pro entitlement with expiry, Stars invoice flow, pre-checkout validation and successful-payment handling
- Docker deployment

## Important compatibility notes (verified against the docs)

- The Vibegram docs claim full Telegram Bot API compatibility but explicitly document only the basic messaging methods (`getMe`, `sendMessage`, `sendPhoto`, `sendDocument`, `sendVoice`, `sendVideo`, `editMessageText`, `deleteMessage`, `setWebhook`, `getWebhookInfo`, `deleteWebhook`). Reactions, chat-member updates and Stars are **not** in the documented list.
- Therefore: reactions and the group greeting are wrapped in silent try/except — if the gateway rejects them, the bot keeps working without them.
- **Colored buttons:** the documented API has no button-color parameter, so no unknown fields are sent (that would risk 400 errors). Buttons render with the messenger's own glass style; when Vibegram documents a color parameter, add it to `menu()` in `app/main.py`.
- **Stars are feature-gated:** disabled by default. Verify on Vibegram that `sendInvoice` with currency `XTR`, pre-checkout and successful-payment updates work, then either set `ENABLE_STARS=true` before first run or flip "خرید پرمیوم" in `/admin` at runtime.

## Setup

1. Create `@VibeChatBot` using https://botfather.vibegram.chat/ and copy the token.
2. Copy `.env.example` to `.env`.
3. Set `VIBE_BOT_TOKEN`.
4. Add at least one AI provider key (`GEMINI_API_KEY` or `GROQ_API_KEY`).
5. Set `OWNER_ID` to the numeric Vibe user ID of the owner (get it from the bot with `/myid`). Without it the admin panel stays off.
6. Run:

```bash
docker compose up -d --build
docker compose logs -f
```

For local development:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python -m app.main
```

## Cloud deployment (GitHub + free hosting)

- Push the `vibechatbot/` folder to GitHub (never commit `.env`).
- On a free deploy service use the Dockerfile; mount or persist `/data` if the platform supports volumes, because the SQLite database lives there. Free tiers that sleep or wipe storage will lose history and subscriptions.
- Set all variables from `.env.example` in the platform's environment/secret settings.

## Admin panel reference (`/admin`)

| Button | Action |
| --- | --- |
| آمار کامل | users, active subs, total/today messages, warnings, bans |
| پخش پیام | broadcast a message to every registered user |
| محدودیت روزانه | unlimited / 20 / 50 / 100 messages per day |
| خرید پرمیوم | toggle premium purchase on/off at runtime |
| اعطای اشتراک | `user_id days` — grant Pro manually |
| لغو اشتراک | revoke a Pro subscription |
| اخطارها / پاک‌کردن اخطار | list recent warnings / reset a user's warnings |
| بن کاربر / رفع بن | block or unblock a user by numeric ID |

While an input is expected, send `/cancel` to abort.

## Security checklist

- Keep bot and AI keys in cloud secrets, never in source control.
- Set `OWNER_ID` to a numeric account ID.
- Back up `/data`.
- Test Stars in a test environment first; do not sell access until an end-to-end purchase passes.
- In groups, the bot only receives what Telegram-style privacy allows; to read all group messages, disable privacy mode for the bot in Vibe BotFather or make it an admin.
