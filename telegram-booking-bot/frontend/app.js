// Конфигурация
const API_URL = window.API_URL || "http://localhost:8000";

// Telegram WebApp
const tg = window.Telegram.WebApp;
tg.ready();
tg.expand();

// Применяем тему Telegram
if (tg.themeParams) {
    const root = document.documentElement;
    if (tg.themeParams.bg_color)
        root.style.setProperty("--tg-theme-bg-color", tg.themeParams.bg_color);
    if (tg.themeParams.text_color)
        root.style.setProperty("--tg-theme-text-color", tg.themeParams.text_color);
    if (tg.themeParams.hint_color)
        root.style.setProperty("--tg-theme-hint-color", tg.themeParams.hint_color);
    if (tg.themeParams.button_color)
        root.style.setProperty("--tg-theme-button-color", tg.themeParams.button_color);
    if (tg.themeParams.button_text_color)
        root.style.setProperty("--tg-theme-button-text-color", tg.themeParams.button_text_color);
    if (tg.themeParams.secondary_bg_color)
        root.style.setProperty("--tg-theme-secondary-bg-color", tg.themeParams.secondary_bg_color);
}

// Состояние приложения
let state = {
    services: [],
    selectedService: null,
    selectedDate: null,
    selectedDateLabel: null,
    selectedTime: null,
};

// ===== Навигация =====

function showScreen(name) {
    document.querySelectorAll(".screen").forEach((s) => s.classList.remove("active"));
    document.getElementById(`screen-${name}`).classList.add("active");
}

function showLoading() {
    document.getElementById("loading").classList.remove("hidden");
}

function hideLoading() {
    document.getElementById("loading").classList.add("hidden");
}

// ===== API =====

async function api(path, options = {}) {
    const res = await fetch(`${API_URL}${path}`, {
        headers: { "Content-Type": "application/json" },
        ...options,
    });
    return res.json();
}

// ===== Экран 1: Услуги =====

async function loadServices() {
    try {
        const data = await api("/api/services");
        state.services = data.services;
        renderServices();
    } catch (e) {
        console.error("Failed to load services:", e);
    }
}

function renderServices() {
    const list = document.getElementById("services-list");
    list.innerHTML = state.services
        .map(
            (s) => `
        <div class="service-card" onclick="selectService(${s.id})">
            <div class="service-emoji">${s.emoji}</div>
            <div class="service-info">
                <div class="service-name">${s.name}</div>
                <div class="service-meta">${s.duration} мин</div>
            </div>
            <div class="service-price">${s.price} ₽</div>
        </div>
    `
        )
        .join("");
}

function selectService(id) {
    state.selectedService = state.services.find((s) => s.id === id);
    state.selectedDate = null;
    state.selectedTime = null;
    loadSlots();
    showScreen("slots");
}

// ===== Экран 2: Слоты =====

async function loadSlots() {
    const info = document.getElementById("selected-service-info");
    const s = state.selectedService;
    info.innerHTML = `${s.emoji} ${s.name} — ${s.price} ₽`;

    try {
        const data = await api(`/api/slots?service_id=${s.id}`);
        renderSlots(data.slots);
    } catch (e) {
        console.error("Failed to load slots:", e);
    }
}

function renderSlots(slots) {
    const container = document.getElementById("slots-list");
    container.innerHTML = slots
        .map(
            (day) => `
        <div class="day-group">
            <div class="day-label">📅 ${day.label}</div>
            ${
                day.hours.length > 0
                    ? `<div class="time-grid">
                    ${day.hours
                        .map(
                            (h) =>
                                `<button class="time-btn" onclick="selectTime('${day.date}', '${day.label}', '${h}', this)">${h}</button>`
                        )
                        .join("")}
                </div>`
                    : `<div class="no-slots">Нет свободных слотов</div>`
            }
        </div>
    `
        )
        .join("");
}

function selectTime(date, dateLabel, time, btn) {
    // Убираем выделение со всех кнопок
    document.querySelectorAll(".time-btn").forEach((b) => b.classList.remove("selected"));
    btn.classList.add("selected");

    state.selectedDate = date;
    state.selectedDateLabel = dateLabel;
    state.selectedTime = time;

    // Показываем экран подтверждения через небольшую задержку
    setTimeout(() => {
        renderConfirm();
        showScreen("confirm");
    }, 200);
}

// ===== Экран 3: Подтверждение =====

function renderConfirm() {
    const s = state.selectedService;
    const details = document.getElementById("confirm-details");
    details.innerHTML = `
        <div class="confirm-row">
            <span class="confirm-label">Услуга</span>
            <span class="confirm-value">${s.emoji} ${s.name}</span>
        </div>
        <div class="confirm-row">
            <span class="confirm-label">Дата</span>
            <span class="confirm-value">${state.selectedDateLabel}</span>
        </div>
        <div class="confirm-row">
            <span class="confirm-label">Время</span>
            <span class="confirm-value">${state.selectedTime}</span>
        </div>
        <div class="confirm-row">
            <span class="confirm-label">Длительность</span>
            <span class="confirm-value">${s.duration} мин</span>
        </div>
        <div class="confirm-row">
            <span class="confirm-label">Итого</span>
            <span class="confirm-value confirm-total">${s.price} ₽</span>
        </div>
    `;
}

async function submitBooking() {
    const btn = document.getElementById("pay-btn");
    btn.disabled = true;
    btn.textContent = "Обработка...";
    showLoading();

    const s = state.selectedService;
    const body = {
        initData: tg.initData || "",
        service_id: s.id,
        service_name: s.name,
        price: s.price,
        date: state.selectedDate,
        date_label: state.selectedDateLabel,
        time: state.selectedTime,
    };

    try {
        const data = await api("/api/book", {
            method: "POST",
            body: JSON.stringify(body),
        });

        if (data.ok) {
            document.getElementById("success-message").textContent =
                `${s.name}, ${state.selectedDateLabel} в ${state.selectedTime}.\nСтоимость: ${s.price} ₽`;
            showScreen("success");
        } else {
            alert("Ошибка при создании записи");
            btn.disabled = false;
            btn.textContent = "💳 Оплатить";
        }
    } catch (e) {
        console.error("Booking failed:", e);
        alert("Ошибка соединения с сервером");
        btn.disabled = false;
        btn.textContent = "💳 Оплатить";
    } finally {
        hideLoading();
    }
}

// ===== Инициализация =====

loadServices();
