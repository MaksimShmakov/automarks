from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User

from .models import Bot, Branch, Tag
from django import forms
from .models import Product, PlanMonthly, BranchPlanMonthly, Funnel, TrafficReport, PatchNote


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
    product = forms.ModelChoiceField(queryset=Product.objects.all(), label="Продукт")
    name = forms.CharField(max_length=255, label="Название")
    description = forms.CharField(required=False, widget=forms.Textarea, label="Описание")
    is_active = forms.BooleanField(required=False, initial=True, label="Активна")

class TrafficReportForm(forms.ModelForm):
    class Meta:
        model = TrafficReport
        fields = ["product", "month", "platform", "vendor", "spend", "impressions", "clicks", "leads_warm", "leads_cold", "notes"]

class PatchNoteForm(forms.ModelForm):
    class Meta:
        model = PatchNote
        fields = ["branch", "title", "change_type", "change_description"]


class CustomUserCreationForm(UserCreationForm):
    class Meta:
        model = User
        fields = ("username", "password1", "password2")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.update({'class': 'form-control'})

class BotForm(forms.ModelForm):
    class Meta:
        model = Bot
        fields = ["name", "product"]


class BotStatusForm(forms.Form):
    inactive = forms.BooleanField(required=False, label="Неактуальный бот")

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
        fields = ["name", "code"]   # название и код ветки

class TagForm(forms.ModelForm):
    class Meta:
        model = Tag
        fields = ["utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content"]


class TagImportForm(forms.Form):
    EXPECTED_COLUMNS = ["utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content"]
    file = forms.FileField(
        label="CSV �?�?�?�?",
        help_text="�?�����?��?��? CSV �?�?�?�? �?" + ", ".join(EXPECTED_COLUMNS),
    )

    def clean_file(self):
        uploaded = self.cleaned_data["file"]
        if not uploaded.name.lower().endswith(".csv"):
            raise forms.ValidationError("?�?�?�?�? �� ����? CSV.")
        return uploaded
