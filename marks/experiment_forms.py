from django import forms

from .models import Experiment


class ExperimentForm(forms.ModelForm):
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
            "start_date",
            "end_date",
            "dashboard_url",
            "result_variant_a",
            "result_variant_b",
            "comment",
        ]
        labels = {
            "title": "Название эксперимента",
            "wants_ab_test": "Хочу А/Б тест",
            "ab_test_custom_option": "Свой вариант",
            "metric_impact": "На какую метрику влияем",
            "expected_change": "Какое изменение ожидаем",
            "hypothesis": "Гипотеза",
            "traffic_volume": "Объем трафика",
            "traffic_volume_other": "Другое (объем трафика)",
            "test_duration": "Длительность теста",
            "duration_users": "До набора X пользователей",
            "duration_end_date": "Плановая дата окончания",
            "start_date": "Дата старта теста",
            "end_date": "Дата окончания теста",
            "dashboard_url": "Ссылка на дашборд",
            "result_variant_a": "Данные по варианту A",
            "result_variant_b": "Данные по варианту B",
            "comment": "Комментарий",
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
            "start_date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "end_date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "dashboard_url": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "https://... или оставьте пустым для общего dashboard",
                }
            ),
            "result_variant_a": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "result_variant_b": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "comment": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
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
            cleaned["start_date"] = None
            cleaned["end_date"] = None
            cleaned["dashboard_url"] = ""
            cleaned["result_variant_a"] = ""
            cleaned["result_variant_b"] = ""
            return cleaned

        if not ab_options:
            self.add_error("ab_test_options", "Выберите минимум один вариант для А/Б теста.")
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
            self.add_error("duration_end_date", "Укажите плановую дату окончания.")

        start_date = cleaned.get("start_date")
        end_date = cleaned.get("end_date")
        if start_date and end_date and end_date < start_date:
            self.add_error("end_date", "Дата окончания не может быть раньше даты старта.")

        return cleaned
