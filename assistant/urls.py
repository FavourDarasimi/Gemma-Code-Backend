from django.urls import path

from . import views

urlpatterns = [
    path("chat/", views.ChatView.as_view(), name="chat"),
    path("health/", views.health, name="health"),
    path(
        "conversations/",
        views.ConversationViewSet.as_view(
            {"get": "list", "post": "create"}
        ),
        name="conversation-list",
    ),
    path(
        "conversations/<uuid:pk>/",
        views.ConversationViewSet.as_view(
            {"get": "retrieve", "patch": "partial_update", "delete": "destroy"}
        ),
        name="conversation-detail",
    ),
]
