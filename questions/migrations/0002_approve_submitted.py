from django.db import migrations


def approve_submitted(apps, schema_editor):
    """Submitting a question now approves it, so anything left waiting is approved."""
    apps.get_model("questions", "Question").objects.filter(status="submitted").update(status="approved")


class Migration(migrations.Migration):
    dependencies = [("questions", "0001_initial")]
    operations = [migrations.RunPython(approve_submitted, migrations.RunPython.noop)]
