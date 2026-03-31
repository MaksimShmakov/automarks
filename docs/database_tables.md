# Таблицы БД

Документ описывает актуальную каноническую схему проекта, которая получается из Django-моделей и миграций приложения `marks` до `0022_experiment_branch`.

Важно:

- Корневой `db.sqlite3` в репозитории отстаёт от текущих моделей и не отражает всю схему.
- Для сверки использована чистая тестовая база, поднятая миграциями через `config.test_settings`.
- Файл [`automarks/models.py`](/c:/Dev/automarks%202.0%20UPD/automarks/models.py) содержит старый SQLAlchemy-модельный код и не участвует в текущей Django-схеме.

## Состав схемы

Основные бизнес-таблицы проекта:

- `marks_product`
- `marks_bot`
- `marks_branch`
- `marks_tag`
- `marks_planmonthly`
- `marks_branchplanmonthly`
- `marks_funnel`
- `marks_trafficreport`
- `marks_patchnote`
- `marks_taskrequest`
- `marks_taskrequest_branches`
- `marks_experiment`
- `marks_userprofile`

Служебные Django-таблицы:

- `auth_user`
- `auth_group`
- `auth_permission`
- `auth_user_groups`
- `auth_user_user_permissions`
- `auth_group_permissions`
- `django_admin_log`
- `django_content_type`
- `django_migrations`
- `django_session`

## Карта связей

- Продукт (`marks_product`) является корнем для ботов, месячных планов, воронок и отчётов по трафику.
- Бот (`marks_bot`) объединяет ветки (`marks_branch`).
- Ветка (`marks_branch`) является базой для тегов, пометок об изменениях, планов по ветке, задач и экспериментов.
- Задача (`marks_taskrequest`) связана с ветками отношением many-to-many через `marks_taskrequest_branches`.
- Пользователь Django (`auth_user`) расширяется бизнес-ролью через `marks_userprofile`.

## Бизнес-таблицы

### `marks_product`

Назначение: справочник продуктов.

Поля:

- `id` `bigint`, PK.
- `name` `varchar(255)`, обязательное, уникальное имя продукта.
- `is_active` `bool`, флаг активности продукта.
- `created_at` `datetime`, дата создания.

Связи:

- 1:N с `marks_bot`.
- 1:N с `marks_planmonthly`.
- 1:N с `marks_funnel`.
- 1:N с `marks_trafficreport`.

Ограничения:

- уникальность `name`.

### `marks_bot`

Назначение: бот конкретного продукта.

Поля:

- `id` `bigint`, PK.
- `product_id` `bigint`, FK на `marks_product.id`, nullable.
- `platform` `varchar(10)`, платформа бота: сейчас используются `tg` и `vk`.
- `name` `varchar(255)`, обязательное, уникальное техническое имя.
- `display_name` `varchar(255)`, отображаемое имя.
- `description` `text`, описание.
- `salebot_url` `varchar(500)`, ссылка на внешнюю систему/сборку.
- `created_at` `datetime`, дата создания.
- `is_active` `bool`, активен ли бот.

Связи:

- N:1 к `marks_product`.
- 1:N с `marks_branch`.

Ограничения:

- уникальность `name`.

Примечания:

- На уровне модели бот умеет собирать конечный URL тега для Telegram и VK.

### `marks_branch`

Назначение: ветка или сценарная линия внутри бота.

Поля:

- `id` `bigint`, PK.
- `bot_id` `bigint`, FK на `marks_bot.id`.
- `name` `varchar(50)`, название ветки.
- `code` `varchar(10)`, короткий код ветки.
- `created_at` `datetime`, дата создания.

Связи:

- N:1 к `marks_bot`.
- 1:N с `marks_tag`.
- 1:N с `marks_branchplanmonthly`.
- 1:N с `marks_patchnote`.
- M:N с `marks_taskrequest` через `marks_taskrequest_branches`.
- 1:N с `marks_experiment`.

Ограничения:

- уникальная пара `(bot_id, code)`.

Примечания:

- После создания ветки сигналом автоматически создаётся первый тег в `marks_tag`.
- Из `code` вычисляется `ref_source`, который используется при генерации VK-ссылок.

### `marks_tag`

Назначение: UTM-тег/автометка внутри ветки.

Поля:

- `id` `bigint`, PK.
- `branch_id` `bigint`, FK на `marks_branch.id`.
- `number` `varchar(20)`, номер тега внутри ветки.
- `utm_source` `varchar(255)`, nullable.
- `utm_medium` `varchar(255)`, nullable.
- `utm_campaign` `varchar(255)`, nullable.
- `utm_term` `varchar(255)`, nullable.
- `utm_content` `varchar(255)`, nullable.
- `budget` `decimal(12,2)`, nullable.
- `url` `varchar(500)`, nullable, итоговая ссылка с меткой.
- `created_at` `datetime`, дата создания.

