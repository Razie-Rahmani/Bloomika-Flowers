# Bloomika Flowers

A Telegram-native storefront for a small flower shop. Customers browse and order through a Telegram Mini App; the shop owner runs the entire backend — products, orders, payment confirmation, FAQ, contact info — from inside the same Telegram bot, with no separate admin dashboard to log into.

**Status:** V1, in active use. Functional end-to-end, with known rough edges listed below.

---

## What it does

**Customer side (Mini App)**
- Browse a product catalog (photo, name, price, category) served from the backend
- Add items to a cart, adjust quantities, check out with name/address/postal code/phone
- See a card number and instructions to pay, then send the payment receipt as a photo directly in the Telegram chat with the bot
- Get notified automatically, right in the chat, as their order moves through payment review → confirmed/rejected → delivered
- Access FAQ and contact info from the bot's main menu

**Admin side (same bot, gated to one Telegram user ID)**
- Add/edit products, including photos, entirely through chat prompts — no web form
- View the last 20 orders, drill into any order's full detail, and confirm/reject/mark-delivered with inline buttons
- Edit FAQ answers and contact info without touching code or redeploying
- Receive every incoming payment receipt as a photo with the order details and Confirm/Reject buttons attached

## Why Telegram-first, not a normal web store

The target customers and the shop owner are both already living in Telegram, and a Mini App means zero app-store friction. It also sidesteps two problems that hit this specific market: general web-hosting/CDN access (e.g. Cloudinary) can be unreliable from Iran under sanctions-related restrictions, and a from-scratch web store would need its own auth, payments UI, and admin panel built from zero. Routing everything — catalog media, admin actions, payment receipts, order status — through Telegram's own infrastructure removes most of that surface area for a V1.

## Tech stack

| Layer | Choice |
|---|---|
| Backend framework | FastAPI (Python), async |
| Telegram bot | aiogram 3, webhook-based (not long-polling) |
| Database | PostgreSQL (Neon), accessed via `psycopg2` |
| Frontend | Vanilla HTML/CSS/JS — no framework, no build step |
| Frontend runtime | Telegram Mini Apps JS SDK (`telegram-web-app.js`) |
| Font | Vazirmatn (self-hosted via CDN), for proper Farsi rendering |
| Hosting | Render — one Web Service (backend) + one Static Site (frontend) |
| Image storage | Product photos and payment receipts stored as `BYTEA` directly in Postgres — no third-party CDN dependency |

Full pinned dependency list: [`backend/requirements.txt`](backend/requirements.txt).

## Architecture

- **Single FastAPI process** hosts both the customer-facing REST API and the Telegram bot. Telegram delivers updates via webhook to `POST /webhook`; `aiogram`'s dispatcher handles them in-process — there's no separate bot worker.
- **One Postgres database**, four tables: `products`, `orders`, `faq`, `contact_info`. `orders.status` is the state machine driving everything (`pending payment` → `pending_confirmation` → `confirmed` / `rejected` → `delivered`).
- **`customer_telegram_id`** on every order is the thread tying the Mini App checkout to the bot conversation — it's what lets the bot match an incoming receipt photo, or a status change, back to the right customer and order.
- **Admin auth** is a shared `ADMIN_API_TOKEN` header for the REST admin endpoints (curl/Postman-level access), and a hardcoded `ADMIN_ID` Telegram user ID check for every bot-side admin action. The bot's own admin flows call the REST handler functions directly in-process, so they never go through the token check — it's purely gate against outside REST access.
- **Payment receipts** are not uploaded through the REST API. Early versions tried that and hit two independent, unfixable-from-app-code failures: large files were silently dropped at the platform/proxy level before reaching FastAPI, and small files were flaky specifically inside Telegram's iOS Mini App WebView. V1 instead has the customer send the receipt as a normal Telegram photo message to the bot, using the same `bot.download()` mechanism already used for product photos. Tradeoff: this only works for customers who opened the shop through the bot (so `customer_telegram_id` is populated) — opening the frontend URL directly in a browser is not a supported path for payment.
- **Order status notifications** are sent inline, synchronously, the moment `update_status()` runs — the same function both the admin's Confirm/Reject/Deliver buttons and the REST `PATCH /orders/{id}` endpoint call, so there's one place responsible for messaging the customer regardless of which path triggered the change.

