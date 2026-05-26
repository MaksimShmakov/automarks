from django import forms

from .models import Bot, MailingExperiment, MailingVariant


MAX_VARIANTS_PER_EXPERIMENT = 2


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


class MailingVariantForm(forms.ModelForm):
    class Meta:
        model = MailingVariant
        fields = ["label", "message_text", "offer_text", "send_time"]
        labels = {
            "label": "Метка варианта",
            "message_text": "Текст сообщения",
            "offer_text": "Оффер (опционально)",
            "send_time": "Время отправки (опционально)",
        }
        widgets = {
            "label": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "A", "maxlength": "20"},
            ),
            "message_text": forms.Textarea(attrs={"class": "form-control", "rows": 4}),
            "offer_text": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
            "send_time": forms.DateTimeInput(
                attrs={"class": "form-control", "type": "datetime-local"},
                format="%Y-%m-%dT%H:%M",
            ),
        }

    def __init__(self, *args, experiment=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.experiment = experiment
        self.fields["label"].required = True
        self.fields["message_text"].required = False
        self.fields["offer_text"].required = False
        self.fields["send_time"].required = False
        self.fields["send_time"].input_formats = ["%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M:%S"]

    def clean_label(self):
        label = (self.cleaned_data.get("label") or "").strip()
        if not label:
            raise forms.ValidationError("Укажите метку варианта (например, A).")
        if self.experiment is None:
            return label
        qs = MailingVariant.objects.filter(experiment=self.experiment, label=label)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError(
                f"Вариант с меткой '{label}' уже есть в этом эксперименте.",
            )
        return label

    def clean(self):
        cleaned = super().clean()
        if self.experiment is not None and not self.instance.pk:
            existing = MailingVariant.objects.filter(experiment=self.experiment).count()
            if existing >= MAX_VARIANTS_PER_EXPERIMENT:
                raise forms.ValidationError(
                    f"У эксперимента уже {MAX_VARIANTS_PER_EXPERIMENT} варианта. "
                    "Удалите один из них, чтобы добавить новый.",
                )
        return cleaned

    def save(self, commit=True):
        obj = super().save(commit=False)
        if self.experiment is not None:
            obj.experiment = self.experiment
        if not obj.weight:
            obj.weight = 1
        if commit:
            obj.save()
        return obj
