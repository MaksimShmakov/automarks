import hashlib
from collections import Counter

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


def import_recipients(experiment, external_ids):
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
            variant = assign_variant_for_recipient(experiment, external_id)
            _, created = MailingRecipient.objects.update_or_create(
                experiment=experiment,
                external_id=external_id,
                defaults={"assigned_variant": variant},
            )
            if created:
                summary["created"] += 1
            else:
                summary["updated"] += 1
            variant_counts[variant.label] += 1

    summary["variants"] = dict(variant_counts)
    return summary