## Repo structure

```
backend/
  main.py           FastAPI app + aiogram bot (routes, webhook, all bot handlers)
  database.py       Postgres connection, schema (init_db), all queries
  requirements.txt  Pinned Python dependencies
frontend/
  index.html        Mini App shell
  app.js            Catalog rendering, cart, checkout
  style.css         Design system (tokens) + component styles
```

## Frontend design

The UI isn't a generic template — it's built off a deliberate design-token system in `style.css`: a romantic-pink brand palette paired with a botanical green for success/confirmation states, RTL layout throughout (`dir="rtl"`, `lang="fa"`), Vazirmatn as the display font for correct Farsi shaping, and a consistent spacing/radius/shadow scale rather than ad-hoc values. No component framework — plain DOM manipulation in `app.js`, which keeps the Mini App's payload small and avoids a build step entirely.
The CSS design system was developed with assistance from Claude using the [UI/UX Pro Max](https://github.com/nextlevelbuilder/ui-ux-pro-max-skill) skill.

## Environment variables

Set these in Render's dashboard (or a local `.env` for development) — none are committed to the repo:

| Variable | Used for |
|---|---|
| `BOT_TOKEN` | Telegram bot token from BotFather |
| `ADMIN_ID` | Telegram user ID authorized to use the admin panel |
| `WEBHOOK_URL` | Public HTTPS URL Telegram sends updates to |
| `WEBHOOK_SECRET` | Shared secret validated on every incoming webhook call |
| `DATABASE_URL` | Postgres connection string (Neon) |
| `ADMIN_API_TOKEN` | Bearer-style token gating the REST admin endpoints |

## Deployment

Two Render services, deployed from this repo:
- **Web Service** (`backend/`) — runs the FastAPI app; sets the Telegram webhook on startup via the app's `lifespan` handler.
- **Static Site** (`frontend/`) — serves the Mini App; its URL is what's registered as the bot's `WebAppInfo` URL and what Telegram opens when a customer taps "Open Shop."

`init_db()` runs on every backend boot and is safe to run repeatedly — it only creates tables/seeds default rows that don't already exist.

## Known issues

This is a working V1, not a finished product. Known problems, in rough order of impact:

- **Mini App geo-blocking from Iranian IPs.** Render's infrastructure has been observed blocking or degrading access from Iranian IP ranges for some users — this is a hosting-provider-level issue, not fixable from application code. A migration to a host without this restriction (e.g. Hetzner, Fly.io) may eventually be needed.
- **Payment flow requires the bot, not just the Mini App.** A customer who reaches the frontend URL directly in a browser (rather than through the Telegram bot) has no `customer_telegram_id`, so there's no way to match a receipt they send back to an order. Accepted tradeoff for V1, not yet solved.
- **No automated tests.** All verification so far has been manual, via Render logs and live testing across device/browser combinations.
- **Order status values are inconsistent in style** — `"pending payment"` (with a space) vs. `"pending_confirmation"` (underscore) vs. `"confirmed"`/`"rejected"`/`"delivered"`. Cosmetic, but a trap for future `WHERE status = ...` queries if the exact string isn't matched.
- **No rate limiting** on the public, unauthenticated endpoints (`GET /products`, `POST /orders/`), so both are open to being spammed.
- **Single shared admin token and single hardcoded admin Telegram ID** — fine for one shop with one operator, not built for multiple admins or role separation.
- **No image compression** — product photos and payment receipts are stored as raw bytes in Postgres with no resizing/compression step, so the database will grow faster than it needs to as more products and orders accumulate.
- **No pagination** on the REST `GET /orders` endpoint or built-in admin order list beyond the bot menu's hardcoded `LIMIT 20` — will need addressing once order volume grows.

## Roadmap / not yet built

- Real payment gateway integration (currently manual bank-transfer + receipt review)
- Admin dashboard beyond the bot's inline-keyboard flows, if/when order volume justifies it
- Automated tests and CI
- A standalone website, if demand outgrows what a Telegram-only storefront can handle