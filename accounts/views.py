import requests
from urllib.parse import urlencode

from django.conf import settings
from django.contrib.auth import authenticate
from django.shortcuts import redirect
from django.urls import reverse
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken, TokenError
from allauth.socialaccount.models import SocialAccount

from .models import CustomUser
from .serializers import (
    LoginSerializer,
    LogoutSerializer,
    SignupSerializer,
    UserSerializer,
)


class SignupView(APIView):
    permission_classes = (AllowAny,)

    def post(self, request):
        serializer = SignupSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        user = serializer.save()
        refresh = RefreshToken.for_user(user)
        return Response(
            {
                "user": UserSerializer(user).data,
                "access": str(refresh.access_token),
                "refresh": str(refresh),
            },
            status=status.HTTP_201_CREATED,
        )


class LoginView(APIView):
    permission_classes = (AllowAny,)

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        email = serializer.validated_data["email"].lower().strip()
        password = serializer.validated_data["password"]

        user = authenticate(request=request, email=email, password=password)
        if user is None:
            return Response(
                {"email": "That email or password isn't right"},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        refresh = RefreshToken.for_user(user)
        return Response(
            {
                "user": UserSerializer(user).data,
                "access": str(refresh.access_token),
                "refresh": str(refresh),
            }
        )


class LogoutView(APIView):
    permission_classes = (IsAuthenticated,)

    def post(self, request):
        serializer = LogoutSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        try:
            token = RefreshToken(serializer.validated_data["refresh"])
            token.blacklist()
            return Response(status=status.HTTP_204_NO_CONTENT)
        except TokenError:
            return Response(
                {"refresh": "Invalid or expired refresh token"},
                status=status.HTTP_400_BAD_REQUEST,
            )


class SessionView(APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request):
        return Response(UserSerializer(request.user).data)


class GitHubRedirectView(APIView):
    permission_classes = (AllowAny,)

    def get(self, request):
        callback_url = request.build_absolute_uri(
            reverse("oauth-github-callback")
        )
        params = {
            "client_id": settings.GITHUB_CLIENT_ID,
            "redirect_uri": callback_url,
            "scope": "user:email",
            "response_type": "code",
        }
        auth_url = (
            f"https://github.com/login/oauth/authorize?{urlencode(params)}"
        )
        return Response({"authorization_url": auth_url})


class GitHubCallbackView(APIView):
    permission_classes = (AllowAny,)

    def get(self, request):
        code = request.query_params.get("code")
        error_param = request.query_params.get("error")

        if error_param:
            return redirect(
                f"{settings.FRONTEND_URL}/callback?error=OAuth+authorization+failed"
            )

        if not code:
            return redirect(
                f"{settings.FRONTEND_URL}/callback?error=Authorization+code+is+required"
            )

        callback_url = request.build_absolute_uri(
            reverse("oauth-github-callback")
        )

        resp = requests.post(
            "https://github.com/login/oauth/access_token",
            data={
                "client_id": settings.GITHUB_CLIENT_ID,
                "client_secret": settings.GITHUB_CLIENT_SECRET,
                "code": code,
                "redirect_uri": callback_url,
            },
            headers={"Accept": "application/json"},
        )
        token_data = resp.json()

        if "access_token" not in token_data:
            return redirect(
                f"{settings.FRONTEND_URL}/callback?error=Failed+to+exchange+authorization+code"
            )

        access_token = token_data["access_token"]
        headers = {
            "Authorization": f"token {access_token}",
            "Accept": "application/json",
        }

        user_resp = requests.get(
            "https://api.github.com/user", headers=headers
        )
        user_data = user_resp.json()

        email = user_data.get("email")
        if not email:
            emails_resp = requests.get(
                "https://api.github.com/user/emails", headers=headers
            )
            emails = emails_resp.json()
            primary = next(
                (e for e in emails if e.get("primary")), {}
            )
            email = primary.get("email")

        if not email:
            return redirect(
                f"{settings.FRONTEND_URL}/callback?error=Could+not+retrieve+email+from+GitHub"
            )

        github_uid = str(user_data["id"])
        social_account = SocialAccount.objects.filter(
            provider="github", uid=github_uid
        ).first()

        if social_account:
            user = social_account.user
        else:
            user = CustomUser.objects.filter(email=email).first()
            if not user:
                user = CustomUser.objects.create_user(
                    email=email, password=None
                )
                user.set_unusable_password()
                user.save()

            SocialAccount.objects.create(
                user=user,
                provider="github",
                uid=github_uid,
                extra_data=user_data,
            )

        refresh = RefreshToken.for_user(user)
        return redirect(
            f"{settings.FRONTEND_URL}/callback?"
            f"access={refresh.access_token}&refresh={refresh}"
        )


class GoogleRedirectView(APIView):
    permission_classes = (AllowAny,)

    def get(self, request):
        callback_url = request.build_absolute_uri(
            reverse("oauth-google-callback")
        )
        params = {
            "client_id": settings.GOOGLE_CLIENT_ID,
            "redirect_uri": callback_url,
            "scope": "email profile",
            "response_type": "code",
        }
        auth_url = "https://accounts.google.com/o/oauth2/v2/auth?{}".format(urlencode(params))
        return Response({"authorization_url": auth_url})


class GoogleCallbackView(APIView):
    permission_classes = (AllowAny,)

    def get(self, request):
        code = request.query_params.get("code")
        error_param = request.query_params.get("error")

        if error_param:
            return redirect(
                f"{settings.FRONTEND_URL}/callback?error=OAuth+authorization+failed"
            )

        if not code:
            return redirect(
                f"{settings.FRONTEND_URL}/callback?error=Authorization+code+is+required"
            )

        callback_url = request.build_absolute_uri(
            reverse("oauth-google-callback")
        )

        resp = requests.post(
            "https://oauth2.googleapis.com/token",
            data={
                "client_id": settings.GOOGLE_CLIENT_ID,
                "client_secret": settings.GOOGLE_CLIENT_SECRET,
                "code": code,
                "redirect_uri": callback_url,
                "grant_type": "authorization_code",
            },
            headers={"Accept": "application/json"},
        )
        token_data = resp.json()

        if "access_token" not in token_data:
            return redirect(
                f"{settings.FRONTEND_URL}/callback?error=Failed+to+exchange+authorization+code"
            )

        access_token = token_data["access_token"]
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
        }

        user_resp = requests.get(
            "https://www.googleapis.com/oauth2/v2/userinfo",
            headers=headers,
        )
        user_data = user_resp.json()

        email = user_data.get("email")
        if not email:
            return redirect(
                f"{settings.FRONTEND_URL}/callback?error=Could+not+retrieve+email+from+Google"
            )

        google_uid = str(user_data.get("id") or user_data.get("sub", email))
        social_account = SocialAccount.objects.filter(
            provider="google", uid=google_uid
        ).first()

        if social_account:
            user = social_account.user
        else:
            user = CustomUser.objects.filter(email=email).first()
            if not user:
                user = CustomUser.objects.create_user(
                    email=email, password=None
                )
                user.set_unusable_password()
                user.save()

            SocialAccount.objects.create(
                user=user,
                provider="google",
                uid=google_uid,
                extra_data=user_data,
            )

        refresh = RefreshToken.for_user(user)
        return redirect(
            f"{settings.FRONTEND_URL}/callback?"
            f"access={refresh.access_token}&refresh={refresh}"
        )
