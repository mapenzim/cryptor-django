import uuid

from django.contrib.auth.models import User
from django.db import models


class VaultCredential(models.Model):
  user = models.OneToOneField(
    User,
    on_delete=models.CASCADE,
    related_name="vault_credential",
  )
  password_signature = models.BinaryField()
  created_at = models.DateTimeField(auto_now_add=True)
  updated_at = models.DateTimeField(auto_now=True)

  def __str__(self):
    return f"Vault credential for {self.user.username}"


class EncryptedDocument(models.Model):
  id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
  owner = models.ForeignKey(
    User,
    on_delete=models.CASCADE,
    related_name="encrypted_documents",
  )
  legacy_id = models.CharField(max_length=128, unique=True, null=True, blank=True)
  title = models.CharField(max_length=200)
  purpose = models.CharField(max_length=200)
  ciphertext = models.BinaryField()
  nonce = models.BinaryField()
  auth_tag = models.BinaryField()
  wrapped_key = models.BinaryField()
  created_at = models.DateTimeField(auto_now_add=True)
  updated_at = models.DateTimeField(auto_now=True)

  class Meta:
    ordering = ["-updated_at"]

  def __str__(self):
    return self.title

