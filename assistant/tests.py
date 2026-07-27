from django.test import TestCase
from django.urls import reverse
from rest_framework import status

from accounts.models import CustomUser
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
        resp = self.client.get(reverse("conversation-detail", args=[1]))
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_unauthenticated_patch_returns_401(self):
        resp = self.client.patch(reverse("conversation-detail", args=[1]))
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_unauthenticated_delete_returns_401(self):
        resp = self.client.delete(reverse("conversation-detail", args=[1]))
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
