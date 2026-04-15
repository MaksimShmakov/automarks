# Telegram Booking Bot — Mini App

Telegram-бот с Mini App для записи на услуги (маникюр, педикюр).

## Структура

```
telegram-booking-bot/
├── backend/
│   ├── main.py          # FastAPI сервер (API)
│   ├── bot.py           # Telegram бот
│   └── requirements.txt
├── frontend/
│   ├── index.html       # Mini App
│   ├── style.css
│   └── app.js
├── .env.example
└── README.md
```

## Как запустить

### 1. Подготовка

```bash
cd telegram-booking-bot

# Создайте .env из примера
cp .env.example .env
```

Заполните `.env`:
- `BOT_TOKEN` — токен от [@BotFather](https://t.me/BotFather)
- `ADMIN_CHAT_ID` — ваш Telegram user ID (узнать у [@userinfobot](https://t.me/userinfobot))
- `WEBAPP_URL` — публичный URL фронтенда (см. шаг 4)

### 2. Установка зависимостей

```bash
cd backend
pip install -r requirements.txt
```

### 3. Запуск backend (API)

```bash
# Из директории backend/
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

API будет доступен на `http://localhost:8000`.

### 4. Запуск frontend

Для локальной разработки:

```bash
# Из директории frontend/
python -m http.server 8080
```

Frontend будет доступен на `http://localhost:8080`.

**Важно:** Telegram Mini App требует HTTPS. Для тестирования используйте **ngrok**:

```bash
# Терминал 1: туннель для frontend
ngrok http 8080
# Скопируйте HTTPS URL (например: https://abc123.ngrok-free.app)

# Терминал 2: туннель для backend
ngrok http 8000
```

Затем:
1. Пропишите ngrok URL фронтенда в `.env` → `WEBAPP_URL`
2. В `frontend/app.js` замените `API_URL` на ngrok URL бэкенда

### 5. Запуск бота

```bash
# Из директории backend/
python bot.py
```

### 6. Тестирование

1. Откройте бота в Telegram
2. Отправьте `/start`
3. Нажмите кнопку «Записаться»
4. Выберите услугу → дату/время → подтвердите

## API Endpoints

| Метод | URL | Описание |
|-------|-----|----------|
| GET | `/api/services` | Список услуг |
| GET | `/api/slots?service_id=1` | Доступные слоты |
| POST | `/api/book` | Создать запись |
| GET | `/api/bookings` | Все записи |
