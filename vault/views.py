import json
from functools import wraps
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth import authenticate, login as auth_login, logout as auth_logout
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from .forms import DocumentForm, SignInForm, SignUpForm, UnlockForm
from .models import EncryptedDocument, VaultCredential
from .services.ai import generate_text
from .services.crypto import decrypt_document, encrypt_text, verify_and_derive_vault_key
from .services.session_keys import clear_vault_key, get_vault_key, store_vault_key


def _session_id(request):
  if request.session.session_key is None:
    request.session.save()
  return request.session.session_key


def vault_required(view_func):
  @wraps(view_func)
  @login_required
  def wrapped(request, *args, **kwargs):
    vault_key = get_vault_key(request.session.session_key)
    if vault_key is None:
      target = reverse("unlock") + "?" + urlencode({"next": request.get_full_path()})
      return redirect(target)
    request.vault_key = vault_key
    return view_func(request, *args, **kwargs)

  return wrapped


def home(request):
  return redirect("dashboard" if request.user.is_authenticated else "login")


def signup(request):
  if request.user.is_authenticated:
    return redirect("dashboard")
  form = SignUpForm(request.POST or None)
  if request.method == "POST" and form.is_valid():
    user = form.save()
    auth_login(request, user)
    request.session.set_expiry(45 * 60)
    vault_key = verify_and_derive_vault_key(
      user.vault_credential.password_signature,
      form.cleaned_data["password1"],
    )
    store_vault_key(_session_id(request), vault_key)
    messages.success(request, "Your encrypted vault is ready.")
    return redirect("dashboard")
  return render(request, "registration/signup.html", {"form": form})


def sign_in(request):
  if request.user.is_authenticated:
    return redirect("dashboard")
  form = SignInForm(request.POST or None)
  if request.method == "POST" and form.is_valid():
    username = form.cleaned_data["username"]
    password = form.cleaned_data["password"]
    user = authenticate(request, username=username, password=password)
    if user is None:
      form.add_error(None, "Invalid username or password.")
    else:
      try:
        signature = user.vault_credential.password_signature
      except VaultCredential.DoesNotExist:
        form.add_error(None, "This account does not have a vault credential.")
      else:
        vault_key = verify_and_derive_vault_key(signature, password)
        if vault_key is None:
          form.add_error(None, "The vault password could not be verified.")
        else:
          auth_login(request, user)
          request.session.set_expiry(45 * 60)
          store_vault_key(_session_id(request), vault_key)
          return redirect("dashboard")
  return render(request, "registration/login.html", {"form": form})


@login_required
def unlock(request):
  if get_vault_key(request.session.session_key) is not None:
    return redirect("dashboard")
  form = UnlockForm(request.POST or None)
  next_url = request.POST.get("next") or request.GET.get("next") or reverse("dashboard")
  if not url_has_allowed_host_and_scheme(
    next_url,
    allowed_hosts={request.get_host()},
    require_https=request.is_secure(),
  ):
    next_url = reverse("dashboard")
  if request.method == "POST" and form.is_valid():
    password = form.cleaned_data["password"]
    vault_key = verify_and_derive_vault_key(
      request.user.vault_credential.password_signature,
      password,
    )
    if vault_key is None:
      form.add_error("password", "Incorrect vault password.")
    else:
      store_vault_key(_session_id(request), vault_key)
      return redirect(next_url)
  return render(
    request,
    "registration/unlock.html",
    {"form": form, "next": next_url},
  )


@require_POST
@login_required
def sign_out(request):
  clear_vault_key(request.session.session_key)
  auth_logout(request)
  return redirect("login")


@login_required
def dashboard(request):
  documents = EncryptedDocument.objects.filter(owner=request.user)
  return render(
    request,
    "vault/dashboard.html",
    {
      "documents": documents,
      "vault_unlocked": get_vault_key(request.session.session_key) is not None,
    },
  )


@vault_required
def document_create(request):
  form = DocumentForm(request.POST or None)
  if request.method == "POST" and form.is_valid():
    payload = encrypt_text(form.cleaned_data["content"], request.vault_key)
    EncryptedDocument.objects.create(
      owner=request.user,
      title=form.cleaned_data["title"],
      purpose=form.cleaned_data["purpose"],
      **payload,
    )
    messages.success(request, "Document encrypted and saved.")
    return redirect("dashboard")
  return render(
    request,
    "vault/editor.html",
    {"form": form, "document": None},
  )


@vault_required
def document_edit(request, document_id):
  document = get_object_or_404(
    EncryptedDocument,
    id=document_id,
    owner=request.user,
  )
  try:
    current_content = decrypt_document(document, request.vault_key)
  except (ValueError, UnicodeError) as exc:
    messages.error(request, f"Document authentication failed: {exc}")
    return redirect("dashboard")

  initial = {
    "title": document.title,
    "purpose": document.purpose,
    "content": current_content,
  }
  form = DocumentForm(request.POST or None, initial=initial)
  if request.method == "POST" and form.is_valid():
    payload = encrypt_text(form.cleaned_data["content"], request.vault_key)
    document.title = form.cleaned_data["title"]
    document.purpose = form.cleaned_data["purpose"]
    for field, value in payload.items():
      setattr(document, field, value)
    document.save()
    messages.success(request, "Document encrypted and updated.")
    return redirect("dashboard")
  return render(
    request,
    "vault/editor.html",
    {"form": form, "document": document},
  )


@require_POST
@vault_required
def document_delete(request, document_id):
  document = get_object_or_404(
    EncryptedDocument,
    id=document_id,
    owner=request.user,
  )
  document.delete()
  messages.success(request, "Document permanently deleted.")
  return redirect("dashboard")


@require_POST
@vault_required
def ai_generate(request):
  try:
    data = json.loads(request.body or b"{}")
  except json.JSONDecodeError:
    return JsonResponse({"error": "Invalid JSON request."}, status=400)
  prompt = str(data.get("prompt", "")).strip()
  if not prompt:
    return JsonResponse({"error": "Type an AI instruction first."}, status=400)
  try:
    return JsonResponse({"content": generate_text(prompt)})
  except (ValueError, RuntimeError) as exc:
    return JsonResponse({"error": str(exc)}, status=503)

