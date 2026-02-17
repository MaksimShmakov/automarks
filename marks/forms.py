from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User

from .models import (
    Bot,
    Branch,
    BranchPlanMonthly,
    Funnel,
    PatchNote,
    PlanMonthly,
    Product,
    Tag,
    TaskRequest,
    TrafficReport,
)


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
    class Meta:
        model = Branch
        fields = ["name", "code"]


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
    class Meta:
        model = TaskRequest
        fields = []

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        def branch_label(obj):
            return f"{obj.bot.name} / {obj.name} ({obj.code})"
        for name, field in self.fields.items():
            if name == "branches":
                field.queryset = Branch.objects.select_related("bot").order_by("bot__name", "name")
                field.label_from_instance = branch_label
                field.widget = forms.CheckboxSelectMultiple(attrs={"class": "form-check-input"})
                if field.queryset.exists():
                    field.help_text = "Список веток: Бот / Ветка (код). Можно выбрать несколько."
                else:
                    field.help_text = "Нет доступных веток. Сначала добавьте их в разделе 'Боты'."
                continue
            if name == "deadline":
                field.input_formats = ["%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S"]
                field.widget = forms.DateTimeInput(
                    format="%Y-%m-%dT%H:%M",
                    attrs={"type": "datetime-local", "class": "form-control"},
                )
                continue
            if name == "comment":
                field.widget = forms.Textarea(attrs={"class": "form-control", "rows": 3})
                continue
            if name == "build_token":
                field.widget = forms.PasswordInput(render_value=True, attrs={"class": "form-control"})
                continue
            field.widget.attrs["class"] = "form-control"

    def _set_type(self, obj, task_type):
        obj.task_type = task_type
        return obj


class PatchTaskRequestForm(BaseTaskRequestForm):
    class Meta:
        model = TaskRequest
        fields = ["branches", "cjm_url", "comment", "deadline"]
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
        fields = ["branches", "tz_url", "comment", "deadline"]
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
    class Meta:
        model = TaskRequest
        fields = ["build_name", "build_token", "cjm_url", "comment", "deadline"]
        labels = {
            "build_name": "Название бота и веток",
            "build_token": "Токен",
            "cjm_url": "CJM (ссылка)",
            "comment": "Комментарий",
            "deadline": "Дедлайн",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["build_name"].required = True
        self.fields["build_token"].required = True
        self.fields["cjm_url"].required = True

    def save(self, commit=True):
        obj = super().save(commit=False)
        self._set_type(obj, TaskRequest.Type.BUILD)
        if commit:
            obj.save()
        return obj


class TaskStatusForm(forms.ModelForm):
    class Meta:
        model = TaskRequest
        fields = ["status"]
        labels = {"status": "Статус"}
        widgets = {"status": forms.Select(attrs={"class": "form-select form-select-sm"})}
