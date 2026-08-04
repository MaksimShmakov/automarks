from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from pathlib import Path
from urllib.parse import urlparse
import re

from .models import (
    Bot,
    Branch,
    BranchPlanMonthly,
    Experiment,
    Funnel,
    PatchNote,
    PlanMonthly,
    Product,
    Tag,
    TaskRequest,
    TrafficReport,
    UtmDictionaryEntry,
)
from .task_time import TASK_INPUT_FORMATS, parse_task_input_datetime


class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = ["name", "is_active"]


class PlanMonthlyForm(forms.ModelForm):
    class Meta:
        model = PlanMonthly
        fields = ["product", "month", "budget", "revenue_target", "warm_leads_target", "cold_leads_target", "notes"]


class BranchPlanMonthlyForm(forms.ModelForm):
    class Meta:
        model = BranchPlanMonthly
        fields = ["branch", "month", "warm_leads", "cold_leads", "expected_revenue", "comment"]


class FunnelForm(forms.ModelForm):
    class Meta:
        model = Funnel
        fields = ["product", "name", "description", "is_active"]


class FunnelMasterForm(forms.Form):
    TYPE_CHOICES = (
        ("funnel", "Воронка"),
        ("bot", "Бот"),
    )
    type = forms.ChoiceField(choices=TYPE_CHOICES, initial="funnel", label="Тип")
    product = forms.ModelChoiceField(queryset=Product.objects.all(), label="Продукт", required=False)
    name = forms.CharField(max_length=255, label="Название")
    description = forms.CharField(required=False, widget=forms.Textarea, label="Описание")
    is_active = forms.BooleanField(required=False, initial=True, label="Активна")

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("type") == "funnel" and not cleaned.get("product"):
            self.add_error("product", "Выберите продукт для воронки.")
        return cleaned


class TrafficReportForm(forms.ModelForm):
    class Meta:
        model = TrafficReport
        fields = ["product", "month", "platform", "vendor", "spend", "impressions", "clicks", "leads_warm", "leads_cold", "notes"]


class PatchNoteForm(forms.Form):
    text = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 4}),
        label="Текст",
    )
    created_at = forms.DateField(
        widget=forms.DateInput(attrs={"type": "date"}),
        label="Дата",
    )
    branches = forms.ModelMultipleChoiceField(
        queryset=Branch.objects.none(),
        widget=forms.CheckboxSelectMultiple(attrs={"class": "form-check-input"}),
        label="Ветки",
    )

    def __init__(self, *args, branches=None, **kwargs):
        super().__init__(*args, **kwargs)
        if branches is None:
            branches = Branch.objects.all()
        self.fields["branches"].queryset = branches


class CustomUserCreationForm(UserCreationForm):
    class Meta:
        model = User
        fields = ("username", "password1", "password2")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.update({"class": "form-control"})


class BotForm(forms.ModelForm):
    class Meta:
        model = Bot
        fields = ["name"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["name"].label = "Username бота"
        self.fields["name"].widget.attrs["placeholder"] = "@new_bot"

    def clean_name(self):
        value = " ".join((self.cleaned_data.get("name") or "").strip().split())
        value = value.lstrip("@")
        if not value:
            raise forms.ValidationError("Укажите username бота.")
        if re.fullmatch(r"[A-Za-z0-9_]{5,32}", value) is None:
            raise forms.ValidationError("Username Telegram должен содержать 5-32 символа: буквы, цифры и _.")
        return value

    def save(self, commit=True):
        obj = super().save(commit=False)
        obj.platform = Bot.Platform.TELEGRAM
        obj.display_name = ""
        if commit:
            obj.save()
        return obj


class VKBotForm(forms.ModelForm):
    class Meta:
        model = Bot
        fields = ["name", "display_name"]
        labels = {
            "name": "ID группы",
            "display_name": "Название",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["name"].widget.attrs["placeholder"] = "203482421"
        self.fields["display_name"].widget.attrs["placeholder"] = "VK бот курса"

    def clean_name(self):
        value = "".join((self.cleaned_data.get("name") or "").split())
        if not value:
            raise forms.ValidationError("Укажите ID группы VK.")
        if re.fullmatch(r"\d{3,32}", value) is None:
            raise forms.ValidationError("ID группы VK должен состоять только из цифр.")
        return value

    def clean_display_name(self):
        value = " ".join((self.cleaned_data.get("display_name") or "").strip().split())
        if not value:
            raise forms.ValidationError("Укажите название для страницы ботов.")
        return value

    def save(self, commit=True):
        obj = super().save(commit=False)
        obj.platform = Bot.Platform.VK
        if commit:
            obj.save()
        return obj


class BotDetailsForm(forms.ModelForm):
    class Meta:
        model = Bot
        fields = ["description", "salebot_url"]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3}),
            "salebot_url": forms.TextInput(attrs={"placeholder": "https://..."}),
        }


