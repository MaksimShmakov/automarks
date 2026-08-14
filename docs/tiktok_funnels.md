# Раздел «TikTok-воронки» — деплой и функционал

Порт standalone-сервиса `el-tiktok-funnels-auto` (FastAPI + React) в automarks как
раздел приложения `marks`. Внешний вид — Django-шаблоны на Bootstrap; логика и
фичи совпадают с сервисом.

---

## Часть 1. Деплой без риска для других баз

### Почему деплой безопасен

1. **Раздел живёт только в собственной БД automarks.** Все данные — в двух новых
   таблицах Postgres-контейнера automarks (`db`, том `pgdata`). Никакие другие
   сервисы/БД на сервере не затрагиваются — automarks изолирован своим контейнером.

2. **Миграции только добавляют, ничего не меняют.** Две миграции:
   - `0032_tiktok_funnels` — `CREATE TABLE marks_tiktokaccount` + `CREATE TABLE marks_tiktokfunnelrequest`;
   - `0033_salebot_export_ready` — `ALTER TABLE marks_tiktokfunnelrequest ADD COLUMN salebot_export_ready`.

   Ни одной операции над существующими таблицами (`marks_bot`, `marks_tag`,
   `marks_funnel`, `marks_taskrequest`, …). Единственная связь с чужой таблицей —
   FK `created_by → auth_user` (ссылка на общую таблицу пользователей Django,
   `ON DELETE SET NULL`); саму `auth_user` миграция не меняет.

   Проверить перед применением прямо на проде:
   ```bash
   docker compose exec web python manage.py sqlmigrate marks 0032
   docker compose exec web python manage.py sqlmigrate marks 0033
   ```
   Увидишь только `CREATE TABLE` / `ADD COLUMN` по двум нашим таблицам.

3. **Склад automarks напрямую не трогает.** Удалённая БД `activation_data`
   (`tt_funnels` / `tiktok_accounts`) на другом сервере пишется исключительно через
   n8n. Деплой automarks физически не может задеть складскую БД — только POST в
   вебхук n8n (а upsert выполняет уже сам n8n).

### Шаги деплоя

1. **Забрать код:**
   ```bash
   cd /path/to/automarks
   git pull
   ```

2. **Добавить переменные окружения** в `.env` (см. `.env.example`, блок «Раздел
   TikTok-воронок»):
   ```env
   FUNNELS_DEV_TOKEN=<длинный-случайный-токен>   # гейт Дев-панели + Кабинетов
   YM_COUNTER_ID=<id счётчика Яндекс.Метрики>     # для генерации скрипта лендинга
   FUNNELS_WEBHOOK_URL=<url вебхука сбора визитов> # тот, что зашивается в скрипт
   FUNNELS_WEBHOOK_TOKEN=<токен вебхука>
   LANDING_BASE_URL=https://go-egeland.ru          # база рекламной UTM-ссылки
   N8N_SYNC_URL=<url вебхука n8n funnel-sync>      # dual-write в склад
   N8N_SYNC_TOKEN=<Authorization для n8n>
   FUNNELS_NOTIFY_CHAT_ID=<chat_id для уведомлений о заявках>  # опц.
   ```
   Проброс этих переменных в контейнер `web` уже прописан в `docker-compose.yml`.

3. **Пересобрать и поднять** (миграции применяются автоматически в `entrypoint.sh`
   → `manage.py migrate --noinput`):
   ```bash
   docker compose up -d --build web
   ```

4. **Проверить, что применились ровно наши миграции и создались только 2 таблицы:**
   ```bash
   docker compose exec web python manage.py showmigrations marks | tail -5
   # 0032_tiktok_funnels [X], 0033_salebot_export_ready [X]
   docker compose exec db psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
     -c "\dt marks_tiktok*"
   # marks_tiktokaccount, marks_tiktokfunnelrequest
   ```

### Откат

Безопасен и локален — дропает только две наши таблицы:
```bash
docker compose exec web python manage.py migrate marks 0031
```

---

## Часть 2. Полный функционал

### Роли и доступ

- **Заявка** — за логином automarks (любой авторизованный пользователь).
- **Дев-панель** и **Кабинеты** — логин **плюс** токен-гейт: один общий токен
  `FUNNELS_DEV_TOKEN` (server-side аналог `X-Dev-Token`, хранится флагом в сессии
  после ввода на `/tiktok/unlock/`).

Пункт меню «TikTok-воронки» (выпадашка: Заявка / Дев-панель / Кабинеты).

### Модель данных (2 таблицы в БД automarks)

**`marks_tiktokaccount`** — рекламный кабинет TikTok (токен 1:1 с кабинетом):

| поле | тип | смысл |
|---|---|---|
| `account_no` | PK, text | номер кабинета (свободная строка) |
| `advertiser_id` | text | ID рекламодателя |
| `access_token` | text | токен CAPI |
| `note` | text | заметка |
| `created_at` | datetime | |

**`marks_tiktokfunnelrequest`** — воронка = один лендинг:

