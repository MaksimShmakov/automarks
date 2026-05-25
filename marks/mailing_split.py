import hashlib


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