class BotStatusForm(forms.Form):
    inactive = forms.BooleanField(required=False, label="Бот неактивен")

    def __init__(self, *args, bot=None, **kwargs):
        self.bot = bot
        if self.bot is None:
            raise ValueError("Bot instance is required for BotStatusForm")
        super().__init__(*args, **kwargs)
        if not self.is_bound:
            self.fields["inactive"].initial = not self.bot.is_active

    def save(self):
        if not self.is_valid():
            raise ValueError("Cannot save inactive state for invalid form")
        self.bot.is_active = not self.cleaned_data["inactive"]
        self.bot.save(update_fields=["is_active"])
        return self.bot


class BranchForm(forms.ModelForm):
    def __init__(self, *args, bot=None, **kwargs):
        self.bot = bot
        super().__init__(*args, **kwargs)
        self.fields["name"].widget.attrs.setdefault("placeholder", "Например, Welcome")
        self.fields["code"].required = False
        self.fields["code"].widget.attrs.setdefault("placeholder", "Например, ell01")
        suggested_code = Branch.suggest_next_code(bot)
        if suggested_code:
            self.fields["code"].help_text = f"Следующий код подставлен автоматически: {suggested_code}"
            if not self.is_bound and not self.initial.get("code") and not getattr(self.instance, "pk", None):
                self.initial["code"] = suggested_code

    class Meta:
        model = Branch
        fields = ["name", "code"]

    def clean_code(self):
        value = " ".join((self.cleaned_data.get("code") or "").strip().split())
        if value:
            return value

        suggested_code = Branch.suggest_next_code(self.bot)
        if suggested_code and not getattr(self.instance, "pk", None):
            return suggested_code
        raise forms.ValidationError("Укажите код ветки.")


