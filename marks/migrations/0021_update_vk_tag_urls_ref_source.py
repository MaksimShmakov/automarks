import re
from urllib.parse import urlencode

from django.db import migrations


def _extract_ref_source(branch_code):
    match = re.search(r"(\d+)$", (branch_code or "").strip())
    if not match:
        return None
    return str(int(match.group(1)))


def update_vk_tag_urls(apps, schema_editor):
    Tag = apps.get_model("marks", "Tag")

    for tag in Tag.objects.select_related("branch__bot").filter(branch__bot__platform="vk"):
        bot_name = (tag.branch.bot.name or "").lstrip("@")
        params = {"ref": tag.number}
        ref_source = _extract_ref_source(tag.branch.code)
        if ref_source is not None:
            params["ref_source"] = ref_source
        tag.url = f"https://vk.com/write-{bot_name}?{urlencode(params)}"
        tag.save(update_fields=["url"])


class Migration(migrations.Migration):

    dependencies = [
        ("marks", "0020_bot_display_name_bot_platform"),
    ]

    operations = [
        migrations.RunPython(update_vk_tag_urls, migrations.RunPython.noop),
    ]