Связи:

- N:1 к `marks_branch`.

Ограничения:

- уникальная пара `(branch_id, number)`.
- сортировка по `number`.

Примечания:

- Если `number` не задан, модель генерирует его автоматически по префиксу ветки.
- Поле `url` пересчитывается автоматически при сохранении через логику модели.

### `marks_planmonthly`

Назначение: месячный план по продукту.

Поля:

- `id` `bigint`, PK.
- `product_id` `bigint`, FK на `marks_product.id`.
- `month` `date`, первое число месяца.
- `budget` `decimal(12,2)`, бюджет.
- `revenue_target` `decimal(12,2)`, целевая выручка.
- `warm_leads_target` `int`, цель по тёплым лидам.
- `cold_leads_target` `int`, цель по холодным лидам.
- `notes` `text`, комментарии.

Связи:

- N:1 к `marks_product`.

Ограничения:

- уникальная пара `(product_id, month)`.

### `marks_branchplanmonthly`

Назначение: месячный план на уровне конкретной ветки.

Поля:

- `id` `bigint`, PK.
- `branch_id` `bigint`, FK на `marks_branch.id`.
- `month` `date`, месяц плана.
- `warm_leads` `int`, план тёплых лидов.
- `cold_leads` `int`, план холодных лидов.
- `expected_revenue` `decimal(12,2)`, ожидаемая выручка.
- `comment` `varchar(255)`, комментарий.

Связи:

- N:1 к `marks_branch`.

Ограничения:

- уникальная пара `(branch_id, month)`.

### `marks_funnel`

Назначение: справочник воронок продукта.

Поля:

- `id` `bigint`, PK.
- `product_id` `bigint`, FK на `marks_product.id`.
- `name` `varchar(255)`, название воронки.
- `description` `text`, описание.
- `is_active` `bool`, активность.
- `created_at` `datetime`, дата создания.

Связи:

- N:1 к `marks_product`.

Ограничения:

- уникальная пара `(product_id, name)`.

### `marks_trafficreport`

Назначение: отчёт по закупке и эффективности трафика за месяц.

Поля:

- `id` `bigint`, PK.
- `product_id` `bigint`, FK на `marks_product.id`.
- `month` `date`, отчётный месяц.
- `platform` `varchar(20)`, источник платформы: `tg`, `vk`, `tt`, `ig`, `other`.
- `vendor` `varchar(255)`, подрядчик или исполнитель.
- `spend` `decimal(12,2)`, расход.
- `impressions` `int`, показы.
- `clicks` `int`, клики.
- `leads_warm` `int`, тёплые лиды.
- `leads_cold` `int`, холодные лиды.
- `notes` `varchar(255)`, примечание.

Связи:

- N:1 к `marks_product`.

Ограничения:

- отдельных уникальных ограничений нет.

### `marks_patchnote`

Назначение: журнал изменений по ветке.

Поля:

- `id` `bigint`, PK.
- `branch_id` `bigint`, FK на `marks_branch.id`.
- `created_by_id` `int`, FK на `auth_user.id`, nullable.
- `created_at` `datetime`, дата фиксации.
- `title` `varchar(255)`, короткий заголовок.
- `change_description` `text`, описание изменения.
- `change_type` `varchar(50)`, тип изменения, по умолчанию `update`.

Связи:

- N:1 к `marks_branch`.
- N:1 к `auth_user`.

Ограничения:

- отдельных уникальных ограничений нет.

### `marks_taskrequest`

Назначение: заявки на работы по ботам и веткам.

Поля:

- `id` `bigint`, PK.
- `task_type` `varchar(20)`, тип задачи: `patch`, `mailing`, `build`.
- `status` `varchar(20)`, статус: `unread`, `in_progress`, `done`.
- `cjm_url` `varchar(200)`, ссылка на CJM.
- `tz_url` `varchar(200)`, ссылка на ТЗ.
- `build_name` `varchar(255)`, имя сборки или список веток для fallback-логики.
- `build_token` `varchar(255)`, токен/идентификатор сборки.
- `comment` `text`, комментарий.
- `deadline` `datetime`, дедлайн.
- `created_by_id` `int`, FK на `auth_user.id`, nullable.
- `created_at` `datetime`, дата создания.
- `completed_at` `datetime`, nullable, дата завершения.
- `updated_at` `datetime`, дата последнего обновления.

Дополнительные фактические колонки в текущей схеме:

