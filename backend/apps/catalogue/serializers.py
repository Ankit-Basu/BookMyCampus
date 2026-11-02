from rest_framework import serializers

from apps.accounts.serializers import UserMiniSerializer

from .models import Custodian, Location, Resource, ResourceAttribute, ResourceImage, ResourceType


class LocationSerializer(serializers.ModelSerializer):
    label = serializers.CharField(source="__str__", read_only=True)

    class Meta:
        model = Location
        fields = ["id", "campus", "building", "floor", "room", "latitude", "longitude", "label"]


class ResourceTypeSerializer(serializers.ModelSerializer):
    resource_count = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = ResourceType
        fields = ["id", "name", "slug", "description", "icon", "color", "allowed_roles", "requires_checkin", "resource_count"]
        read_only_fields = ["slug"]


class ResourceImageSerializer(serializers.ModelSerializer):
    src = serializers.CharField(read_only=True)

    class Meta:
        model = ResourceImage
        fields = ["id", "src", "url", "image", "caption", "order"]


class ResourceAttributeSerializer(serializers.ModelSerializer):
    class Meta:
        model = ResourceAttribute
        fields = ["key", "value"]


class ResourceListSerializer(serializers.ModelSerializer):
    type_name = serializers.CharField(source="type.name", read_only=True)
    type_slug = serializers.CharField(source="type.slug", read_only=True)
    type_color = serializers.CharField(source="type.color", read_only=True)
    type_icon = serializers.CharField(source="type.icon", read_only=True)
    department_code = serializers.CharField(source="department.code", read_only=True, default=None)
    location_label = serializers.CharField(source="location.__str__", read_only=True, default=None)
    building = serializers.CharField(source="location.building", read_only=True, default=None)
    cover = serializers.CharField(read_only=True)
    requires_approval = serializers.SerializerMethodField()
    is_saved = serializers.SerializerMethodField()

    class Meta:
        model = Resource
        fields = [
            "id", "code", "name", "description", "type", "type_name", "type_slug", "type_color", "type_icon",
            "department", "department_code", "location", "location_label", "building", "capacity", "features",
            "cover", "value_inr", "status", "requires_approval", "is_saved",
        ]

    def get_is_saved(self, obj):
        return obj.id in self.context.get("saved_ids", ())

    def get_requires_approval(self, obj):
        wf_types = self.context.get("wf_types")
        if wf_types is None:
            from apps.approvals.services import resolve_workflow

            request = self.context.get("request")
            return bool(request and resolve_workflow(obj, request.user))
        return obj.type_id in wf_types


class ResourceDetailSerializer(ResourceListSerializer):
    images = ResourceImageSerializer(many=True, read_only=True)
    attributes = ResourceAttributeSerializer(many=True, required=False)
    custodian_list = serializers.SerializerMethodField()
    location_detail = LocationSerializer(source="location", read_only=True)
    allowed_roles = serializers.ListField(source="type.allowed_roles", read_only=True)
    requires_checkin = serializers.BooleanField(source="type.requires_checkin", read_only=True)
    custodian_ids = serializers.ListField(child=serializers.IntegerField(), write_only=True, required=False)

    class Meta(ResourceListSerializer.Meta):
        fields = ResourceListSerializer.Meta.fields + [
            "images", "attributes", "custodian_list", "location_detail", "allowed_roles", "requires_checkin",
            "image", "image_url", "custodian_ids",
        ]

    def get_custodian_list(self, obj):
        users = [c.user for c in Custodian.objects.filter(resource=obj).select_related("user")]
        return UserMiniSerializer(users, many=True).data

    def _save_nested(self, resource, attrs, custodian_ids):
        if attrs is not None:
            resource.attributes.all().delete()
            ResourceAttribute.objects.bulk_create([ResourceAttribute(resource=resource, **a) for a in attrs])
        if custodian_ids is not None:
            Custodian.objects.filter(resource=resource).delete()
            Custodian.objects.bulk_create(
                [Custodian(resource=resource, user_id=u, is_primary=i == 0) for i, u in enumerate(custodian_ids)]
            )

    def create(self, validated):
        attrs = validated.pop("attributes", None)
        cids = validated.pop("custodian_ids", None)
        r = super().create(validated)
        self._save_nested(r, attrs, cids)
        return r

    def update(self, instance, validated):
        attrs = validated.pop("attributes", None)
        cids = validated.pop("custodian_ids", None)
        r = super().update(instance, validated)
        self._save_nested(r, attrs, cids)
        return r
