from django.urls import path

from . import views


urlpatterns = [
  path("", views.home, name="home"),
  path("signup/", views.signup, name="signup"),
  path("login/", views.sign_in, name="login"),
  path("unlock/", views.unlock, name="unlock"),
  path("logout/", views.sign_out, name="logout"),
  path("vault/", views.dashboard, name="dashboard"),
  path("vault/new/", views.document_create, name="document_create"),
  path("vault/<uuid:document_id>/", views.document_edit, name="document_edit"),
  path(
    "vault/<uuid:document_id>/delete/",
    views.document_delete,
    name="document_delete",
  ),
  path("api/ai/generate/", views.ai_generate, name="ai_generate"),
]

