import os
import secrets
import string


MODEL = os.environ.get("CRYPTOR_OLLAMA_MODEL", "llama3:8b").strip() or "llama3:8b"
try:
  TIMEOUT = max(30.0, float(os.environ.get("CRYPTOR_OLLAMA_TIMEOUT", "300")))
except ValueError:
  TIMEOUT = 300.0


def _password_note():
  alphabet = string.ascii_letters + string.digits + "!@#$%^&*()_+"
  password = "".join(secrets.choice(alphabet) for _ in range(20))
  return (
    "--- GENERATED SECURE CREDENTIAL ---\n\n"
    f"Password: {password}\n\n"
    "Store this credential only inside your encrypted vault."
  )


def generate_text(prompt):
  prompt = prompt.strip()
  if not prompt:
    raise ValueError("Type an AI instruction first.")
  if "password" in prompt.lower():
    return _password_note()

  from ollama import Client

  try:
    response = Client(timeout=TIMEOUT).chat(
      model=MODEL,
      keep_alive="10m",
      options={"num_predict": 256},
      messages=[
        {
          "role": "system",
          "content": (
            "You are a secure local cryptographic helper. Return only the "
            "requested template or content without conversational preamble."
          ),
        },
        {"role": "user", "content": prompt},
      ],
    )
    return response["message"]["content"]
  except Exception as exc:
    message = str(exc)
    normalized = message.lower()
    error_name = type(exc).__name__.lower()
    if "404" in normalized and "not found" in normalized:
      raise RuntimeError(
        f"Ollama model '{MODEL}' is missing. Run: ollama pull {MODEL}"
      ) from exc
    if "timeout" in error_name or "timed out" in normalized:
      raise RuntimeError(
        f"Ollama exceeded {TIMEOUT:g} seconds. Try again or increase "
        "CRYPTOR_OLLAMA_TIMEOUT."
      ) from exc
    if "connection refused" in normalized or "failed to connect" in normalized:
      raise RuntimeError("Ollama is not running. Start it and try again.") from exc
    raise RuntimeError(message or "Ollama generation failed.") from exc

