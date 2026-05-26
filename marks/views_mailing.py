from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .mailing_forms import MailingExperimentForm, MailingVariantForm
from .models import MailingExperiment, MailingVariant, UserProfile
from .permissions import require_roles


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
        MailingExperiment.objects.select_related("bot", "created_by")
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


def _render_experiment_detail(request, experiment, variant_form=None):
    variants = experiment.variants.all().order_by("label", "id")
    return render(
        request,
        "marks/mailing_experiment_detail.html",
        {
            "experiment": experiment,
            "variants": variants,
            "variant_form": variant_form or MailingVariantForm(experiment=experiment),
        },
    )


@login_required
@require_roles('admin', 'manager', 'marketer', 'analyst', UserProfile.Role.BOT_USER)
def mailing_experiment_detail(request, pk):
    experiment = get_object_or_404(
        MailingExperiment.objects.select_related("bot", "created_by"), pk=pk,
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