| поле | тип | смысл |
|---|---|---|
| `id` | PK, bigint | суррогатный ключ |
| `landing_endpoint` | text, unique, nullable | `location.pathname`, напр. `/pasha_all` |
| `offer` | text | оффер/метка |
| `bot_url` / `bot_name` | text | ссылка на бота и распарсенный идентификатор |
| `page_type` | `button`/`mirror`/`''` | какой JS-шаблон генерить |
| `pixel_code` | text | `event_source_id` |
| `account_no` | text (без FK) | какой кабинет шлёт события |
| `utm_source` / `utm_medium` / `utm_term` | text | 3 хранимых UTM |
| `comment` | text | |
| `status` | `pending`/`active`/`archived` | |
| `salebot_export_ready` | bool | «В сейлботе достроен экспорт» — обязательно для активации |
| `warehouse_synced` | bool | долетела ли строка в склад |
| `created_by` | FK→auth_user, nullable | кто создал |
| `created_at` / `updated_at` | datetime | |

`campaign`/`content`/`id`/`ttclid` в БД **не хранятся** — это фиксированные макросы,
которые TikTok подставляет в ссылку сам (отсюда 6 меток, но в БД только 3).

### Куда и как летят данные

```
  Маркетолог/разработчик (браузер)
          │  создаёт/правит воронку и кабинет
          ▼
  ┌─────────────────────────┐
  │  automarks (Django)     │   ← источник правды
  │  marks_tiktokfunnel...  │
  │  marks_tiktokaccount    │
  └───────────┬─────────────┘
              │  синхронный POST JSON (requests)
              │  {type: funnel|account, ...}
              ▼
  ┌─────────────────────────┐
  │  n8n вебхук funnel-sync │   Authorization: N8N_SYNC_TOKEN
  └───────────┬─────────────┘
              │  UPSERT
              ▼
  ┌───────────────────────────────────────────┐
  │  СКЛАД activation_data (удалённый сервер)  │
  │  tt_funnels          ← из воронок          │
  │  tiktok_accounts     ← из кабинетов        │
  │  visits_data         ← из скрипта лендинга │
  └───────────┬───────────────────────────────┘
              │  читают CAPI-воркфлоу n8n
              │  (tt_funnels ⋈ tiktok_accounts ⋈ visits_data)
              ▼
        TikTok Events API (Subscribe/Purchase/Click)
```

Три независимых потока данных:

1. **Воронка/кабинет → automarks → n8n → склад.**
   На create/update воронки или кабинета automarks пишет строку в свою БД (источник
   правды) и **синхронно** шлёт POST в вебхук n8n `funnel-sync`
   (`marks/services/tiktok_sync.py`). n8n делает upsert в `activation_data.tt_funnels`
   / `tiktok_accounts`. Пустые строки → `NULL` (важно для `account_no`). Если
   n8n/сеть недоступны — воронка всё равно сохранена, `warehouse_synced=False`,
   в Дев-панели кнопка «В склад» для ретрая. Без `landing_endpoint` синк воронки
   пропускается (складу нечем делать upsert).

2. **Лендинг-скрипт → вебхук сбора → visits_data.** Раздел лишь **генерит** JS
   (`marks/services/landing_templates.py`, шаблоны button/mirror) с подставленными
   `pixel_code`/`YM_COUNTER_ID`/`FUNNELS_WEBHOOK_*`. Скрипт ставится на лендинг; при
   клике он шлёт данные визита в `FUNNELS_WEBHOOK_URL`, откуда они попадают в
   `visits_data`. Этот поток вне automarks.

3. **CAPI: склад → TikTok.** Отдельные воркфлоу n8n читают склад (JOIN воронки ⋈
   кабинета ⋈ визита по `account_no`/`landing_endpoint`) и шлют конверсии в TikTok
   Events API. Тоже вне automarks.

### Как активировать воронку

Перевод в статус `active` разрешён guard'ом (`marks/views_tiktok.py`) только при
**всех трёх** условиях:

1. отмечена галочка **«Экспорт»** (`salebot_export_ready` = true) — в Salebot
   достроен экспорт событий;
2. задан `account_no`;
3. такой кабинет заведён в разделе «Кабинеты».

Иначе — сообщение об ошибке, статус не меняется. Это защита от «воронка активна, а
события/конверсии молча не идут».

### Полный сценарий запуска

1. **Кабинеты** (`/tiktok/accounts/`, под токеном): завести кабинет(ы) —
   `account_no`, `advertiser_id`, `access_token`. Уходит в склад `tiktok_accounts`.
2. **Заявка** (`/tiktok/apply/`, под логином): маркетолог создаёт черновик воронки.
   `landing_endpoint` нормализуется, `bot_name` парсится, `status=pending`.
3. **Дев-панель** (`/tiktok/panel/`, под токеном): разработчик дозаполняет
   `pixel_code`, `page_type`, `account_no`, UTM; жмёт «Сохранить» (уходит в склад).
4. **Скрипт** (кнопка в строке): скопировать сгенерённый JS и поставить на лендинг.
5. Отметить **«Экспорт»** после достройки в Salebot и перевести воронку в **Активна**.
6. **UTM** (кнопка в строке): скопировать рекламную ссылку для запуска трафика.

### Ключевые файлы

- `marks/models.py` — `TikTokAccount`, `TikTokFunnelRequest`
- `marks/migrations/0032_tiktok_funnels.py`, `0033_salebot_export_ready.py`
- `marks/views_tiktok.py` — вьюхи, токен-гейт, guard активации
- `marks/forms.py` — `TikTokFunnelIntakeForm`, `TikTokAccountForm`
- `marks/services/tiktok_sync.py` — dual-write в склад через n8n
- `marks/services/landing_templates.py` — генерация JS-скрипта + UTM-ссылки
- `marks/services/telegram.py::notify_new_tiktok_funnel` — уведомление о заявке
- `marks/templates/marks/tiktok_*.html` — шаблоны раздела
