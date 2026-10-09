from rest_framework import serializers


class RangeBoundsMixin(serializers.Serializer):
    """Expose a DateTimeRangeField `period` as flat `start` / `end` fields."""

    start = serializers.SerializerMethodField()
    end = serializers.SerializerMethodField()

    def get_start(self, obj):
        return obj.period.lower.isoformat() if obj.period else None

    def get_end(self, obj):
        return obj.period.upper.isoformat() if obj.period else None
