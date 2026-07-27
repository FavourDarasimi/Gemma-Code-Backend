import json

from django.test import TestCase
from django.urls import reverse
from rest_framework_simplejwt.tokens import RefreshToken

from .models import CustomUser


class AuthEndpointTests(TestCase):
    def setUp(self):
        self.signup_url = reverse("auth-signup")
        self.login_url = reverse("auth-login")
        self.logout_url = reverse("auth-logout")
        self.session_url = reverse("auth-session")

    def test_signup_creates_user_and_returns_tokens(self):
        resp = self.client.post(
            self.signup_url,
            {"email": "alice@example.com", "password": "secure12345"},
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 201)
        data = resp.json()
        self.assertIn("access", data)
        self.assertIn("refresh", data)
        self.assertEqual(data["user"]["email"], "alice@example.com")
        self.assertTrue(CustomUser.objects.filter(email="alice@example.com").exists())

    def test_signup_duplicate_email_returns_error(self):
        CustomUser.objects.create_user("dup@example.com", "somepass")
        resp = self.client.post(
            self.signup_url,
            {"email": "dup@example.com", "password": "secure12345"},
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("email", resp.json())

    def test_signup_missing_fields_return_400(self):
        resp = self.client.post(
            self.signup_url,
            {"email": "missing@example.com"},
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)

    def test_login_returns_tokens(self):
        CustomUser.objects.create_user("login@example.com", "testpass123")
        resp = self.client.post(
            self.login_url,
            {"email": "login@example.com", "password": "testpass123"},
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("access", data)
        self.assertIn("refresh", data)

    def test_login_wrong_credentials(self):
        resp = self.client.post(
            self.login_url,
            {"email": "nobody@example.com", "password": "wrong"},
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 401)
        self.assertIn("email", resp.json())

    def test_session_authenticated(self):
        user = CustomUser.objects.create_user("session@example.com", "testpass")
        refresh = RefreshToken.for_user(user)
        resp = self.client.get(
            self.session_url,
            HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["email"], "session@example.com")

    def test_session_unauthenticated(self):
        resp = self.client.get(self.session_url)
        self.assertEqual(resp.status_code, 401)

    def test_logout_blacklists_token(self):
        user = CustomUser.objects.create_user("logout@example.com", "testpass")
        refresh = RefreshToken.for_user(user)
        access = str(refresh.access_token)

        resp = self.client.post(
            self.logout_url,
            {"refresh": str(refresh)},
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {access}",
        )
        self.assertEqual(resp.status_code, 204)

        resp = self.client.post(
            self.logout_url,
            {"refresh": str(refresh)},
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {access}",
        )
        self.assertEqual(resp.status_code, 400)

    def test_login_case_insensitive_email(self):
        CustomUser.objects.create_user("Case@Test.Com", "testpass123")
        resp = self.client.post(
            self.login_url,
            {"email": "case@test.com", "password": "testpass123"},
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)

    def test_signup_normalizes_email(self):
        resp = self.client.post(
            self.signup_url,
            {"email": "UPPER@EXAMPLE.COM", "password": "secure12345"},
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 201)
        self.assertTrue(
            CustomUser.objects.filter(email="upper@example.com").exists()
        )
