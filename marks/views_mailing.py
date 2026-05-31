import csv as csv_module
import re

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .mailing_forms import (
    MailingExperimentForm,
    MailingVariantForm,
    MailingVariantMetricForm,
)
from .mailing_split import (
    MailingSplitError,
    apply_split_weights,
    assign_pending_recipients,
    import_recipients,
    parse_recipient_ids,
)
from .models import (
    MailingExperiment,
    MailingVariant,
    MailingVariantMetric,
    UserProfile,
)
from .permissions import require_roles


REQUIRED_VARIANTS_FOR_IMPORT = 2
FINAL_MAILING_STATUSES = {
    MailingExperiment.Status.SUCCESS,
    MailingExperiment.Status.FAILED,
}
WORKING_MAILING_STATUSES = (
    MailingExperiment.Status.BACKLOG,
    MailingExperiment.Status.DRAFT,
    MailingExperiment.Status.IN_PROGRESS,
    MailingExperiment.Status.COMPLETED,
)
WORKING_STATUS_CHOICES = [
    (code, label)
    for code, label in MailingExperiment.Status.choices
    if code in {s.value for s in WORKING_MAILING_STATUSES}
]


def _metric_form_prefix(variant):
    return f"metric_{variant.pk}"


def _attach_metric_view_data(variant):
    metric = variant.metric if hasattr(variant, "metric") else None
    variant.metric_obj = metric
    sent = metric.sent if metric else 0
    if sent:
        variant.conversion_rate = (metric.conversions / sent) * 100
        variant.has_conversion_rate = True
    else:
        variant.conversion_rate = 0
        variant.has_conversion_rate = False
    return variant


MAILING_ACTIVE_COLUMNS = [
    {"status": MailingExperiment.Status.BACKLOG, "title": "Подготовка", "color": "secondary"},
    {"status": MailingExperiment.Status.DRAFT, "title": "Разработка", "color": "primary"},
    {"status": MailingExperiment.Status.IN_PROGRESS, "title": "В процессе", "color": "warning"},
    {"status": MailingExperiment.Status.COMPLETED, "title": "На оценке", "color": "dark"},
]

MAILING_LIBRARY_COLUMNS = [
    {"status": MailingExperiment.Status.SUCCESS, "title": "Успех", "color": "success"},
    {"status": MailingExperiment.Status.FAILED, "title": "Провал", "color": "danger"},
    {"status": MailingExperiment.Status.RETEST, "title": "Ретест", "color": "info"},
]


def _build_mailing_columns(experiments):
    active_columns = [{**column, "items": []} for column in MAILING_ACTIVE_COLUMNS]
    library_columns = [{**column, "items": []} for column in MAILING_LIBRARY_COLUMNS]
    active_map = {column["status"]: column for column in active_columns}
    library_map = {column["status"]: column for column in library_columns}

    for experiment in experiments:
        if experiment.status in active_map:
            active_map[experiment.status]["items"].append(experiment)
        elif experiment.status in library_map:
            library_map[experiment.status]["items"].append(experiment)
    return active_columns, library_columns


@login_required
@require_roles('admin', 'manager', 'marketer', 'analyst', UserProfile.Role.BOT_USER)
def mailing_experiments_board(request):
    experiments = (
        MailingExperiment.objects.select_related("created_by").prefetch_related("bots")
        .all()
    )
    active_columns, library_columns = _build_mailing_columns(experiments)

    return render(
        request,
        "marks/mailing_board.html",
        {
            "active_columns": active_columns,
            "library_columns": library_columns,
        },
    )


@login_required
@require_roles('admin', 'manager', 'marketer', 'analyst', UserProfile.Role.BOT_USER)
def mailing_experiment_create(request):
    if request.method == "POST":
        form = MailingExperimentForm(request.POST)
        if form.is_valid():
            experiment = form.save(commit=False)
            experiment.created_by = request.user
            experiment.save()
            messages.success(request, "Рассылочный эксперимент создан.")
            return redirect("mailing_experiments_board")
        messages.error(request, "Не удалось сохранить эксперимент. Проверьте заполнение полей.")
    else:
        form = MailingExperimentForm()

    return render(
        request,
        "marks/mailing_experiment_form.html",
        {"form": form},
    )


