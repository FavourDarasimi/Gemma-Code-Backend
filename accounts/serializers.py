from django.contrib.auth import authenticate
from rest_framework import serializers
from rest_framework_simplejwt.tokens import RefreshToken, TokenError

from .models import CustomUser


class SignupSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)

    class Meta:
        model = CustomUser
        fields = ("email", "password")

    def validate_email(self, value):
        normalized = value.lower().strip()
        if CustomUser.objects.filter(email__iexact=normalized).exists():
            raise serializers.ValidationError(
                "An account with this email already exists"
            )
        return normalized

    def create(self, validated_data):
        return CustomUser.objects.create_user(
            email=validated_data["email"],
            password=validated_data["password"],
        )


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField()


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomUser
        fields = ("id", "email", "is_staff", "date_joined")


class LogoutSerializer(serializers.Serializer):
    refresh = serializers.CharField()

    def validate_refresh(self, value):
        try:
            token = RefreshToken(value)
        except TokenError:
            raise serializers.ValidationError("Invalid or expired refresh token")
        return value
