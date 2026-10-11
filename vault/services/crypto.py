import base64
import secrets
from hmac import compare_digest

from Crypto.Cipher import AES
from Crypto.Protocol.KDF import scrypt


SCRYPT_N = 2 ** 14
SCRYPT_R = 8
SCRYPT_P = 1
SCRYPT_DKLEN = 64
SCHEME = "scrypt"
KEY_FORMAT = b"v2:"


def _derive(secret, salt):
  derived = scrypt(
    secret,
    salt,
    key_len=SCRYPT_DKLEN,
    N=SCRYPT_N,
    r=SCRYPT_R,
    p=SCRYPT_P,
  )
  return derived[:32], derived[32:]


def create_password_signature(password):
  secret = password.encode("utf-8")
  salt = secrets.token_bytes(16)
  verifier, _ = _derive(secret, salt)
  salt_text = base64.urlsafe_b64encode(salt).decode("ascii")
  verifier_text = base64.urlsafe_b64encode(verifier).decode("ascii")
  return (
    f"{SCHEME}${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}$"
    f"{salt_text}${verifier_text}"
  ).encode("ascii")


def verify_and_derive_vault_key(signature, password):
  try:
    text = bytes(signature).decode("ascii")
    scheme, n, r, p, salt_text, verifier_text = text.split("$", 5)
    if scheme != SCHEME:
      return None
    if (int(n), int(r), int(p)) != (SCRYPT_N, SCRYPT_R, SCRYPT_P):
      return None
    salt = base64.urlsafe_b64decode(salt_text.encode("ascii"))
    expected = base64.urlsafe_b64decode(verifier_text.encode("ascii"))
    actual, vault_key = _derive(password.encode("utf-8"), salt)
    return vault_key if compare_digest(actual, expected) else None
  except (TypeError, ValueError, UnicodeError):
    return None


def _wrap_file_key(vault_key, file_key):
  cipher = AES.new(vault_key, AES.MODE_EAX)
  encrypted_key, tag = cipher.encrypt_and_digest(file_key)
  packed = cipher.nonce + tag + encrypted_key
  return KEY_FORMAT + base64.urlsafe_b64encode(packed)


def _unwrap_file_key(vault_key, wrapped_key):
  wrapped_key = bytes(wrapped_key)
  if not wrapped_key.startswith(KEY_FORMAT):
    raise ValueError("Unsupported document key format")
  packed = base64.urlsafe_b64decode(wrapped_key[len(KEY_FORMAT):])
  if len(packed) != 64:
    raise ValueError("Malformed wrapped document key")
  nonce, tag, ciphertext = packed[:16], packed[16:32], packed[32:]
  return AES.new(vault_key, AES.MODE_EAX, nonce).decrypt_and_verify(
    ciphertext,
    tag,
  )


def encrypt_text(plaintext, vault_key):
  if not isinstance(vault_key, bytes) or len(vault_key) != 32:
    raise ValueError("The authenticated vault key is unavailable")
  file_key = secrets.token_bytes(32)
  cipher = AES.new(file_key, AES.MODE_EAX)
  ciphertext, tag = cipher.encrypt_and_digest(plaintext.encode("utf-8"))
  return {
    "ciphertext": ciphertext,
    "nonce": cipher.nonce,
    "auth_tag": tag,
    "wrapped_key": _wrap_file_key(vault_key, file_key),
  }


def decrypt_document(document, vault_key):
  file_key = _unwrap_file_key(vault_key, document.wrapped_key)
  cipher = AES.new(file_key, AES.MODE_EAX, bytes(document.nonce))
  plaintext = cipher.decrypt_and_verify(
    bytes(document.ciphertext),
    bytes(document.auth_tag),
  )
  return plaintext.decode("utf-8")

