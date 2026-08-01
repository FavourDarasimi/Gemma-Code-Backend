import json
import time

from django.core.exceptions import ValidationError
from django.http import StreamingHttpResponse
from rest_framework import status, viewsets
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .gemma_service import ModelNotAvailableError, is_loaded, load_model, stream_reply
from .models import Conversation, Message
from .serializers import (
    ConversationDetailSerializer,
    ConversationSerializer,
)

CHECKPOINT_INTERVAL = 1.0
CONTINUE_INSTRUCTION = (
    "Continue from where you left off. Do not repeat anything already "
    "written — continue directly from the last line."
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


class ChatView(APIView):
    permission_classes = (IsAuthenticated,)

    def post(self, request):
        conversation_id = request.data.get("conversation_id")
        message = request.data.get("message", "")

        if not message or not isinstance(message, str) or not message.strip():
            return Response(
                {"message": "Message cannot be empty"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if conversation_id is not None:
            try:
                conversation = Conversation.objects.get(
                    id=conversation_id, owner=request.user
                )
            except (ValueError, TypeError, ValidationError):
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
            conversation = Conversation.objects.create(
                owner=request.user, title="New chat"
            )

        try:
            load_model()
        except ModelNotAvailableError as exc:
            return Response(
                {"message": str(exc)},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        Message.objects.create(
            conversation=conversation,
            role=Message.Role.USER,
            content=message,
        )

        if conversation.title == "New chat":
            conversation.title = (message[:40].rstrip() or "New conversation")
            conversation.save(update_fields=["title"])

        assistant_msg = Message.objects.create(
            conversation=conversation,
            role=Message.Role.ASSISTANT,
            content="",
            complete=False,
        )

        history = [
            {"role": m.role, "content": m.content}
            for m in conversation.messages.all()
            if m.id != assistant_msg.id
        ]

        def generate():
            yield f"data: {json.dumps({'conversation_id': str(conversation.id), 'title': conversation.title})}\n\n"
            yield from _persist_stream(assistant_msg, history)

        return StreamingHttpResponse(generate(), content_type="text/event-stream")


class ChatContinueView(APIView):
    permission_classes = (IsAuthenticated,)

    def post(self, request):
        conversation_id = request.data.get("conversation_id")
        if not conversation_id:
            return Response(
                {"conversation_id": "Required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            conversation = Conversation.objects.get(
                id=conversation_id, owner=request.user
            )
        except (ValueError, TypeError, ValidationError):
            return Response(
                {"conversation_id": "Invalid conversation ID"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Conversation.DoesNotExist:
            return Response(
                {"conversation_id": "Conversation not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        last = conversation.messages.last()
        if (
            last is None
            or last.role != Message.Role.ASSISTANT
            or last.complete
        ):
            return Response(
                {"message": "Nothing to continue"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            load_model()
        except ModelNotAvailableError as exc:
            return Response(
                {"message": str(exc)},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        history = [
            {"role": m.role, "content": m.content}
            for m in conversation.messages.all()
        ]
        history.append({"role": "user", "content": CONTINUE_INSTRUCTION})

        def generate():
            yield from _persist_stream(last, history)

        return StreamingHttpResponse(generate(), content_type="text/event-stream")


def _persist_stream(assistant_msg, history):
    """Stream model chunks while checkpoint-saving the partial reply.

    The assistant message exists in the DB before streaming starts
    (``complete=False``); text is throttled to the DB every
    ``CHECKPOINT_INTERVAL`` seconds so an interrupted stream (worker kill,
    proxy timeout) still leaves the partial reply persisted and resumable.
    """
    full_reply = [assistant_msg.content]
    last_save = time.monotonic()

    try:
        for chunk in stream_reply(history):
            full_reply.append(chunk)
            yield f"data: {json.dumps({'text': chunk})}\n\n"
            if time.monotonic() - last_save > CHECKPOINT_INTERVAL:
                Message.objects.filter(id=assistant_msg.id).update(
                    content="".join(full_reply)
                )
                last_save = time.monotonic()
    except ModelNotAvailableError:
        Message.objects.filter(id=assistant_msg.id).update(
            content="".join(full_reply),
            complete=False,
        )
        yield f"data: {json.dumps({'error': 'Couldn\u2019t reach the assistant. Check your connection and try again.'})}\n\n"
        yield "data: [DONE]\n\n"
        return

    Message.objects.filter(id=assistant_msg.id).update(
        content="".join(full_reply),
        complete=True,
    )
    yield "data: [DONE]\n\n"


@api_view(["GET"])
@permission_classes([AllowAny])
def health(request):
    loaded = False
    try:
        load_model()
        loaded = is_loaded()
    except Exception:
        loaded = False

    return Response(
        {
            "status": "ok" if loaded else "error",
            "model_loaded": loaded,
        }
    )
