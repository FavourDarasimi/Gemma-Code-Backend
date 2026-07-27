from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from .models import Conversation
from .serializers import (
    ConversationDetailSerializer,
    ConversationSerializer,
)


class ConversationViewSet(viewsets.ModelViewSet):
    permission_classes = (IsAuthenticated,)
    http_method_names = ["get", "post", "patch", "delete"]

    def get_queryset(self):
        return Conversation.objects.filter(owner=self.request.user)

    def get_serializer_class(self):
        if self.action == "retrieve":
            return ConversationDetailSerializer
        return ConversationSerializer

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)
