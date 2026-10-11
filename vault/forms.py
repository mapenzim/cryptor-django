from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from django.db import transaction

from .models import VaultCredential
from .services.crypto import create_password_signature


class SignUpForm(UserCreationForm):
    class Meta:
        model = User
        fields = ("username", "password1", "password2")

    def clean_password1(self):
        password = self.cleaned_data["password1"]
        if len(password) < 12:
            raise forms.ValidationError("Use at least 12 characters.")
        return password

    @transaction.atomic
    def save(self, commit=True):
        if not commit:
            raise ValueError("Vault users must be saved atomically")
        user = super().save(commit=True)
        VaultCredential.objects.create(
            user=user,
            password_signature=create_password_signature(
                self.cleaned_data["password1"],
            ),
        )
        return user


class SignInForm(forms.Form):
    username = forms.CharField(
        max_length=150,
        widget=forms.TextInput(attrs={"autofocus": True}),
    )
    password = forms.CharField(widget=forms.PasswordInput)


class UnlockForm(forms.Form):
    password = forms.CharField(
        label="Vault password",
        widget=forms.PasswordInput(attrs={"autocomplete": "current-password"}),
    )


class DocumentForm(forms.Form):
    title = forms.CharField(max_length=200)
    purpose = forms.CharField(max_length=200)
    content = forms.CharField(
        min_length=6,
        widget=forms.Textarea(attrs={"rows": 22}),
    )


class PromptForm(forms.Form):
    prompt = forms.CharField(max_length=2000)

