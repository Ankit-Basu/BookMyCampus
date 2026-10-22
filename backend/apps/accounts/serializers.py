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


class AdminUserSerializer(serializers.ModelSerializer):
    """What a facility manager / admin may change from the People directory."""

    name = serializers.SerializerMethodField()
    department_code = serializers.CharField(source="department.code", read_only=True, default=None)
    role_label = serializers.CharField(source="get_role_display", read_only=True)
    booking_count = serializers.IntegerField(read_only=True, default=0)
    noshows_30d = serializers.IntegerField(read_only=True, default=0)
    is_restricted = serializers.BooleanField(read_only=True)
    password = serializers.CharField(write_only=True, required=False, allow_blank=True)

    class Meta:
        model = User
        fields = [
            "id", "username", "name", "first_name", "last_name", "email", "phone", "role", "role_label",
            "department", "department_code", "is_active", "is_restricted", "restricted_until", "restriction_reason",
            "booking_count", "noshows_30d", "last_login", "date_joined", "password",
        ]
        read_only_fields = ["restricted_until", "restriction_reason", "last_login", "date_joined"]

    def get_name(self, obj):
        return obj.get_full_name() or obj.username

    def validate(self, attrs):
        me = self.context["request"].user
        if self.instance is not None and self.instance.pk == me.pk:
            if attrs.get("is_active") is False:
                raise serializers.ValidationError("You can't deactivate your own account.")
            if "role" in attrs and attrs["role"] != me.role:
                raise serializers.ValidationError("Ask another administrator to change your own role.")
        if self.instance is None and not attrs.get("username"):
            raise serializers.ValidationError("UMS ID (username) is required.")
        return attrs

    def create(self, validated):
        password = validated.pop("password", "") or None
        user = User(**validated)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save()
        return user

    def update(self, instance, validated):
        password = validated.pop("password", "")
        user = super().update(instance, validated)
        if password:
            user.set_password(password)
            user.save(update_fields=["password"])
        return user
