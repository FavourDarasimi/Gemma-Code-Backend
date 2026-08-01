import json
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse
from rest_framework import status

from accounts.models import CustomUser
from .gemma_service import ModelNotAvailableError
from .models import Conversation, Message


class ConversationAPITests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.alice = CustomUser.objects.create_user("alice@test.com", "pass1234")
        cls.bob = CustomUser.objects.create_user("bob@test.com", "pass1234")

    def setUp(self):
        self.list_url = reverse("conversation-list")

    def _auth(self, user):
        from rest_framework_simplejwt.tokens import RefreshToken

        refresh = RefreshToken.for_user(user)
        return f"Bearer {refresh.access_token}"

    # ── unauthenticated ──────────────────────────────────────────

    def test_unauthenticated_list_returns_401(self):
        resp = self.client.get(self.list_url)
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_unauthenticated_create_returns_401(self):
        resp = self.client.post(self.list_url, {"title": "x"})
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_unauthenticated_retrieve_returns_401(self):
        resp = self.client.get(
            reverse("conversation-detail", args=["00000000-0000-0000-0000-000000000001"])
        )
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_unauthenticated_patch_returns_401(self):
        resp = self.client.patch(
            reverse("conversation-detail", args=["00000000-0000-0000-0000-000000000001"])
        )
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_unauthenticated_delete_returns_401(self):
        resp = self.client.delete(
            reverse("conversation-detail", args=["00000000-0000-0000-0000-000000000001"])
        )
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    # ── create ───────────────────────────────────────────────────

    def test_create_conversation(self):
        resp = self.client.post(
            self.list_url,
            {"title": "My chat"},
            HTTP_AUTHORIZATION=self._auth(self.alice),
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        data = resp.json()
        self.assertEqual(data["title"], "My chat")
        self.assertIn("id", data)
        self.assertIn("created_at", data)
        self.assertIn("updated_at", data)
        self.assertNotIn("messages", data)

    def test_create_conversation_default_title(self):
        resp = self.client.post(
            self.list_url,
            {},
            HTTP_AUTHORIZATION=self._auth(self.alice),
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(resp.json()["title"], "New conversation")

    # ── list ─────────────────────────────────────────────────────

    def test_list_own_conversations_only(self):
        Conversation.objects.create(owner=self.alice, title="Alice chat")
        Conversation.objects.create(owner=self.bob, title="Bob chat")

        resp = self.client.get(
            self.list_url,
            HTTP_AUTHORIZATION=self._auth(self.alice),
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        titles = [c["title"] for c in resp.json()]
        self.assertIn("Alice chat", titles)
        self.assertNotIn("Bob chat", titles)

    def test_list_does_not_include_messages(self):
        conv = Conversation.objects.create(owner=self.alice, title="test")
        Message.objects.create(conversation=conv, role="user", content="hi")

        resp = self.client.get(
            self.list_url,
            HTTP_AUTHORIZATION=self._auth(self.alice),
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertNotIn("messages", resp.json()[0])

    # ── retrieve ─────────────────────────────────────────────────

    def test_retrieve_includes_messages(self):
        conv = Conversation.objects.create(owner=self.alice, title="test")
        msg = Message.objects.create(
            conversation=conv, role="user", content="Hello"
        )

        resp = self.client.get(
            reverse("conversation-detail", args=[conv.id]),
            HTTP_AUTHORIZATION=self._auth(self.alice),
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        data = resp.json()
        self.assertIn("messages", data)
        self.assertEqual(len(data["messages"]), 1)
        self.assertEqual(data["messages"][0]["content"], "Hello")

    def test_retrieve_messages_ordered_by_created_at(self):
        conv = Conversation.objects.create(owner=self.alice, title="test")
        m1 = Message.objects.create(conversation=conv, role="user", content="First")
        m2 = Message.objects.create(
            conversation=conv, role="assistant", content="Second"
        )

        resp = self.client.get(
            reverse("conversation-detail", args=[conv.id]),
            HTTP_AUTHORIZATION=self._auth(self.alice),
        )
        contents = [m["content"] for m in resp.json()["messages"]]
        self.assertEqual(contents, ["First", "Second"])

    # ── update (rename) ──────────────────────────────────────────

    def test_patch_rename(self):
        conv = Conversation.objects.create(owner=self.alice, title="old")
        resp = self.client.patch(
            reverse("conversation-detail", args=[conv.id]),
            {"title": "renamed"},
            content_type="application/json",
            HTTP_AUTHORIZATION=self._auth(self.alice),
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.json()["title"], "renamed")
        conv.refresh_from_db()
        self.assertEqual(conv.title, "renamed")

    # ── delete ───────────────────────────────────────────────────

    def test_delete_own_conversation(self):
        conv = Conversation.objects.create(owner=self.alice)
        resp = self.client.delete(
            reverse("conversation-detail", args=[conv.id]),
            HTTP_AUTHORIZATION=self._auth(self.alice),
        )
        self.assertEqual(resp.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Conversation.objects.filter(id=conv.id).exists())

    # ── ownership scoping → 404 ──────────────────────────────────

    def _bobs_conversation(self):
        return Conversation.objects.create(owner=self.bob, title="Bob secret")

    def test_retrieve_other_users_conversation_returns_404(self):
        conv = self._bobs_conversation()
        resp = self.client.get(
            reverse("conversation-detail", args=[conv.id]),
            HTTP_AUTHORIZATION=self._auth(self.alice),
        )
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_patch_other_users_conversation_returns_404(self):
        conv = self._bobs_conversation()
        resp = self.client.patch(
            reverse("conversation-detail", args=[conv.id]),
            {"title": "hacked"},
            content_type="application/json",
            HTTP_AUTHORIZATION=self._auth(self.alice),
        )
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_delete_other_users_conversation_returns_404(self):
        conv = self._bobs_conversation()
        resp = self.client.delete(
            reverse("conversation-detail", args=[conv.id]),
            HTTP_AUTHORIZATION=self._auth(self.alice),
        )
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)
        self.assertTrue(Conversation.objects.filter(id=conv.id).exists())

    # ── cascade delete ───────────────────────────────────────────

    def test_delete_conversation_cascades_to_messages(self):
        conv = Conversation.objects.create(owner=self.alice)
        Message.objects.create(conversation=conv, role="user", content="msg")
        conv.delete()
        self.assertEqual(Message.objects.count(), 0)


CHUNKS = [
    "I understand your request. Let me analyze the code carefully. ",
    "Based on what you've shown me, I can suggest a structured approach ",
    "to solve this. Would you like me to elaborate on any part?",
]


class ChatAPITests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.alice = CustomUser.objects.create_user("alice@test.com", "pass1234")
        cls.bob = CustomUser.objects.create_user("bob@test.com", "pass1234")

    def setUp(self):
        self.url = reverse("chat")
        self.stream_patcher = patch("assistant.views.stream_reply")
        self.mock_stream = self.stream_patcher.start()
        self.mock_stream.return_value = iter(CHUNKS)

    def tearDown(self):
        self.stream_patcher.stop()

    def _auth(self, user):
        from rest_framework_simplejwt.tokens import RefreshToken

        refresh = RefreshToken.for_user(user)
        return f"Bearer {refresh.access_token}"

    def _consume_stream(self, resp):
        return b"".join(resp.streaming_content).decode()

    # ── unauthenticated ──────────────────────────────────────────

    def test_unauthenticated_returns_401(self):
        resp = self.client.post(self.url, {"message": "hi"})
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    # ── validation ───────────────────────────────────────────────

    def test_missing_message_returns_400(self):
        resp = self.client.post(
            self.url,
            {},
            content_type="application/json",
            HTTP_AUTHORIZATION=self._auth(self.alice),
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_empty_message_returns_400(self):
        resp = self.client.post(
            self.url,
            {"message": ""},
            content_type="application/json",
            HTTP_AUTHORIZATION=self._auth(self.alice),
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_whitespace_message_returns_400(self):
        resp = self.client.post(
            self.url,
            {"message": "   "},
            content_type="application/json",
            HTTP_AUTHORIZATION=self._auth(self.alice),
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    # ── new conversation ─────────────────────────────────────────

    def test_new_conversation_creates_conversation_and_saves_messages(self):
        resp = self.client.post(
            self.url,
            {
                "conversation_id": None,
                "message": "Hello, how are you?",
            },
            content_type="application/json",
            HTTP_AUTHORIZATION=self._auth(self.alice),
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        body = self._consume_stream(resp)
        self.assertIn("data: [DONE]", body)
        self.assertIn("data: ", body)

        messages = Message.objects.filter(conversation__owner=self.alice)
        self.assertEqual(messages.count(), 2)
        self.assertEqual(messages.filter(role="user").count(), 1)
        self.assertEqual(messages.filter(role="assistant").count(), 1)
        self.assertEqual(messages.filter(role="user").first().content, "Hello, how are you?")
        self.assertEqual(
            messages.filter(role="assistant").first().content,
            "".join(CHUNKS),
        )

    def test_new_conversation_title_from_first_message(self):
        resp = self.client.post(
            self.url,
            {
                "conversation_id": None,
                "message": "Can you help me refactor this Python function?",
            },
            content_type="application/json",
            HTTP_AUTHORIZATION=self._auth(self.alice),
        )
        self._consume_stream(resp)
        conv = Conversation.objects.get(owner=self.alice)
        self.assertEqual(conv.title, "Can you help me refactor this Python fun")

    def test_new_conversation_title_fallback_when_short(self):
        resp = self.client.post(
            self.url,
            {
                "conversation_id": None,
                "message": "Hi",
            },
            content_type="application/json",
            HTTP_AUTHORIZATION=self._auth(self.alice),
        )
        self._consume_stream(resp)
        conv = Conversation.objects.get(owner=self.alice)
        self.assertEqual(conv.title, "Hi")

    # ── existing conversation ────────────────────────────────────

    def test_existing_conversation_appends_messages(self):
        conv = Conversation.objects.create(owner=self.alice, title="Existing")

        resp = self.client.post(
            self.url,
            {
                "conversation_id": conv.id,
                "message": "Another question",
            },
            content_type="application/json",
            HTTP_AUTHORIZATION=self._auth(self.alice),
        )
        self._consume_stream(resp)

        self.assertEqual(conv.messages.filter(role="user").count(), 1)
        self.assertEqual(conv.messages.filter(role="assistant").count(), 1)
        self.assertEqual(
            conv.messages.filter(role="user").first().content, "Another question"
        )

    # ── conversation memory ──────────────────────────────────────

    def test_conversation_memory(self):
        resp = self.client.post(
            self.url,
            {"conversation_id": None, "message": "First question"},
            content_type="application/json",
            HTTP_AUTHORIZATION=self._auth(self.alice),
        )
        self._consume_stream(resp)

        conv = Conversation.objects.get(owner=self.alice)
        self.assertEqual(conv.messages.count(), 2)

        resp = self.client.post(
            self.url,
            {"conversation_id": conv.id, "message": "Second question"},
            content_type="application/json",
            HTTP_AUTHORIZATION=self._auth(self.alice),
        )
        self._consume_stream(resp)

        self.assertEqual(conv.messages.count(), 4)
        roles = list(conv.messages.values_list("role", flat=True))
        self.assertEqual(roles, ["user", "assistant", "user", "assistant"])

    # ── SSE format ───────────────────────────────────────────────

    def test_sse_format(self):
        resp = self.client.post(
            self.url,
            {
                "conversation_id": None,
                "message": "Hi",
            },
            content_type="application/json",
            HTTP_AUTHORIZATION=self._auth(self.alice),
        )
        body = self._consume_stream(resp)
        lines = [l for l in body.split("\n") if l.startswith("data: ")]
        self.assertGreater(len(lines), 2)
        first = json.loads(lines[0][6:])
        self.assertIn("conversation_id", first)
        self.assertIsInstance(first["conversation_id"], str)
        for line in lines[1:-1]:
            self.assertTrue(line.startswith("data: "))
            payload = json.loads(line[6:])
            self.assertIn("text", payload)
        self.assertEqual(lines[-1], "data: [DONE]")

    # ── ownership scoping ────────────────────────────────────────

    def test_other_users_conversation_returns_404(self):
        conv = Conversation.objects.create(owner=self.bob, title="Bob secret")
        resp = self.client.post(
            self.url,
            {
                "conversation_id": conv.id,
                "message": "Hello",
            },
            content_type="application/json",
            HTTP_AUTHORIZATION=self._auth(self.alice),
        )
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    # ── partial replies / completion flag ────────────────────────

    def test_assistant_message_starts_incomplete_and_flips_complete(self):
        resp = self.client.post(
            self.url,
            {
                "conversation_id": None,
                "message": "Hi",
            },
            content_type="application/json",
            HTTP_AUTHORIZATION=self._auth(self.alice),
        )
        assistant = Message.objects.get(
            conversation__owner=self.alice, role="assistant"
        )
        self.assertFalse(assistant.complete)

        self._consume_stream(resp)

        assistant.refresh_from_db()
        self.assertTrue(assistant.complete)
        self.assertEqual(assistant.content, "".join(CHUNKS))

    def test_interrupted_stream_persists_partial_reply(self):
        def interrupted():
            yield "first half "
            yield "second half"
            raise ModelNotAvailableError("down")

        self.mock_stream.return_value = interrupted()

        resp = self.client.post(
            self.url,
            {
                "conversation_id": None,
                "message": "Hi",
            },
            content_type="application/json",
            HTTP_AUTHORIZATION=self._auth(self.alice),
        )
        body = self._consume_stream(resp)

        self.assertIn('"error"', body)
        self.assertIn("data: [DONE]", body)

        assistant = Message.objects.get(
            conversation__owner=self.alice, role="assistant"
        )
        self.assertEqual(assistant.content, "first half second half")
        self.assertFalse(assistant.complete)


class ContinueAPITests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.alice = CustomUser.objects.create_user("alice@test.com", "pass1234")
        cls.bob = CustomUser.objects.create_user("bob@test.com", "pass1234")

    def setUp(self):
        self.url = reverse("chat-continue")
        self.stream_patcher = patch("assistant.views.stream_reply")
        self.mock_stream = self.stream_patcher.start()
        self.mock_stream.return_value = iter(CHUNKS)

    def tearDown(self):
        self.stream_patcher.stop()

    def _auth(self, user):
        from rest_framework_simplejwt.tokens import RefreshToken

        refresh = RefreshToken.for_user(user)
        return f"Bearer {refresh.access_token}"

    def _consume_stream(self, resp):
        return b"".join(resp.streaming_content).decode()

    def _conv_with_partial(self, owner, partial="partial reply "):
        conv = Conversation.objects.create(owner=owner, title="Partial")
        Message.objects.create(
            conversation=conv, role="user", content="original question"
        )
        Message.objects.create(
            conversation=conv,
            role="assistant",
            content=partial,
            complete=False,
        )
        return conv

    # ── guards ───────────────────────────────────────────────────

    def test_unauthenticated_returns_401(self):
        resp = self.client.post(
            self.url,
            {"conversation_id": None},
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_missing_conversation_id_returns_400(self):
        resp = self.client.post(
            self.url,
            {},
            content_type="application/json",
            HTTP_AUTHORIZATION=self._auth(self.alice),
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_other_users_conversation_returns_404(self):
        conv = self._conv_with_partial(self.bob)
        resp = self.client.post(
            self.url,
            {"conversation_id": conv.id},
            content_type="application/json",
            HTTP_AUTHORIZATION=self._auth(self.alice),
        )
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_complete_last_message_returns_400(self):
        conv = self._conv_with_partial(self.alice)
        conv.messages.filter(role="assistant").update(complete=True)
        resp = self.client.post(
            self.url,
            {"conversation_id": conv.id},
            content_type="application/json",
            HTTP_AUTHORIZATION=self._auth(self.alice),
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_no_messages_returns_400(self):
        conv = Conversation.objects.create(owner=self.alice, title="Empty")
        resp = self.client.post(
            self.url,
            {"conversation_id": conv.id},
            content_type="application/json",
            HTTP_AUTHORIZATION=self._auth(self.alice),
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    # ── continue ─────────────────────────────────────────────────

    def test_continue_appends_and_marks_complete(self):
        conv = self._conv_with_partial(self.alice)
        resp = self.client.post(
            self.url,
            {"conversation_id": conv.id},
            content_type="application/json",
            HTTP_AUTHORIZATION=self._auth(self.alice),
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        body = self._consume_stream(resp)
        self.assertIn("data: [DONE]", body)

        assistant = conv.messages.filter(role="assistant").last()
        self.assertEqual(assistant.content, "partial reply " + "".join(CHUNKS))
        self.assertTrue(assistant.complete)

    def test_continue_appends_continue_instruction_to_prompt(self):
        conv = self._conv_with_partial(self.alice)
        resp = self.client.post(
            self.url,
            {"conversation_id": conv.id},
            content_type="application/json",
            HTTP_AUTHORIZATION=self._auth(self.alice),
        )
        self._consume_stream(resp)

        prompt = self.mock_stream.call_args.args[0]
        self.assertEqual(prompt[-1]["role"], "user")
        self.assertIn("continue", prompt[-1]["content"].lower())
        self.assertEqual(prompt[-2]["content"], "partial reply ")

    def test_continue_does_not_create_new_messages(self):
        conv = self._conv_with_partial(self.alice)
        resp = self.client.post(
            self.url,
            {"conversation_id": conv.id},
            content_type="application/json",
            HTTP_AUTHORIZATION=self._auth(self.alice),
        )
        self._consume_stream(resp)
        self.assertEqual(conv.messages.count(), 2)