class TagForm(forms.ModelForm):
    class Meta:
        model = Tag
        fields = ["utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "budget"]


class TagImportForm(forms.Form):
    EXPECTED_COLUMNS = ["utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content"]
    file = forms.FileField(
        label="CSV файл",
        help_text="Загрузите CSV со столбцами: " + ", ".join(EXPECTED_COLUMNS),
    )

    def clean_file(self):
        uploaded = self.cleaned_data["file"]
        if not uploaded.name.lower().endswith(".csv"):
            raise forms.ValidationError("Нужен файл CSV.")
        return uploaded


class BaseTaskRequestForm(forms.ModelForm):
    MAX_PHOTO_SIZE = 10 * 1024 * 1024
    ALLOWED_PHOTO_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}

    notify_me = forms.BooleanField(
        required=False,
        label="Хочу получить уведомление",
    )
    tg_username = forms.CharField(
        required=False,
        max_length=64,
        label="Username в Telegram",
    )

    class Meta:
        model = TaskRequest
        fields = []

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        def branch_label(obj):
            return f"{obj.bot.title} / {obj.name} ({obj.code})"
        for name, field in self.fields.items():
            if name == "branches":
                field.queryset = Branch.objects.select_related("bot").order_by(
                    "bot__platform",
                    "bot__display_name",
                    "bot__name",
                    "name",
                )
                field.label_from_instance = branch_label
                field.widget = forms.CheckboxSelectMultiple(attrs={"class": "form-check-input"})
                if field.queryset.exists():
                    field.help_text = "Список веток: Бот / Ветка (код). Можно выбрать несколько."
                else:
                    field.help_text = "Нет доступных веток. Сначала добавьте их в разделе 'Боты'."
                continue
            if name == "deadline":
                field.input_formats = list(TASK_INPUT_FORMATS)
                field.widget = forms.DateTimeInput(
                    format="%Y-%m-%dT%H:%M",
                    attrs={"type": "datetime-local", "class": "form-control", "autocomplete": "off"},
                )
                continue
            if name == "photo":
                field.required = False
                field.help_text = "Можно выбрать файл или вставить изображение через Ctrl+V."
                field.widget = forms.ClearableFileInput(
                    attrs={
                        "class": "form-control",
                        "accept": "image/*",
                    }
                )
                continue
            if name == "comment":
                field.widget = forms.Textarea(attrs={"class": "form-control", "rows": 3, "autocomplete": "off"})
                continue
            if name == "build_token":
                field.widget = forms.PasswordInput(
                    attrs={
                        "class": "form-control",
                        "autocomplete": "new-password",
                        "data-lpignore": "true",
                    }
                )
                continue
            if name == "notify_me":
                field.widget = forms.CheckboxInput(attrs={"class": "form-check-input"})
                continue
            if name == "tg_username":
                field.widget = forms.TextInput(
                    attrs={
                        "class": "form-control",
                        "placeholder": "@username или chat_id",
                        "autocomplete": "off",
                    }
                )
                continue
            field.widget.attrs["class"] = "form-control"
            field.widget.attrs["autocomplete"] = "off"

    def _set_type(self, obj, task_type):
        obj.task_type = task_type
        return obj

    def clean_deadline(self):
        raw_value = self.data.get(self.add_prefix("deadline")) or ""
        if not raw_value.strip():
            return self.cleaned_data.get("deadline")
        try:
            return parse_task_input_datetime(raw_value)
        except ValueError:
            raise forms.ValidationError("Укажите дату и время в корректном формате.")

    def clean_photo(self):
        uploaded = self.cleaned_data.get("photo")
        if not uploaded:
            return uploaded

        extension = Path(uploaded.name or "").suffix.lower()
        if extension not in self.ALLOWED_PHOTO_EXTENSIONS:
            raise forms.ValidationError("Поддерживаются только изображения: PNG, JPG, WEBP, GIF, BMP.")

        content_type = (getattr(uploaded, "content_type", "") or "").lower()
        if content_type and not content_type.startswith("image/"):
            raise forms.ValidationError("Загрузите изображение.")

        if uploaded.size > self.MAX_PHOTO_SIZE:
            raise forms.ValidationError("Фото должно быть не больше 10 МБ.")

        return uploaded

    def clean(self):
        cleaned = super().clean()
        notify_me = bool(cleaned.get("notify_me"))
        tg_username = (cleaned.get("tg_username") or "").strip()
        if tg_username.startswith("@"):
            tg_username = tg_username[1:]

        if notify_me and not tg_username:
            self.add_error("tg_username", "Укажите username в Telegram или chat_id.")
            return cleaned

        if tg_username:
            is_username = re.fullmatch(r"[A-Za-z0-9_]{5,32}", tg_username) is not None
            is_chat_id = re.fullmatch(r"-?\d{5,20}", tg_username) is not None
            if not is_username and not is_chat_id:
                self.add_error("tg_username", "Неверный формат. Пример: @my_user или 123456789.")

        cleaned["tg_username"] = tg_username if notify_me else ""
        return cleaned


