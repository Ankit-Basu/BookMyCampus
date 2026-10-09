from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from .models import Department, User


class DepartmentSerializer(serializers.ModelSerializer):
    head_name = serializers.CharField(source="head.get_full_name", read_only=True, default=None)

    class Meta:
        model = Department
        fields = ["id", "code", "name", "head", "head_name"]


class UserSerializer(serializers.ModelSerializer):
    name = serializers.SerializerMethodField()
    role_label = serializers.CharField(source="get_role_display", read_only=True)
    department_code = serializers.CharField(source="department.code", read_only=True, default=None)
    is_restricted = serializers.BooleanField(read_only=True)
    is_manager = serializers.BooleanField(read_only=True)
    can_book_recurring = serializers.BooleanField(read_only=True)
    custodian_of = serializers.SerializerMethodField()
    noshow_count = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id", "username", "name", "first_name", "last_name", "email", "phone", "role", "role_label",
            "department", "department_code", "is_restricted", "restricted_until", "restriction_reason",
            "is_manager", "can_book_recurring", "calendar_token", "custodian_of", "noshow_count",
        ]
        read_only_fields = ["username", "role", "calendar_token", "restricted_until", "restriction_reason"]

    def get_name(self, obj):
        return obj.get_full_name() or obj.username

    def get_custodian_of(self, obj):
        return list(obj.custodied.values_list("id", flat=True))

    def get_noshow_count(self, obj):
        from datetime import timedelta

        from django.utils import timezone

        return obj.noshows.filter(waived=False, recorded_at__gte=timezone.now() - timedelta(days=30)).count()


class UserMiniSerializer(serializers.ModelSerializer):
    name = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ["id", "name", "role", "department"]

    def get_name(self, obj):
        return obj.get_full_name() or obj.username


class LoginSerializer(TokenObtainPairSerializer):
    def validate(self, attrs):
        data = super().validate(attrs)
        data["user"] = UserSerializer(self.user).data
        return data
