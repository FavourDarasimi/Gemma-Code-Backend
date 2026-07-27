from django.urls import path

from . import views

urlpatterns = [
    path("signup/", views.SignupView.as_view(), name="auth-signup"),
    path("login/", views.LoginView.as_view(), name="auth-login"),
    path("logout/", views.LogoutView.as_view(), name="auth-logout"),
    path("session/", views.SessionView.as_view(), name="auth-session"),
    path(
        "oauth/github/redirect/",
        views.GitHubRedirectView.as_view(),
        name="oauth-github-redirect",
    ),
    path(
        "oauth/github/callback/",
        views.GitHubCallbackView.as_view(),
        name="oauth-github-callback",
    ),
    path(
        "oauth/google/redirect/",
        views.GoogleRedirectView.as_view(),
        name="oauth-google-redirect",
    ),
    path(
        "oauth/google/callback/",
        views.GoogleCallbackView.as_view(),
        name="oauth-google-callback",
    ),
]
