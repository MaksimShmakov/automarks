from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from .mailing_forms import MailingExperimentForm
from .models import MailingExperiment, UserProfile
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
