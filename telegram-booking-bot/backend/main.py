import os
import json
import hashlib
import hmac
import logging
from datetime import datetime, timedelta
from urllib.parse import parse_qsl

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

import telegram

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID", "")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Booking Bot API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory хранилище записей
bookings: list[dict] = []


def validate_telegram_data(init_data: str) -> dict | None:
    """Проверяет подпись данных от Telegram Mini App."""
    parsed = dict(parse_qsl(init_data, keep_blank_values=True))
    received_hash = parsed.pop("hash", None)
    if not received_hash:
        return None

    data_check_string = "\n".join(
        f"{k}={v}" for k, v in sorted(parsed.items())
    )
    secret_key = hmac.new(
        b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256
    ).digest()
    computed_hash = hmac.new(
        secret_key, data_check_string.encode(), hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(computed_hash, received_hash):
        return None

    user_data = parsed.get("user")
    if user_data:
        return json.loads(user_data)
    return None


@app.get("/api/services")
async def get_services():
    """Список доступных услуг."""
    services = [
        {
            "id": 1,
            "name": "Маникюр классический",
            "price": 1500,
            "duration": 60,
            "emoji": "\U0001f485",
        },
        {
            "id": 2,
            "name": "Маникюр с покрытием",
            "price": 2500,
            "duration": 90,
            "emoji": "\u2728",
        },
        {
            "id": 3,
            "name": "Педикюр классический",
            "price": 2000,
            "duration": 60,
            "emoji": "\U0001f9b6",
        },
        {
            "id": 4,
            "name": "Педикюр с покрытием",
            "price": 3000,
            "duration": 90,
            "emoji": "\U0001f48e",
        },
    ]
    return {"services": services}


@app.get("/api/slots")
async def get_slots(service_id: int):
    """Доступные слоты на ближайшие 3 дня."""
    today = datetime.now()
    slots = []
    hours = ["10:00", "11:30", "13:00", "14:30", "16:00", "17:30"]

    for day_offset in range(1, 4):
        date = (today + timedelta(days=day_offset)).replace(
            hour=0, minute=0, second=0, microsecond=0,
        )
        date_str = date.strftime("%Y-%m-%d")
        day_label = date.strftime("%d.%m.%Y")

        available_hours = []
        for h in hours:
            # Проверяем, не занят ли слот
            is_booked = any(
                b["date"] == date_str
                and b["time"] == h
                and b["service_id"] == service_id
                for b in bookings
            )
            if not is_booked:
                available_hours.append(h)

        slots.append({
            "date": date_str,
            "label": day_label,
            "hours": available_hours,
        })

    return {"slots": slots}


@app.post("/api/book")
async def create_booking(request: Request):
    """Создать запись."""
    body = await request.json()

    init_data = body.get("initData", "")
    service_id = body.get("service_id")
    service_name = body.get("service_name")
    price = body.get("price")
    date = body.get("date")
    date_label = body.get("date_label")
    time_slot = body.get("time")

    # Извлекаем данные пользователя
    user = validate_telegram_data(init_data)
    user_id = None
    user_name = "Гость"

    if user:
        user_id = user.get("id")
        first = user.get("first_name", "")
        last = user.get("last_name", "")
        username = user.get("username", "")
        user_name = f"{first} {last}".strip()
        if username:
            user_name += f" (@{username})"
    else:
        # Для тестирования без валидации
        user_id = body.get("user_id")
        user_name = body.get("user_name", "Тестовый пользователь")

    booking = {
        "id": len(bookings) + 1,
        "user_id": user_id,
        "user_name": user_name,
        "service_id": service_id,
        "service_name": service_name,
        "price": price,
        "date": date,
        "date_label": date_label,
        "time": time_slot,
        "created_at": datetime.now().isoformat(),
    }
    bookings.append(booking)
    logger.info("New booking: %s", booking)

    # Отправляем сообщения через Telegram Bot API
    if BOT_TOKEN:
        bot = telegram.Bot(token=BOT_TOKEN)

        # Сообщение пользователю
        if user_id:
            user_message = (
                f"\u2705 *Вы записаны!*\n\n"
                f"\U0001f485 Услуга: {service_name}\n"
                f"\U0001f4c5 Дата: {date_label}\n"
                f"\U0001f552 Время: {time_slot}\n"
                f"\U0001f4b0 Стоимость: {price} \u20bd\n\n"
                f"Ждём вас! \U0001f60a"
            )
            try:
                await bot.send_message(
                    chat_id=user_id,
                    text=user_message,
                    parse_mode="Markdown",
                )
            except Exception as e:
                logger.error("Failed to send message to user: %s", e)

        # Сообщение администратору
        if ADMIN_CHAT_ID:
            admin_message = (
                f"\U0001f4cb *Новая запись!*\n\n"
                f"\U0001f464 Клиент: {user_name}\n"
                f"\U0001f485 Услуга: {service_name}\n"
                f"\U0001f4c5 Дата: {date_label}\n"
                f"\U0001f552 Время: {time_slot}\n"
                f"\U0001f4b0 Стоимость: {price} \u20bd"
            )
            try:
                await bot.send_message(
                    chat_id=int(ADMIN_CHAT_ID),
                    text=admin_message,
                    parse_mode="Markdown",
                )
            except Exception as e:
                logger.error("Failed to send message to admin: %s", e)

    return JSONResponse({"ok": True, "booking": booking})


@app.get("/api/bookings")
async def list_bookings():
    """Все записи (для админки)."""
    return {"bookings": bookings}
