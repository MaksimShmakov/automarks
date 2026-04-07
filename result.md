# API: Multimodal Answers Links — Инструкция для фронтенда

## Общие сведения

| Параметр     | Значение                                                |
|--------------|---------------------------------------------------------|
| Base URL     | `http://37.233.85.146:8025/api`                         |
| Эндпоинт     | `POST /api/v1/school/multimodal_answers_links`          |
| Авторизация  | Заголовок `Authorization`                               |
| Тип запроса  | `application/json`                                      |

---

## Авторизация

Все запросы требуют заголовок `Authorization` со значением API-ключа —
**строка без префикса `Bearer`**.

```http
Authorization: <PLATFORM_API_KEY>
Content-Type: application/json
```

При неверном или отсутствующем ключе:

```json
HTTP 401
{ "detail": "API-key Error" }
```

---

## POST `/api/v1/school/multimodal_answers_links`

Сервер скачивает файлы по переданным URL, классифицирует их
на документы и аудио, распознаёт содержимое и передаёт в модель
вместе с текстовым сообщением.

### Тело запроса (JSON)

| Поле           | Тип        | Обязательно | Описание                                             |
|----------------|------------|-------------|------------------------------------------------------|
| `user_id`      | `string`   | ✅           | Уникальный идентификатор пользователя                |
| `vector_keys`  | `string[]` | ✅           | Список ключей предметных баз, например `["math_11"]` |
| `kind`         | `string`   | ✅           | Строго `"dialog_yarik_links"`                        |
| `user_message` | `string`   | ❌           | Текстовый вопрос (опционально)                       |
| `links`        | `string[]` | ❌           | Список URL-ссылок на файлы (картинки, PDF, аудио)    |

> **Важно:** хотя бы одно из полей `links` или `user_message` должно
> быть заполнено. При отсутствии обоих — ошибка 400.

### Поддерживаемые типы файлов в `links`

| Тип               | Расширения                                                       |
|-------------------|------------------------------------------------------------------|
| Изображения / PDF | `.jpg`, `.jpeg`, `.png`, `.pdf`                                  |
| Аудио             | `.ogg`, `.mp3`, `.wav`, `.m4a`, `.aac`, `.flac`, `.webm`, `.opus`|

> Тип определяется по расширению в URL. Если расширение не распознано —
> ошибка 400.

---

## Примеры запросов

### Только текст

```json
{
  "user_id": "user_42",
  "vector_keys": ["math_11"],
  "kind": "dialog_yarik_links",
  "user_message": "Объясни, что такое производная"
}
```

### Текст + ссылки на файлы

```json
{
  "user_id": "user_42",
  "vector_keys": ["math_11"],
  "kind": "dialog_yarik_links",
  "user_message": "Реши задачу из картинки, инструкция в аудио",
  "links": [
    "http://37.233.85.146/shared/math_task.jpg",
    "http://37.233.85.146/shared/math_task.ogg"
  ]
}
```

### Только ссылки (без текста)

```json
{
  "user_id": "user_42",
  "vector_keys": ["physics_11"],
  "kind": "dialog_yarik_links",
  "links": [
    "http://37.233.85.146/shared/task_page1.jpg",
    "http://37.233.85.146/shared/task_page2.jpg"
  ]
}
```

---

### cURL

```bash
curl -X POST "http://37.233.85.146:8025/api/v1/school/multimodal_answers_links" \
  -H "Authorization: YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "user_42",
    "vector_keys": ["math_11"],
    "kind": "dialog_yarik_links",
    "user_message": "Задача",
    "links": [
      "http://37.233.85.146/shared/math_task.jpg",
      "http://37.233.85.146/shared/math_task.ogg"
    ]
  }'
```

### JavaScript (fetch)

