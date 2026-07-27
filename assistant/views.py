import json
import time

from django.http import StreamingHttpResponse
from rest_framework import status, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Conversation, Message
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


MOCK_REPLY = (
    "I understand your request. Let me analyze the code carefully. "
    "Based on what you've shown me, I can suggest a structured approach "
    "to solve this. Would you like me to elaborate on any part?"
)


class ChatView(APIView):
    permission_classes = (IsAuthenticated,)

    def post(self, request):
        conversation_id = request.data.get("conversation_id")
        messages = request.data.get("messages", [])

        if not messages or not isinstance(messages, list):
            return Response(
                {"messages": "At least one message is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        last_msg = messages[-1]
        if not last_msg.get("content", "").strip():
            return Response(
                {"messages": "Message content cannot be empty"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if conversation_id is not None:
            try:
                conversation = Conversation.objects.get(
                    id=int(conversation_id), owner=request.user
                )
            except (ValueError, TypeError):
                return Response(
                    {"conversation_id": "Invalid conversation ID"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            except Conversation.DoesNotExist:
                return Response(
                    {"conversation_id": "Conversation not found"},
                    status=status.HTTP_404_NOT_FOUND,
                )
        else:
            title = (last_msg["content"][:40].rstrip() or "New conversation")
            conversation = Conversation.objects.create(
                owner=request.user, title=title
            )

        Message.objects.create(
            conversation=conversation,
            role=Message.Role.USER,
            content=last_msg["content"],
        )

        def generate():
            words = MOCK_REPLY.split()
            for i, word in enumerate(words):
                chunk = word + (" " if i < len(words) - 1 else "")
                yield f"data: {json.dumps({'text': chunk})}\n\n"
                time.sleep(0.02)
            yield "data: [DONE]\n\n"

            Message.objects.create(
                conversation=conversation,
                role=Message.Role.ASSISTANT,
                content=MOCK_REPLY,
            )

        return StreamingHttpResponse(generate(), content_type="text/event-stream")
