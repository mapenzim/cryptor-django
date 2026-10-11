import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
  initial = True

  dependencies = [
    migrations.swappable_dependency(settings.AUTH_USER_MODEL),
  ]

  operations = [
    migrations.CreateModel(
      name="VaultCredential",
      fields=[
        ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
        ("password_signature", models.BinaryField()),
        ("created_at", models.DateTimeField(auto_now_add=True)),
        ("updated_at", models.DateTimeField(auto_now=True)),
        (
          "user",
          models.OneToOneField(
            on_delete=django.db.models.deletion.CASCADE,
            related_name="vault_credential",
            to=settings.AUTH_USER_MODEL,
          ),
        ),
      ],
    ),
    migrations.CreateModel(
      name="EncryptedDocument",
      fields=[
        ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
        ("title", models.CharField(max_length=200)),
        ("purpose", models.CharField(max_length=200)),
        ("ciphertext", models.BinaryField()),
        ("nonce", models.BinaryField()),
        ("auth_tag", models.BinaryField()),
        ("wrapped_key", models.BinaryField()),
        ("created_at", models.DateTimeField(auto_now_add=True)),
        ("updated_at", models.DateTimeField(auto_now=True)),
        (
          "owner",
          models.ForeignKey(
            on_delete=django.db.models.deletion.CASCADE,
            related_name="encrypted_documents",
            to=settings.AUTH_USER_MODEL,
          ),
        ),
      ],
      options={"ordering": ["-updated_at"]},
    ),
  ]

