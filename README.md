# VibeChatBot 1.0

Bilingual (Persian/English) AI assistant for Vibegram, using the Vibe Bot API gateway.

## Included in this starter
- Vibe Bot API base URL configuration (the documented aiogram base is `https://api.vibegram.chat`, without `/bot`)
- Long polling using aiogram 3
- Persian and English interface
- Inline-button main menu (no emoji in bot-authored text)
- Gemini then Groq fallback through OpenAI-compatible chat completions
- Per-user conversation history in SQLite
- Daily free quota
- Pro entitlement with expiry
- Telegram Stars invoice flow, pre-checkout validation and successful-payment handling
- Owner-only basic statistics
- Docker deployment

## Important compatibility note about Stars
The Vibegram documentation currently labels its gateway Telegram Bot API 7.x compatible and its visible method list does not explicitly document `sendInvoice`, `answerPreCheckoutQuery`, `pre_checkout_query`, or `successful_payment`. Therefore Stars are feature-gated and disabled by default.

1. Deploy with `ENABLE_STARS=false`.
2. Verify on Vibegram that `sendInvoice` with currency `XTR` is accepted, that pre-checkout updates arrive, and that successful-payment updates are delivered.
3. Only then set `ENABLE_STARS=true` and restart.
4. Do not sell paid access until an end-to-end test purchase and duplicate-update test pass.

For digital services on Telegram, Telegram's rules require Stars (`XTR`). The standard flow is invoice -> pre-checkout -> successful payment; persist the charge ID and provide `/paysupport`.

## Setup

1. Create `@VibeChatBot` using https://botfather.vibegram.chat/ and copy the token.
2. Copy `.env.example` to `.env`.
3. Set `VIBE_BOT_TOKEN`.
4. Add at least one AI provider key (`GEMINI_API_KEY` or `GROQ_API_KEY`).
5. Set `OWNER_ID` to the numeric Vibe user ID of the owner.
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

## Cloud deployment

Use any always-on Docker host that supports persistent volumes. Mount `/data` persistently because the SQLite database lives there. Set the variables from `.env.example` in the host's secret/environment settings. Do not commit `.env` or tokens to Git.

A free cloud tier may sleep, limit hours, or delete local storage. For reliable bot polling, use an always-on worker and persistent disk. SQLite is suitable for the initial single-instance bot; migrate to PostgreSQL before running multiple replicas.

## AI provider costs and limits

Gemini and Groq free tiers are subject to provider-specific rate limits and model availability. This project falls back to Groq if Gemini errors. It does not promise unlimited free inference. Review provider terms and quotas before launch.

## Current scope / next development steps

This is an executable MVP, not a full Mira clone. It does not yet implement image generation, voice transcription, web search, group moderation, Mini App, advanced agent tools, admin web dashboard, refunds, or subscription auto-renewal. Add these as separate modules after confirming the gateway's supported methods and event types.

## Security checklist
- Keep bot and AI keys in cloud secrets, never source control.
- Set `OWNER_ID` to a numeric account ID.
- Back up `/data`.
- Add privacy notice and data deletion flow before public launch.
- Add rate limiting and abuse monitoring before opening to large audiences.
- Test Stars in a test environment first.


## VibeL 1.0 personality and controls (v1.1)

- Public identity: Vibe / وایب, presented as VibeL 1.0 by VibeChat.
- Support: `@ThePouYa`; creator: Pouya; creator channel: `@VibeChat`.
- Persian/English welcome menu: Change language, Change model, Help, Support, Buy Premium.
- The only selectable model label is `VibeL 1.0`. The configured AI provider remains an implementation detail.
- Daily message limit defaults to unlimited (`FREE_DAILY_LIMIT=0`). The owner can set it at runtime with `/quota 20` or disable it with `/quota off`. `OWNER_ID` must be set to the owner's numeric Vibe user ID for owner commands.
- Conversation memory: regular users retain 20 recent messages plus a rolling summary compacted after 40 stored messages; Pro users retain 50 recent messages plus a rolling summary compacted after 100 stored messages. `/reset` clears both recent history and summary.
- In groups, the bot responds only when mentioned or when a user replies to a bot message. The bot must be allowed to receive those updates by the group privacy/access settings.
- Text capabilities include conversation, translation, summarization, writing, coding/debugging, tutoring, brainstorming, analysis of supplied text, planning and context-aware replies.
- Automatic group warnings, message reactions, media/file understanding, web search, and colored button styles are not enabled in this release. They require additional implementation and confirmation that Vibegram's deployed API supports the corresponding Telegram methods.
- Vibegram's published developer page currently describes compatibility with Telegram Bot API 7.x and lists standard message/chat/file methods, long polling, webhooks and Mini Apps. Do not assume newer Telegram Bot API 10.x features are available on Vibegram until verified.