class PatchTaskRequestForm(BaseTaskRequestForm):
    class Meta:
        model = TaskRequest
        fields = ["branches", "cjm_url", "comment", "photo", "deadline"]
        labels = {
            "branches": "Ветки",
            "cjm_url": "CJM (ссылка)",
            "comment": "Комментарий",
            "deadline": "Дедлайн",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["branches"].required = True
        self.fields["cjm_url"].required = True

    def save(self, commit=True):
        obj = super().save(commit=False)
        self._set_type(obj, TaskRequest.Type.PATCH)
        if commit:
            obj.save()
            self.save_m2m()
        return obj


class MailingTaskRequestForm(BaseTaskRequestForm):
    class Meta:
        model = TaskRequest
        fields = ["branches", "tz_url", "comment", "photo", "deadline"]
        labels = {
            "branches": "Ветки",
            "tz_url": "ТЗ (ссылка)",
            "comment": "Комментарий",
            "deadline": "Дедлайн",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["branches"].required = True
        self.fields["tz_url"].required = True

    def save(self, commit=True):
        obj = super().save(commit=False)
        self._set_type(obj, TaskRequest.Type.MAILING)
        if commit:
            obj.save()
            self.save_m2m()
        return obj


class BuildTaskRequestForm(BaseTaskRequestForm):
    bot_name = forms.CharField(
        max_length=255,
        label="Имя бота",
    )
    branch_name = forms.CharField(
        required=False,
        max_length=255,
        label="Ветка (необязательно)",
    )

    class Meta:
        model = TaskRequest
        fields = ["build_token", "cjm_url", "comment", "photo", "deadline"]
        labels = {
            "build_token": "Токен",
            "cjm_url": "CJM (ссылка)",
            "comment": "Комментарий",
            "deadline": "Дедлайн",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["bot_name"].widget.attrs["placeholder"] = "@new_bot"
        self.fields["branch_name"].widget.attrs["placeholder"] = "main"
        self.fields["build_token"].required = True
        self.fields["cjm_url"].required = True

    def clean(self):
        cleaned = super().clean()
        bot_name = " ".join((cleaned.get("bot_name") or "").replace(",", " ").strip().split())
        branch_name = " ".join((cleaned.get("branch_name") or "").replace(",", " ").strip().split())

        if not bot_name:
            self.add_error("bot_name", "Укажите имя бота.")

        cleaned["bot_name"] = bot_name
        cleaned["branch_name"] = branch_name
        return cleaned

    def save(self, commit=True):
        obj = super().save(commit=False)
        self._set_type(obj, TaskRequest.Type.BUILD)
        bot_name = self.cleaned_data.get("bot_name") or ""
        branch_name = self.cleaned_data.get("branch_name") or ""
        obj.build_name = f"{bot_name} / {branch_name}" if branch_name else bot_name
        if commit:
            obj.save()
        return obj


class TaskStatusForm(forms.ModelForm):
    class Meta:
        model = TaskRequest
        fields = ["status"]
        labels = {"status": "Статус"}
        widgets = {"status": forms.Select(attrs={"class": "form-select form-select-sm"})}


class LegacyExperimentForm(forms.ModelForm):
    AB_TEST_OPTIONS = [
        ("start", "Стартовый"),
        ("segmentation", "Сегментация"),
        ("number", "Номер"),
        ("subscription", "Подписка"),
        ("push", "Дожимы"),
        ("sale", "Продажа"),
        ("custom", "Свой вариант"),
    ]

    ab_test_options = forms.MultipleChoiceField(
        choices=AB_TEST_OPTIONS,
        required=False,
        widget=forms.CheckboxSelectMultiple(),
        label="Варианты",
    )

    class Meta:
        model = Experiment
        fields = [
            "title",
            "wants_ab_test",
            "ab_test_options",
            "ab_test_custom_option",
            "metric_impact",
            "expected_change",
            "hypothesis",
            "traffic_volume",
            "traffic_volume_other",
            "test_duration",
            "duration_users",
            "duration_end_date",
            "comment",
            "status",
        ]
        labels = {
            "title": "Название эксперимента",
            "wants_ab_test": "Хочу АБ тест",
            "ab_test_custom_option": "Свой вариант",
            "metric_impact": "На какую метрику влияем",
            "expected_change": "Какое изменение ожидаем",
            "hypothesis": "Гипотеза",
            "traffic_volume": "Объем трафика",
            "traffic_volume_other": "Другое (объем трафика)",
            "test_duration": "Длительность теста",
            "duration_users": "До набора X пользователей",
            "duration_end_date": "Конкретная дата окончания",
            "comment": "Комментарий",
            "status": "Статус",
        }
        widgets = {
            "title": forms.TextInput(attrs={"class": "form-control"}),
            "ab_test_custom_option": forms.TextInput(attrs={"class": "form-control"}),
            "metric_impact": forms.TextInput(attrs={"class": "form-control"}),
            "expected_change": forms.TextInput(attrs={"class": "form-control"}),
            "hypothesis": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "traffic_volume": forms.Select(attrs={"class": "form-select"}),
            "traffic_volume_other": forms.TextInput(attrs={"class": "form-control"}),
            "test_duration": forms.Select(attrs={"class": "form-select"}),
            "duration_users": forms.NumberInput(attrs={"class": "form-control", "min": "1"}),
            "duration_end_date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "comment": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
            "status": forms.Select(attrs={"class": "form-select"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["wants_ab_test"].required = False

    def clean(self):
        cleaned = super().clean()
        wants_ab_test = bool(cleaned.get("wants_ab_test"))
        ab_options = cleaned.get("ab_test_options") or []

        if not wants_ab_test:
            cleaned["ab_test_options"] = []
            cleaned["ab_test_custom_option"] = ""
            cleaned["metric_impact"] = ""
            cleaned["expected_change"] = ""
            cleaned["hypothesis"] = ""
            cleaned["traffic_volume"] = ""
            cleaned["traffic_volume_other"] = ""
            cleaned["test_duration"] = ""
            cleaned["duration_users"] = None
            cleaned["duration_end_date"] = None
            return cleaned

        if not ab_options:
            self.add_error("ab_test_options", "Выберите минимум один вариант для АБ теста.")
        if "custom" in ab_options and not (cleaned.get("ab_test_custom_option") or "").strip():
            self.add_error("ab_test_custom_option", "Заполните поле 'Свой вариант'.")
        if not (cleaned.get("metric_impact") or "").strip():
            self.add_error("metric_impact", "Заполните поле метрики.")
        if not (cleaned.get("expected_change") or "").strip():
            self.add_error("expected_change", "Заполните ожидаемое изменение.")
        if not (cleaned.get("hypothesis") or "").strip():
            self.add_error("hypothesis", "Заполните гипотезу.")

        traffic_volume = cleaned.get("traffic_volume")
        if not traffic_volume:
            self.add_error("traffic_volume", "Выберите объем трафика.")
        elif traffic_volume == Experiment.TrafficVolume.OTHER and not (cleaned.get("traffic_volume_other") or "").strip():
            self.add_error("traffic_volume_other", "Укажите свой вариант объема трафика.")

        duration = cleaned.get("test_duration")
        if not duration:
            self.add_error("test_duration", "Выберите длительность теста.")
        elif duration == Experiment.TestDuration.UNTIL_USERS and not cleaned.get("duration_users"):
            self.add_error("duration_users", "Укажите количество пользователей.")
        elif duration == Experiment.TestDuration.END_DATE and not cleaned.get("duration_end_date"):
            self.add_error("duration_end_date", "Укажите дату окончания.")

        return cleaned


class MarkForm(forms.Form):
    """Генератор UTM-метки: закрытые поля — из справочника, ручные — по маске."""

    NAME_RE = re.compile(r"^[a-z0-9-]+$")
    CYRILLIC_RE = re.compile(r"[а-яёА-ЯЁ]")

    original_url = forms.CharField(
        label="Ссылка (лендинг / канал / бот / ролик)",
        max_length=2000,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "https://el-ed.ru/oge"}),
    )
    source = forms.ChoiceField(label="source", choices=[])
    source_custom = forms.CharField(
        label="имя для шаблонного source",
        max_length=255,
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "python2026 (для tg-<имя> и т.п.)"}),
    )
    medium = forms.ChoiceField(label="medium", choices=[])
    mark_type = forms.ChoiceField(label="тип", choices=[])
    direction = forms.ChoiceField(label="направление", choices=[])
    funnel = forms.ChoiceField(label="воронка", choices=[])
    funnel_custom = forms.CharField(
        label="конкретный канал/бот в воронке (через дефис)",
        max_length=255,
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "python2026 → tgk-python2026"}),
    )
    name = forms.CharField(
        label="имя кампании",
        max_length=255,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "pyweek2026"}),
    )
    utm_term = forms.CharField(
        label="term (аудитория/ключ + таргетолог)",
        max_length=255,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "retarget-konkurenty-vld"}),
    )
    utm_content = forms.CharField(
        label="content (ID объявления)",
        max_length=255,
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "ad-456"}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Шаблоны source (tg-<имя> и т.п.) теперь доступны: выбираешь шаблон + вписываешь имя.
        self.fields["source"].choices = self._dict_choices("source", include_templates=True)
        self.fields["medium"].choices = self._dict_choices("medium")
        self.fields["mark_type"].choices = self._dict_choices("type")
        self.fields["direction"].choices = self._dict_choices("direction")
        self.fields["funnel"].choices = self._dict_choices("funnel")
        for field_name in ("source", "medium", "mark_type", "direction", "funnel"):
            self.fields[field_name].widget.attrs["class"] = "form-select"

    @staticmethod
    def _dict_choices(field, include_templates=True):
        queryset = UtmDictionaryEntry.objects.filter(field=field, is_active=True)
        if not include_templates:
            queryset = queryset.filter(is_template=False)
        options = []
        for entry in queryset:
            suffix = " (шаблон)" if entry.is_template else (f" — {entry.label}" if entry.label else "")
            options.append((entry.value, f"{entry.value}{suffix}"))
        return [("", "— выбери —")] + options

    @staticmethod
    def resolve_template_source(template, custom):
        """tg-<имя> + 'python2026' → 'tg-python2026'; <partner> + 'vc' → 'vc'."""
        prefix = template.split("<", 1)[0]
        custom = custom.strip()
        if prefix and not custom.startswith(prefix):
            return f"{prefix}{custom}"
        return custom

    def clean_original_url(self):
        value = (self.cleaned_data.get("original_url") or "").strip()
        if " " in value or self.CYRILLIC_RE.search(value):
            raise forms.ValidationError("URL без пробелов и кириллицы.")
        try:
            value.encode("ascii")
        except UnicodeEncodeError:
            raise forms.ValidationError("URL только из ASCII-символов.")
        parsed = urlparse(value)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise forms.ValidationError("Нужен полный http(s) URL, например https://el-ed.ru/oge.")
        return value

    def clean_name(self):
        value = (self.cleaned_data.get("name") or "").strip()
        if not self.NAME_RE.match(value):
            raise forms.ValidationError(
                "Только латиница, цифры и дефис; без пробелов и подчёркивания."
            )
        return value

    def _clean_manual_value(self, key):
        value = (self.cleaned_data.get(key) or "").strip()
        if not value:
            return value  # пустое допустимо (обязательность проверяет сама форма)
        if not self.NAME_RE.match(value):
            raise forms.ValidationError(
                "Только латиница, цифры и дефис; без пробелов и подчёркивания."
            )
        return value

    def clean_utm_term(self):
        return self._clean_manual_value("utm_term")

    def clean_utm_content(self):
        return self._clean_manual_value("utm_content")

    def clean(self):
        cleaned = super().clean()

        # source: шаблон → собрать по маске + флаг «на заявку Грише».
        source = cleaned.get("source")
        if source:
            entry = UtmDictionaryEntry.objects.filter(
                field="source", value=source, is_active=True
            ).first()
            if entry and entry.is_template:
                custom = (cleaned.get("source_custom") or "").strip()
                if not custom:
                    self.add_error("source_custom", "Заполни имя для шаблонного source.")
                else:
                    resolved = self.resolve_template_source(source, custom)
                    if not self.NAME_RE.match(resolved):
                        self.add_error("source_custom", "Только латиница, цифры и дефис.")
                    else:
                        cleaned["resolved_source"] = resolved
                        cleaned["pending_review"] = True
            else:
                cleaned["resolved_source"] = source
                cleaned["pending_review"] = False

        # воронка: конкретный канал/бот через дефис (tgk-python2026, bot-efir).
        funnel = cleaned.get("funnel")
        if funnel:
            funnel_custom = (cleaned.get("funnel_custom") or "").strip()
            if funnel_custom:
                if not self.NAME_RE.match(funnel_custom):
                    self.add_error("funnel_custom", "Только латиница, цифры и дефис.")
                else:
                    cleaned["resolved_funnel"] = f"{funnel}-{funnel_custom}"
            else:
                cleaned["resolved_funnel"] = funnel

        return cleaned


class TagMarkForm(MarkForm):
    """Принудительный генератор UTM для метки бота (Tag): как MarkForm, но без целевого URL.

    URL метки — это deep-link бота (t.me/бот?start=номер), он генерится в Tag.save().
    Поэтому поле original_url убираем; добавляем budget.
    """

    budget = forms.DecimalField(
        label="бюджет",
        required=False,
        min_value=0,
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields.pop("original_url", None)
