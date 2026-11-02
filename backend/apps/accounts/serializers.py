from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from .models import Department, Role, User


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

    def validate_email(self, value):
        if value and User.objects.filter(email__iexact=value).exclude(pk=getattr(self.instance, "pk", None)).exists():
            raise serializers.ValidationError("This email already has an account.")
        return value

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


class RegisterSerializer(serializers.Serializer):
    """Public sign-up. Always creates a student: the role is never taken from the request."""

    registration_no = serializers.RegexField(
        r"^[0-9]{8}$", error_messages={"invalid": "Enter your 8-digit registration number."}
    )
    first_name = serializers.CharField(max_length=150)
    last_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    email = serializers.EmailField()
    department = serializers.PrimaryKeyRelatedField(queryset=Department.objects.all(), required=False, allow_null=True)
    password = serializers.CharField(write_only=True, trim_whitespace=False)

    def validate_registration_no(self, value):
        if User.objects.filter(username=value).exists():
            raise serializers.ValidationError("This registration number already has an account. Sign in instead.")
        return value

    def validate_email(self, value):
        value = value.lower()
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("This email already has an account.")
        return value

    def validate(self, attrs):
        if attrs["password"] == attrs["registration_no"]:
            raise serializers.ValidationError({"password": "Your password can't be your registration number."})
        try:
            validate_password(attrs["password"])
        except DjangoValidationError as e:
            raise serializers.ValidationError({"password": list(e.messages)})
        return attrs

    def create(self, validated):
        try:
            return User.objects.create_user(
                username=validated["registration_no"],
                password=validated["password"],
                email=validated["email"],
                first_name=validated["first_name"],
                last_name=validated.get("last_name", ""),
                department=validated.get("department"),
                role=Role.STUDENT,
            )
        except IntegrityError:
            # two sign-ups for one number at the same instant: the database keeps exactly one
            raise serializers.ValidationError(
                {"registration_no": "This registration number already has an account. Sign in instead."}
            )

    def to_representation(self, user):
        return {"username": user.username, "name": user.get_full_name()}


class ChangePasswordSerializer(serializers.Serializer):
    current_password = serializers.CharField(trim_whitespace=False)
    new_password = serializers.CharField(trim_whitespace=False)

    def validate_current_password(self, value):
        if not self.context["request"].user.check_password(value):
            raise serializers.ValidationError("That isn't your current password.")
        return value

    def validate_new_password(self, value):
        user = self.context["request"].user
        if value == user.username:
            raise serializers.ValidationError("Your password can't be your registration number.")
        try:
            validate_password(value, user)
        except DjangoValidationError as e:
            raise serializers.ValidationError(list(e.messages))
        return value


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
