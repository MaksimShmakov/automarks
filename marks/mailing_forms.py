from django import forms

from .models import Bot, MailingExperiment


class MailingExperimentForm(forms.ModelForm):
    class Meta:
        model = MailingExperiment
        fields = [
            "title",
            "hypothesis",
            "bot",
            "test_dimension",
            "traffic_split",
            "traffic_split_other",
            "start_date",
            "end_date",
            "comment",
        ]
        labels = {
            "title": "Название эксперимента",
            "hypothesis": "Гипотеза",
            "bot": "Бот",
            "test_dimension": "Что тестируем",
            "traffic_split": "Сплит трафика",
            "traffic_split_other": "Свой сплит",
            "start_date": "Дата старта",
            "end_date": "Дата окончания",
            "comment": "Комментарий",
        }
        widgets = {
            "title": forms.TextInput(attrs={"class": "form-control"}),
            "hypothesis": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "bot": forms.Select(attrs={"class": "form-select"}),
            "test_dimension": forms.Select(attrs={"class": "form-select"}),
            "traffic_split": forms.Select(attrs={"class": "form-select"}),
            "traffic_split_other": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "напр. 80/20"},
            ),
            "start_date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "end_date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "comment": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["bot"].required = False
        self.fields["bot"].queryset = Bot.objects.all().order_by(
            "platform", "display_name", "name",
        )
        self.fields["bot"].label_from_instance = (
            lambda obj: f"{obj.title} ({obj.get_platform_display()})"
        )

    def clean(self):
        cleaned = super().clean()
        traffic_split = cleaned.get("traffic_split") or ""
        traffic_split_other = (cleaned.get("traffic_split_other") or "").strip()

        if traffic_split == MailingExperiment.TrafficSplit.OTHER and not traffic_split_other:
            self.add_error(
                "traffic_split_other",
                "Укажите свой сплит в формате '80/20'.",
            )
        if traffic_split != MailingExperiment.TrafficSplit.OTHER:
            cleaned["traffic_split_other"] = ""

        start_date = cleaned.get("start_date")
        end_date = cleaned.get("end_date")
        if start_date and end_date and end_date < start_date:
            self.add_error("end_date", "Дата окончания не может быть раньше даты старта.")

        return cleaned
