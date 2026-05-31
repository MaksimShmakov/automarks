import csv as csv_module
import hashlib
from collections import Counter
from io import StringIO

from django.db import transaction


class MailingSplitError(ValueError):
    pass


def assign_variant_for_recipient(experiment, external_id):
    variants = list(experiment.variants.all().order_by("label", "id"))
    if not variants:
        raise MailingSplitError(
            f"MailingExperiment #{experiment.pk} has no variants."
        )

    total_weight = sum(int(v.weight or 0) for v in variants)
    if total_weight <= 0:
        raise MailingSplitError(
            f"MailingExperiment #{experiment.pk} has zero total weight."
        )

    seed = f"{experiment.pk}:{external_id}".encode("utf-8")
    bucket = int(hashlib.sha256(seed).hexdigest()[:16], 16) % total_weight

    cumulative = 0
    for variant in variants:
        cumulative += int(variant.weight or 0)
        if bucket < cumulative:
            return variant
    return variants[-1]


def import_recipients(experiment, external_ids, assign_variants=True):
    from .models import MailingRecipient

    seen = set()
    cleaned = []
    skipped = 0
    for raw_id in external_ids or ():
        if raw_id is None:
            skipped += 1
            continue
        normalized = str(raw_id).strip()
        if not normalized:
            skipped += 1
            continue
        if normalized in seen:
            continue
        seen.add(normalized)
        cleaned.append(normalized)

    summary = {
        "processed": len(cleaned),
        "created": 0,
        "updated": 0,
        "skipped": skipped,
        "variants": {},
    }

    if not cleaned:
        return summary

    variant_counts = Counter()

    with transaction.atomic():
        for external_id in cleaned:
            if assign_variants:
                variant = assign_variant_for_recipient(experiment, external_id)
            else:
                variant = None
            _, created = MailingRecipient.objects.update_or_create(
                experiment=experiment,
                external_id=external_id,
                defaults={"assigned_variant": variant},
            )
            if created:
                summary["created"] += 1
            else:
                summary["updated"] += 1
            if variant is not None:
                variant_counts[variant.label] += 1

    summary["variants"] = dict(variant_counts)
    return summary


def assign_pending_recipients(experiment):
    from .models import MailingRecipient

    pending = list(
        MailingRecipient.objects
        .filter(experiment=experiment, assigned_variant__isnull=True)
        .order_by("external_id")
    )

    summary = {
        "processed": 0,
        "created": 0,
        "updated": 0,
        "skipped": 0,
        "variants": {},
    }
    if not pending:
        return summary

    variant_counts = Counter()
    with transaction.atomic():
        for recipient in pending:
            variant = assign_variant_for_recipient(experiment, recipient.external_id)
            recipient.assigned_variant = variant
            recipient.save(update_fields=["assigned_variant"])
            variant_counts[variant.label] += 1
            summary["updated"] += 1

    summary["processed"] = len(pending)
    summary["variants"] = dict(variant_counts)
    return summary


def apply_split_weights(experiment):
    from .models import Experiment

    weights = Experiment.parse_traffic_split(
        experiment.traffic_split, experiment.traffic_split_other,
    )
    if weights is None:
        raise MailingSplitError(
            f"MailingExperiment #{experiment.pk}: cannot parse traffic_split "
            f"({experiment.traffic_split!r}, other={experiment.traffic_split_other!r})."
        )

    variants = list(experiment.variants.all().order_by("label", "id"))
    if not variants:
        raise MailingSplitError(
            f"MailingExperiment #{experiment.pk} has no variants."
        )
    if len(variants) != len(weights):
        raise MailingSplitError(
            f"MailingExperiment #{experiment.pk}: split has {len(weights)} weight(s), "
            f"but experiment has {len(variants)} variant(s)."
        )

    assigned = {}
    with transaction.atomic():
        for variant, weight in zip(variants, weights):
            variant.weight = int(weight)
            variant.save(update_fields=["weight"])
            assigned[variant.label] = int(weight)
    return assigned


def _looks_like_header(value):
    stripped = (value or "").strip()
    if not stripped:
        return False
    return not any(ch.isdigit() for ch in stripped)


def parse_recipient_ids(raw_text):
    if not raw_text:
        return []

    lines = raw_text.splitlines()
    non_empty = [ln for ln in lines if ln.strip()]
    if not non_empty:
        return []

    has_comma = any("," in ln for ln in non_empty)
    has_semi = any(";" in ln for ln in non_empty)

    if has_comma or has_semi:
        delimiter = ";" if has_semi and not has_comma else ","
        reader = csv_module.reader(StringIO(raw_text), delimiter=delimiter)
        rows = [
            row
            for row in reader
            if any((cell or "").strip() for cell in row)
        ]
        if not rows:
            return []
        if _looks_like_header(rows[0][0] if rows[0] else ""):
            rows = rows[1:]
        result = []
        for row in rows:
            if not row:
                continue
            value = (row[0] or "").strip()
            if value:
                result.append(value)
        return result

    cleaned = [ln.strip() for ln in non_empty]
    if cleaned and _looks_like_header(cleaned[0]):
        cleaned = cleaned[1:]
    return cleaned
