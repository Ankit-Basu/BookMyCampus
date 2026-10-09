from rest_framework import serializers

from apps.approvals.models import Approval
from apps.common.fields import RangeBoundsMixin

from .models import Booking, CheckIn, NoShow, RecurrenceRule


class ApprovalSerializer(serializers.ModelSerializer):
    decided_by_name = serializers.CharField(source="decided_by.get_full_name", read_only=True, default=None)

    class Meta:
        model = Approval
        fields = ["id", "order", "step_name", "approver_role", "status", "decided_by_name", "decided_at", "activated_at", "comment"]


class CheckInSerializer(serializers.ModelSerializer):
    class Meta:
        model = CheckIn
        fields = ["checked_in_at", "method", "checked_out_at", "condition_note"]


class BookingSerializer(RangeBoundsMixin, serializers.ModelSerializer):
    resource_name = serializers.CharField(source="resource.name", read_only=True)
    resource_code = serializers.CharField(source="resource.code", read_only=True)
    resource_cover = serializers.CharField(source="resource.cover", read_only=True)
    resource_type = serializers.CharField(source="resource.type.name", read_only=True)
    resource_color = serializers.CharField(source="resource.type.color", read_only=True)
    requires_checkin = serializers.BooleanField(source="resource.type.requires_checkin", read_only=True)
    location = serializers.CharField(source="resource.location.__str__", read_only=True, default=None)
    user_name = serializers.SerializerMethodField()
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    approvals = ApprovalSerializer(many=True, read_only=True)
    checkin = CheckInSerializer(read_only=True)
    series_size = serializers.SerializerMethodField()

    class Meta:
        model = Booking
        fields = [
            "id", "reference", "resource", "resource_name", "resource_code", "resource_cover", "resource_type",
            "resource_color", "requires_checkin", "location", "user", "user_name", "title", "purpose", "on_behalf_of",
            "attendees", "start", "end", "status", "status_label", "status_note", "recurrence", "occurrence_index",
            "series_size", "created_at", "decided_at", "approvals", "checkin",
        ]

    def get_user_name(self, obj):
        return obj.user.get_full_name() or obj.user.username

    def get_series_size(self, obj):
        return obj.recurrence.requested_occurrences if obj.recurrence_id else None


class BookingDetailSerializer(BookingSerializer):
    qr_token = serializers.UUIDField(read_only=True)

    class Meta(BookingSerializer.Meta):
        fields = BookingSerializer.Meta.fields + ["qr_token"]


class RecurrenceInput(serializers.Serializer):
    freq = serializers.ChoiceField(choices=RecurrenceRule.Freq.choices, default="weekly")
    interval = serializers.IntegerField(min_value=1, max_value=4, default=1)
    weekdays = serializers.ListField(child=serializers.IntegerField(min_value=0, max_value=6), required=False)
    until = serializers.DateField(required=False, allow_null=True)
    count = serializers.IntegerField(min_value=1, max_value=52, required=False, allow_null=True)
    conflict_policy = serializers.ChoiceField(choices=RecurrenceRule.ConflictPolicy.choices, default="skip")

    def validate(self, attrs):
        if not attrs.get("until") and not attrs.get("count"):
            raise serializers.ValidationError("Give an end date or a number of occurrences.")
        return attrs


class BookingCreateSerializer(serializers.Serializer):
    resource = serializers.IntegerField()
    start = serializers.DateTimeField()
    end = serializers.DateTimeField()
    title = serializers.CharField(max_length=160)
    purpose = serializers.CharField(required=False, allow_blank=True, default="")
    on_behalf_of = serializers.CharField(required=False, allow_blank=True, default="")
    attendees = serializers.IntegerField(min_value=1, default=1)
    recurrence = RecurrenceInput(required=False, allow_null=True)
    accessories = serializers.ListField(child=serializers.DictField(), required=False)


class NoShowSerializer(serializers.ModelSerializer):
    user_name = serializers.SerializerMethodField()
    resource_name = serializers.CharField(source="resource.name", read_only=True)
    booking_reference = serializers.CharField(source="booking.reference", read_only=True)
    booking_start = serializers.SerializerMethodField()
    user_restricted_until = serializers.DateTimeField(source="user.restricted_until", read_only=True)

    class Meta:
        model = NoShow
        fields = [
            "id", "user", "user_name", "resource", "resource_name", "booking", "booking_reference", "booking_start",
            "recorded_at", "waived", "waived_reason", "user_restricted_until",
        ]

    def get_user_name(self, obj):
        return obj.user.get_full_name() or obj.user.username

    def get_booking_start(self, obj):
        return obj.booking.period.lower.isoformat()