def _render_experiment_detail(request, experiment, variant_form=None, metric_forms=None):
    variants = list(
        experiment.variants.select_related("metric")
        .annotate(recipient_count=Count("recipients"))
        .order_by("label", "id")
    )
    for variant in variants:
        _attach_metric_view_data(variant)

    metric_forms = metric_forms or {}
    variants_with_forms = []
    for variant in variants:
        form = metric_forms.get(variant.pk) or MailingVariantMetricForm(
            instance=variant.metric_obj,
            prefix=_metric_form_prefix(variant),
        )
        variants_with_forms.append({"variant": variant, "metric_form": form})

    recipients_count = experiment.recipients.count()
    assigned_total = sum(v.recipient_count for v in variants)
    unassigned_count = max(recipients_count - assigned_total, 0)

    return render(
        request,
        "marks/mailing_experiment_detail.html",
        {
            "experiment": experiment,
            "variants": variants,
            "variants_with_forms": variants_with_forms,
            "variant_form": variant_form or MailingVariantForm(experiment=experiment),
            "recipients_count": recipients_count,
            "unassigned_count": unassigned_count,
            "can_import": len(variants) == REQUIRED_VARIANTS_FOR_IMPORT,
            "is_final": experiment.status in FINAL_MAILING_STATUSES,
            "working_status_choices": WORKING_STATUS_CHOICES,
        },
    )


@login_required
@require_roles('admin', 'manager', 'marketer', 'analyst', UserProfile.Role.BOT_USER)
def mailing_experiment_detail(request, pk):
    experiment = get_object_or_404(
        MailingExperiment.objects.select_related("created_by").prefetch_related("bots"), pk=pk,
    )
    return _render_experiment_detail(request, experiment)


@login_required
@require_POST
@require_roles('admin', 'manager', 'marketer', 'analyst', UserProfile.Role.BOT_USER)
def mailing_variant_add(request, pk):
    experiment = get_object_or_404(MailingExperiment, pk=pk)
    form = MailingVariantForm(request.POST, experiment=experiment)
    if form.is_valid():
        form.save()
        messages.success(request, "Вариант добавлен.")

        variants_now = experiment.variants.count()
        pending_exists = experiment.recipients.filter(
            assigned_variant__isnull=True,
        ).exists()
        if variants_now == REQUIRED_VARIANTS_FOR_IMPORT and pending_exists:
            try:
                apply_split_weights(experiment)
                summary = assign_pending_recipients(experiment)
                messages.success(
                    request,
                    "Загруженные ранее получатели распределены: "
                    + _format_import_summary(summary),
                )
            except MailingSplitError as exc:
                messages.warning(
                    request,
                    f"Не удалось распределить ранее загруженных получателей: {exc}",
                )
        return redirect("mailing_experiment_detail", pk=experiment.pk)
    messages.error(request, "Не удалось добавить вариант. Проверьте заполнение полей.")
    return _render_experiment_detail(request, experiment, variant_form=form)


@login_required
@require_POST
@require_roles('admin', 'manager', 'marketer', 'analyst', UserProfile.Role.BOT_USER)
def mailing_variant_delete(request, pk, variant_pk):
    experiment = get_object_or_404(MailingExperiment, pk=pk)
    variant = get_object_or_404(
        MailingVariant, pk=variant_pk, experiment=experiment,
    )
    variant.delete()
    messages.success(request, "Вариант удалён.")
    return redirect("mailing_experiment_detail", pk=experiment.pk)


