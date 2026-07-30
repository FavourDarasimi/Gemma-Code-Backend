from django.contrib import admin
from django.urls import include, re_path

urlpatterns = [
    re_path(r"^admin/", admin.site.urls),
    re_path(r"^api/auth/", include("accounts.urls")),
    re_path(r"^api/", include("assistant.urls")),
]
