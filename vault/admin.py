from django.contrib import admin

from .models import EncryptedDocument, VaultCredential


@admin.register(EncryptedDocument)
class EncryptedDocumentAdmin(admin.ModelAdmin):
  list_display = ("title", "owner", "purpose", "updated_at")
  list_filter = ("owner",)
  search_fields = ("title", "purpose", "owner__username")
  readonly_fields = (
    "ciphertext",
    "nonce",
    "auth_tag",
    "wrapped_key",
    "created_at",
    "updated_at",
  )


@admin.register(VaultCredential)
class VaultCredentialAdmin(admin.ModelAdmin):
  list_display = ("user", "created_at", "updated_at")
  readonly_fields = ("password_signature", "created_at", "updated_at")