def _decode_recipients_file(uploaded_file):
    raw = uploaded_file.read()
    if not raw:
        return ""
    for encoding in ("utf-8-sig", "utf-8", "cp1251"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ValueError(
        "Не удалось прочитать файл. Поддерживаются кодировки UTF-8 и CP1251.",
    )


def _format_import_summary(summary):
    parts = []
    for label in sorted(summary.get("variants", {}).keys()):
        parts.append(f"вариант {label} — {summary['variants'][label]}")
    if summary.get("updated"):
        parts.append(f"обновлено {summary['updated']}")
    if summary.get("skipped"):
        parts.append(f"пропущено {summary['skipped']}")
    base = f"Обработано {summary.get('processed', 0)}"
    if parts:
        return f"{base}: " + ", ".join(parts)
    return base


@login_required
@require_POST
@require_roles('admin', 'manager', 'marketer', 'analyst', UserProfile.Role.BOT_USER)
def mailing_import_recipients(request, pk):
    experiment = get_object_or_404(MailingExperiment, pk=pk)

    uploaded = request.FILES.get("recipients_file")
    if not uploaded:
        messages.error(request, "Прикрепите файл со списком получателей.")
        return redirect("mailing_experiment_detail", pk=experiment.pk)

    try:
        text = _decode_recipients_file(uploaded)
    except ValueError as exc:
        messages.error(request, str(exc))
        return redirect("mailing_experiment_detail", pk=experiment.pk)

    ids = parse_recipient_ids(text)
    if not ids:
        messages.error(
            request,
            "Не нашёл ни одного идентификатора в файле. "
            "Проверьте формат: по одному id на строку или CSV с id в первой колонке.",
        )
        return redirect("mailing_experiment_detail", pk=experiment.pk)

    variants_count = experiment.variants.count()

    if variants_count < REQUIRED_VARIANTS_FOR_IMPORT:
        # Reset any partial assignments to keep state consistent.
        experiment.recipients.update(assigned_variant=None)
        summary = import_recipients(experiment, ids, assign_variants=False)
        messages.success(
            request,
            "Получатели загружены, ждут добавления вариантов. "
            + _format_import_summary(summary),
        )
        return redirect("mailing_experiment_detail", pk=experiment.pk)

    try:
        apply_split_weights(experiment)
    except MailingSplitError as exc:
        messages.error(request, f"Не удалось применить сплит трафика: {exc}")
        return redirect("mailing_experiment_detail", pk=experiment.pk)

    try:
        summary = import_recipients(experiment, ids)
    except MailingSplitError as exc:
        messages.error(request, f"Не удалось распределить получателей: {exc}")
        return redirect("mailing_experiment_detail", pk=experiment.pk)

    messages.success(request, _format_import_summary(summary))
    return redirect("mailing_experiment_detail", pk=experiment.pk)


def _safe_filename_token(value):
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", (value or "").strip())
    return cleaned.strip("._-") or "x"


@login_required
@require_roles('admin', 'manager', 'marketer', 'analyst', UserProfile.Role.BOT_USER)
def mailing_export_cohort(request, pk, variant_pk):
    experiment = get_object_or_404(MailingExperiment, pk=pk)
    variant = get_object_or_404(
        MailingVariant, pk=variant_pk, experiment=experiment,
    )

    external_ids = list(
        variant.recipients.order_by("external_id").values_list("external_id", flat=True)
    )
    body = "\n".join(external_ids)
    if body:
        body += "\n"

    response = HttpResponse(body, content_type="text/plain; charset=utf-8")
    filename = (
        f"experiment_{experiment.pk}_variant_{_safe_filename_token(variant.label)}.txt"
    )
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


@login_required
@require_roles('admin', 'manager', 'marketer', 'analyst', UserProfile.Role.BOT_USER)
def mailing_export_all_cohorts(request, pk):
    experiment = get_object_or_404(MailingExperiment, pk=pk)
    recipients = (
        experiment.recipients
        .select_related("assigned_variant")
        .order_by("assigned_variant__label", "external_id")
    )

    response = HttpResponse(content_type="text/csv; charset=utf-8")
    filename = f"experiment_{experiment.pk}_cohorts.csv"
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    response.write("﻿")

    writer = csv_module.writer(response)
    writer.writerow(["external_id", "variant_label", "start_param"])
    for recipient in recipients:
        variant = recipient.assigned_variant
        writer.writerow([
            recipient.external_id,
            variant.label if variant else "",
            variant.start_param if variant else "",
        ])
    return response


@login_required
@require_POST
@require_roles('admin', 'manager', 'marketer', 'analyst', UserProfile.Role.BOT_USER)
def mailing_variant_metric_edit(request, pk, variant_pk):
    experiment = get_object_or_404(MailingExperiment, pk=pk)
    variant = get_object_or_404(
        MailingVariant, pk=variant_pk, experiment=experiment,
    )
    metric, _ = MailingVariantMetric.objects.get_or_create(variant=variant)
    form = MailingVariantMetricForm(
        request.POST, instance=metric, prefix=_metric_form_prefix(variant),
    )
    if form.is_valid():
        form.save()
        messages.success(request, f"Метрики варианта {variant.label} сохранены.")
        return redirect("mailing_experiment_detail", pk=experiment.pk)

    flat_errors = "; ".join(
        f"{name}: {', '.join(errs)}" for name, errs in form.errors.items()
    ) or "проверьте поля"
    messages.error(
        request,
        f"Не удалось сохранить метрики варианта {variant.label}: {flat_errors}.",
    )
    return _render_experiment_detail(
        request, experiment, metric_forms={variant.pk: form},
    )


@login_required
@require_POST
@require_roles('admin', 'manager', 'marketer', 'analyst', UserProfile.Role.BOT_USER)
def mailing_set_winner(request, pk):
    experiment = get_object_or_404(MailingExperiment, pk=pk)
    action = (request.POST.get("action") or "").strip()

    if action == "fail":
        experiment.winner_variant = None
        experiment.status = MailingExperiment.Status.FAILED
        experiment.save(update_fields=["winner_variant", "status", "updated_at"])
        messages.success(request, "Эксперимент отмечен как провал.")
        return redirect("mailing_experiment_detail", pk=experiment.pk)

    if action == "success":
        variant_pk_raw = (request.POST.get("variant_pk") or "").strip()
        if not variant_pk_raw.isdigit():
            messages.error(request, "Выберите вариант-победитель.")
            return redirect("mailing_experiment_detail", pk=experiment.pk)
        variant = get_object_or_404(
            MailingVariant, pk=int(variant_pk_raw), experiment=experiment,
        )
        experiment.winner_variant = variant
        experiment.status = MailingExperiment.Status.SUCCESS
        experiment.save(update_fields=["winner_variant", "status", "updated_at"])
        messages.success(
            request,
            f"Победитель зафиксирован: вариант {variant.label}.",
        )
        return redirect("mailing_experiment_detail", pk=experiment.pk)

    messages.error(request, "Неизвестное действие.")
    return redirect("mailing_experiment_detail", pk=experiment.pk)


@login_required
@require_POST
@require_roles('admin', 'manager', 'marketer', 'analyst', UserProfile.Role.BOT_USER)
def mailing_set_status(request, pk):
    experiment = get_object_or_404(MailingExperiment, pk=pk)
    new_status = (request.POST.get("status") or "").strip()

    allowed = {code for code, _ in WORKING_STATUS_CHOICES}
    if new_status not in allowed:
        messages.error(
            request,
            "Недопустимый рабочий статус. Финальный исход выставляется отдельно через «Итог теста».",
        )
        return redirect("mailing_experiment_detail", pk=experiment.pk)

    if experiment.status in FINAL_MAILING_STATUSES:
        messages.error(
            request,
            "Эксперимент уже в финальном статусе. Смена рабочей стадии недоступна.",
        )
        return redirect("mailing_experiment_detail", pk=experiment.pk)

    if experiment.status == new_status:
        messages.info(request, "Стадия не изменилась.")
        return redirect("mailing_experiment_detail", pk=experiment.pk)

    experiment.status = new_status
    experiment.save(update_fields=["status", "updated_at"])

    label = dict(MailingExperiment.Status.choices).get(new_status, new_status)
    messages.success(request, f"Стадия эксперимента: {label}.")
    return redirect("mailing_experiment_detail", pk=experiment.pk)