- `tg_username` `varchar(255)`, nullable, legacy-колонка, добавлена миграциями совместимости.
- `feedback_comment` `text`, nullable, legacy-колонка, добавлена миграциями совместимости.

Связи:

- N:1 к `auth_user`.
- M:N с `marks_branch` через `marks_taskrequest_branches`.

Ограничения:

- отдельных уникальных ограничений нет.

Примечания:

- `completed_at` управляется логикой модели: при статусе `done` выставляется автоматически.
- Физическая таблица шире текущей модели из-за миграций совместимости.

### `marks_taskrequest_branches`

Назначение: промежуточная таблица many-to-many между задачами и ветками.

Поля:

- `id` `bigint`, PK.
- `taskrequest_id` `bigint`, FK на `marks_taskrequest.id`.
- `branch_id` `bigint`, FK на `marks_branch.id`.

Связи:

- N:1 к `marks_taskrequest`.
- N:1 к `marks_branch`.

Ограничения:

- уникальная пара `(taskrequest_id, branch_id)`.

Примечания:

- Таблица создаётся Django автоматически из `ManyToManyField`.

### `marks_experiment`

Назначение: карточка эксперимента и A/B-теста.

Поля:

- `id` `bigint`, PK.
- `title` `varchar(255)`, заголовок.
- `branch_id` `bigint`, FK на `marks_branch.id`, nullable.
- `wants_ab_test` `bool`, нужен ли A/B-тест.
- `ab_test_options` `json`, список вариантов.
- `ab_test_custom_option` `varchar(255)`, кастомный вариант.
- `metric_impact` `varchar(255)`, метрика влияния.
- `expected_change` `varchar(255)`, ожидаемое изменение.
- `hypothesis` `text`, гипотеза.
- `traffic_volume` `varchar(20)`, режим деления трафика.
- `traffic_volume_other` `varchar(255)`, кастомное деление трафика.
- `test_duration` `varchar(20)`, тип длительности теста.
- `duration_users` `int`, nullable, порог пользователей.
- `duration_end_date` `date`, nullable, дата окончания по сценарию длительности.
- `start_date` `date`, nullable, фактический старт.
- `end_date` `date`, nullable, фактическое завершение.
- `dashboard_url` `varchar(500)`, ссылка на дашборд.
- `result_variant_a` `text`, результат варианта A.
- `result_variant_b` `text`, результат варианта B.
- `comment` `text`, комментарий.
- `status` `varchar(20)`, статус эксперимента.
- `created_by_id` `int`, FK на `auth_user.id`, nullable.
- `created_at` `datetime`, дата создания.
- `updated_at` `datetime`, дата обновления.

Связи:

- N:1 к `marks_branch`, связь опциональна.
- N:1 к `auth_user`, связь опциональна.

Ограничения:

- отдельных уникальных ограничений нет.

Примечания:

- `ab_test_options` хранится как JSON-массив.
- В модели есть логика проверки активности API-эксперимента по статусу, датам и сплиту трафика.

### `marks_userprofile`

Назначение: бизнес-профиль пользователя Django.

Поля:

- `id` `bigint`, PK.
- `user_id` `int`, FK и одновременно `OneToOne` на `auth_user.id`.
- `role` `varchar(20)`, бизнес-роль пользователя: `admin`, `manager`, `marketer`, `bot_user`.

Связи:

- 1:1 с `auth_user`.

Ограничения:

- уникальность `user_id`.

Примечания:

- Профиль создаётся автоматически сигналом при создании пользователя.

## Служебные Django-таблицы

### `auth_user`

Основная таблица пользователей Django. На неё ссылаются `marks_userprofile`, `marks_patchnote`, `marks_taskrequest`, `marks_experiment` и стандартные таблицы прав.

### `auth_group`

Группы пользователей Django.

### `auth_permission`

Справочник прав доступа по моделям и действиям.

### `auth_user_groups`

Промежуточная many-to-many таблица между `auth_user` и `auth_group`.

### `auth_user_user_permissions`

Промежуточная many-to-many таблица между `auth_user` и `auth_permission` для персональных прав.

### `auth_group_permissions`

Промежуточная many-to-many таблица между `auth_group` и `auth_permission`.

### `django_admin_log`

Журнал действий в Django Admin.

### `django_content_type`

Технический справочник моделей Django, нужен для permissions и generic-механизмов.

### `django_migrations`

Список применённых миграций.

### `django_session`

Сессии пользователей Django.

## Итог

Если смотреть только на прикладную область проекта, ядро схемы образуют `marks_product -> marks_bot -> marks_branch -> marks_tag`, а вокруг этого ядра строятся планы, отчёты, задачи, эксперименты и профиль ролей пользователей.
