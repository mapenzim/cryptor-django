import json
import os
import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from vault.models import EncryptedDocument, VaultCredential
from vault.services.crypto import (
  create_password_signature,
  decrypt_document,
  encrypt_text,
  verify_and_derive_vault_key,
)
from vault.services.session_keys import clear_vault_key, get_vault_key


PASSWORD = "correct-horse-battery-staple-2026!"


class VaultFlowTests(TestCase):
  def signup(self, username="alice"):
    response = self.client.post(
      reverse("signup"),
      {
        "username": username,
        "password1": PASSWORD,
        "password2": PASSWORD,
      },
    )
    self.assertRedirects(response, reverse("dashboard"))
    return User.objects.get(username=username)

  def test_signup_creates_credential_and_unlocked_session(self):
    user = self.signup()
    self.assertTrue(hasattr(user, "vault_credential"))
    self.assertIsNotNone(get_vault_key(self.client.session.session_key))

  def test_document_round_trip_and_ciphertext_storage(self):
    user = self.signup()
    secret = "Recovery code: A1-B2-C3-D4"
    response = self.client.post(
      reverse("document_create"),
      {"title": "Recovery", "purpose": "MFA", "content": secret},
    )
    self.assertRedirects(response, reverse("dashboard"))

    document = EncryptedDocument.objects.get(owner=user)
    self.assertNotIn(secret.encode("utf-8"), bytes(document.ciphertext))
    vault_key = get_vault_key(self.client.session.session_key)
    self.assertEqual(decrypt_document(document, vault_key), secret)

    response = self.client.get(reverse("document_edit", args=[document.id]))
    self.assertContains(response, secret)

  def test_documents_are_owner_isolated(self):
    alice = self.signup()
    self.client.post(
      reverse("document_create"),
      {"title": "Alice only", "purpose": "Private", "content": "Alice secret"},
    )
    document = EncryptedDocument.objects.get(owner=alice)
    old_session = self.client.session.session_key
    self.client.post(reverse("logout"))
    self.assertIsNone(get_vault_key(old_session))

    bob = User.objects.create_user(username="bob", password=PASSWORD)
    VaultCredential.objects.create(
      user=bob,
      password_signature=create_password_signature(PASSWORD),
    )
    response = self.client.post(
      reverse("login"),
      {"username": "bob", "password": PASSWORD},
    )
    self.assertRedirects(response, reverse("dashboard"))
    response = self.client.get(reverse("document_edit", args=[document.id]))
    self.assertEqual(response.status_code, 404)

  def test_session_without_memory_key_requires_unlock(self):
    self.signup()
    clear_vault_key(self.client.session.session_key)
    response = self.client.get(reverse("document_create"))
    self.assertRedirects(
      response,
      reverse("unlock") + "?next=%2Fvault%2Fnew%2F",
      fetch_redirect_response=False,
    )

  def test_local_password_generator_endpoint(self):
    self.signup()
    response = self.client.post(
      reverse("ai_generate"),
      data=json.dumps({"prompt": "Generate a strong password"}),
      content_type="application/json",
    )
    self.assertEqual(response.status_code, 200)
    self.assertIn("Password:", response.json()["content"])


class CryptoTests(TestCase):
  def test_wrong_password_cannot_derive_vault_key(self):
    signature = create_password_signature(PASSWORD)
    self.assertIsNotNone(verify_and_derive_vault_key(signature, PASSWORD))
    self.assertIsNone(verify_and_derive_vault_key(signature, "wrong password"))


class DesktopImportTests(TestCase):
  def test_imports_encrypted_documents_without_changing_source(self):
    signature = create_password_signature(PASSWORD)
    vault_key = verify_and_derive_vault_key(signature, PASSWORD)
    encrypted = encrypt_text("Imported desktop secret", vault_key)

    with tempfile.TemporaryDirectory() as directory:
      database = os.path.join(directory, "desktop.db")
      with sqlite3.connect(database) as connection:
        connection.executescript(
          """
          CREATE TABLE users(user_name BLOB, password BLOB);
          CREATE TABLE lockedfiles(
            file_id BLOB, owner_name BLOB, data_file BLOB, cipher_aes BLOB,
            tag BLOB, session_key BLOB, ts TEXT, last_updated TEXT,
            file_title TEXT, file_for TEXT
          );
          """
        )
        connection.execute(
          "INSERT INTO users(user_name, password) VALUES(?, ?)",
          (b"legacy-user", signature),
        )
        connection.execute(
          """
          INSERT INTO lockedfiles VALUES(
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
          )
          """,
          (
            b"legacy-document-id",
            b"legacy-user",
            encrypted["ciphertext"],
            encrypted["nonce"],
            encrypted["auth_tag"],
            encrypted["wrapped_key"],
            "2026-01-02T03:04:05",
            "2026-01-03T04:05:06",
            "Imported note",
            "Migration test",
          ),
        )

      source_before = Path(database).read_bytes()
      with patch.dict(os.environ, {"CRYPTOR_IMPORT_PASSWORD": PASSWORD}):
        call_command(
          "import_desktop_vault",
          username="legacy-user",
          database=database,
          verbosity=0,
        )
      source_after = Path(database).read_bytes()

    self.assertEqual(source_after, source_before)
    user = User.objects.get(username="legacy-user")
    document = EncryptedDocument.objects.get(owner=user)
    imported_key = verify_and_derive_vault_key(
      user.vault_credential.password_signature,
      PASSWORD,
    )
    self.assertEqual(
      decrypt_document(document, imported_key),
      "Imported desktop secret",
    )

