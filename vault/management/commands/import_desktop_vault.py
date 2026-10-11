import getpass
import os
import sqlite3
from pathlib import Path
from types import SimpleNamespace

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from vault.models import EncryptedDocument, VaultCredential
from vault.services.crypto import decrypt_document, verify_and_derive_vault_key


DEFAULT_DATABASE = "~/.cryptor_app/notebookserver.db"


def _as_bytes(value):
    if isinstance(value, bytes):
        return value
    if isinstance(value, memoryview):
        return value.tobytes()
    if isinstance(value, str):
        return value.encode("utf-8")
    raise CommandError("The desktop database contains an unsupported binary value.")


def _as_text(value):
    if isinstance(value, bytes):
        return value.decode("utf-8")
    if isinstance(value, memoryview):
        return value.tobytes().decode("utf-8")
    return str(value)


def _source_datetime(value):
    if value is None:
        return None
    parsed = parse_datetime(_as_text(value))
    if parsed is not None and timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed, timezone.get_current_timezone())
    return parsed


class Command(BaseCommand):
    help = "Copy one account from the desktop SQLite vault without changing it."

    def add_arguments(self, parser):
        parser.add_argument("--username", required=True)
        parser.add_argument("--database", default=DEFAULT_DATABASE)

    def handle(self, *args, **options):
        database_path = Path(options["database"]).expanduser().resolve()
        username = options["username"].strip()
        if not username:
            raise CommandError("Username cannot be blank.")
        if not database_path.is_file():
            raise CommandError(f"Desktop database not found: {database_path}")

        password = os.environ.get("CRYPTOR_IMPORT_PASSWORD")
        if password is None:
            password = getpass.getpass(f"Desktop vault password for {username}: ")
        if not password:
            raise CommandError("A desktop vault password is required.")

        source_uri = f"{database_path.as_uri()}?mode=ro"
        try:
            with sqlite3.connect(source_uri, uri=True) as connection:
                connection.row_factory = sqlite3.Row
                source_user = self._find_user(connection, username)
                source_documents = self._find_documents(connection, username)
        except sqlite3.Error as exc:
            raise CommandError(f"Could not read the desktop database: {exc}") from exc

        signature = _as_bytes(source_user["password"])
        vault_key = verify_and_derive_vault_key(signature, password)
        if vault_key is None:
            raise CommandError("The desktop username or vault password is incorrect.")

        prepared = self._validate_documents(source_documents, vault_key)
        with transaction.atomic():
            user = self._prepare_user(username, password, signature)
            created_count, updated_count = self._copy_documents(user, prepared)

        self.stdout.write(
            self.style.SUCCESS(
                f"Imported {created_count} and refreshed {updated_count} encrypted "
                f"document(s) for {username}. The desktop database was not changed."
            )
        )

    def _find_user(self, connection, username):
        try:
            rows = connection.execute(
                "SELECT user_name, password FROM users"
            ).fetchall()
        except sqlite3.Error as exc:
            raise CommandError("This is not a compatible Cryptor desktop database.") from exc
        for row in rows:
            if _as_text(row["user_name"]) == username:
                return row
        raise CommandError(f"Desktop user '{username}' was not found.")

    def _find_documents(self, connection, username):
        try:
            rows = connection.execute(
                """
                SELECT file_id, owner_name, data_file, cipher_aes, tag,
                       session_key, ts, last_updated, file_title, file_for
                FROM lockedfiles
                """
            ).fetchall()
        except sqlite3.Error as exc:
            raise CommandError("The desktop document table is incompatible.") from exc
        return [row for row in rows if _as_text(row["owner_name"]) == username]

    def _validate_documents(self, rows, vault_key):
        prepared = []
        for row in rows:
            legacy_id = _as_text(row["file_id"])
            item = {
                "legacy_id": legacy_id,
                "title": (_as_text(row["file_title"]) if row["file_title"] else "Untitled")[:200],
                "purpose": (_as_text(row["file_for"]) if row["file_for"] else "General")[:200],
                "ciphertext": _as_bytes(row["data_file"]),
                "nonce": _as_bytes(row["cipher_aes"]),
                "auth_tag": _as_bytes(row["tag"]),
                "wrapped_key": _as_bytes(row["session_key"]),
                "created_at": _source_datetime(row["ts"]),
                "updated_at": _source_datetime(row["last_updated"]),
            }
            probe = SimpleNamespace(
                ciphertext=item["ciphertext"],
                nonce=item["nonce"],
                auth_tag=item["auth_tag"],
                wrapped_key=item["wrapped_key"],
            )
            try:
                decrypt_document(probe, vault_key)
            except (TypeError, ValueError, UnicodeError) as exc:
                raise CommandError(
                    f"Desktop document {legacy_id} failed authentication; nothing was imported."
                ) from exc
            prepared.append(item)
        return prepared

    def _prepare_user(self, username, password, signature):
        user, created = User.objects.get_or_create(username=username)
        if not created:
            try:
                existing_signature = bytes(user.vault_credential.password_signature)
            except VaultCredential.DoesNotExist:
                existing_signature = None
            if existing_signature is not None and existing_signature != signature:
                raise CommandError(
                    "A web account with this username belongs to a different vault."
                )
        user.set_password(password)
        user.save()
        VaultCredential.objects.update_or_create(
            user=user,
            defaults={"password_signature": signature},
        )
        return user

    def _copy_documents(self, user, prepared):
        created_count = 0
        updated_count = 0
        for item in prepared:
            existing = EncryptedDocument.objects.filter(
                legacy_id=item["legacy_id"]
            ).first()
            if existing is not None and existing.owner_id != user.id:
                raise CommandError("A legacy document identifier belongs to another user.")
            defaults = {
                key: value
                for key, value in item.items()
                if key not in {"legacy_id", "created_at", "updated_at"}
            }
            document, created = EncryptedDocument.objects.update_or_create(
                legacy_id=item["legacy_id"],
                defaults={"owner": user, **defaults},
            )
            created_count += int(created)
            updated_count += int(not created)
            timestamps = {}
            if item["created_at"] is not None:
                timestamps["created_at"] = item["created_at"]
            if item["updated_at"] is not None:
                timestamps["updated_at"] = item["updated_at"]
            if timestamps:
                EncryptedDocument.objects.filter(pk=document.pk).update(**timestamps)
        return created_count, updated_count