```javascript
const API_BASE = "http://37.233.85.146:8025/api";

async function sendLinksRequest({ apiKey, userId, vectorKeys, message, links }) {
  const payload = {
    user_id: userId,
    vector_keys: vectorKeys,
    kind: "dialog_yarik_links",
    links: links || [],
  };
  if (message) payload.user_message = message;

  const response = await fetch(
    `${API_BASE}/v1/school/multimodal_answers_links`,
    {
      method: "POST",
      headers: {
        "Authorization": apiKey,
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    }
  );

  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error(err.detail || `HTTP ${response.status}`);
  }

  const data = await response.json();
  return data.answer; // строка с LaTeX-формулами
}
```

---

## Формат ответа

### Успешный ответ `200 OK`

```json
{
  "answer": "Привет! Разберём задачу из твоего файла 😊\n\n..."
}
```

| Поле     | Тип      | Описание                                               |
|----------|----------|--------------------------------------------------------|
| `answer` | `string` | Текстовый ответ модели с LaTeX-формулами внутри текста |

Ответ — **plain string**. Математические формулы передаются в формате
**LaTeX** внутри текста:

| Вид      | Разделитель | Пример                                      |
|----------|-------------|---------------------------------------------|
| Инлайн   | `\( ... \)` | `\( x^2 + y^2 = r^2 \)`                    |
| Блочная  | `\[ ... \]` | `\[ \int_0^1 x^2 \, dx = \frac{1}{3} \]`  |

> Для рендера формул используй **KaTeX** или **MathJax**.

---

## Порядок обработки на сервере

```
links[]  ──► скачать файлы (таймаут 30 сек/файл)
             │
             ├── .jpg/.jpeg/.png/.pdf ──► распознавание текста/содержимого
             └── .ogg/.mp3/.wav/...  ──► транскрибация аудио в текст
                          │
             user_message ──► объединяется с результатами
                          │
                    RAG + история ──► модель ──► {"answer": "..."}
```

---

## Память диалога (контекст)

Сервер **автоматически сохраняет историю** переписки для каждого `user_id`.
Скользящее окно — последние **10 сообщений** (human/ai).

Смена `vector_keys` в следующем запросе переключает предметную базу
«на лету» — история при этом **сохраняется**.

### Сброс контекста

```
POST /api/v1/school/reset
```

```json
{
  "user_id": "user_42",
  "kind": "dialog_yarik_links"
}
```

Заголовки:

```http
Authorization: <PLATFORM_API_KEY>
Content-Type: application/json
```

Ответ:

```json
{ "response": true }
```

---

## Параметр `vector_keys`

Формат ключа: `<предмет>_<класс>`, где класс — от `05` до `11`.

| Ключ-префикс  | Предмет              |
|---------------|----------------------|
| `math`        | Математика (база)    |
| `mathprof`    | Математика (профиль) |
| `physics`     | Физика               |
| `chemistry`   | Химия                |
| `society`     | Обществознание       |
| `biology`     | Биология             |
| `history`     | История              |
| `russian`     | Русский язык         |
| `literature`  | Литература           |
| `english`     | Английский язык      |
| `informatics` | Информатика          |
| `geography`   | География            |

---

## Коды ошибок

| HTTP-код | Описание                                                                 |
|----------|--------------------------------------------------------------------------|
| `200`    | Успешный ответ                                                           |
| `400`    | Неверный `kind`, пустые `vector_keys`, нет контента, недоступная ссылка |
| `401`    | Неверный или отсутствующий API-ключ                                      |
| `500`    | Внутренняя ошибка сервера                                                |

**Примеры ошибок 400:**

```json
{ "detail": "Unsupported dialog kind for /v1/school/multimodal_answers_links: dialog" }
```
```json
{ "detail": "No input provided: send at least one of (links, user_message)." }
```
```json
{ "detail": "vector_keys must be non-empty" }
```
```json
{ "detail": "Ссылка недействительна (HTTP 404): http://example.com/file.jpg" }
```
```json
{ "detail": "Ссылка недействительна: http://example.com/file.jpg" }
```
```json
{ "detail": "Не удалось определить тип файла по расширению: http://example.com/file.zip" }
```
