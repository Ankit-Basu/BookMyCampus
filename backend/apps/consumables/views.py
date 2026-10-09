from django.db.models import F, Q
from django.shortcuts import get_object_or_404
from rest_framework import mixins, serializers, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.accounts.permissions import IsManager, ReadOnlyOrManager
from apps.bookings.models import Booking

from .models import Consumable, Issuance
from .services import issue, return_issuance


class ConsumableSerializer(serializers.ModelSerializer):
    is_low = serializers.BooleanField(read_only=True)
    resource_name = serializers.CharField(source="resource.name", read_only=True, default=None)
    resource_type_name = serializers.CharField(source="resource_type.name", read_only=True, default=None)
    issued_out = serializers.SerializerMethodField()

    class Meta:
        model = Consumable
        fields = [
            "id", "name", "sku", "kind", "resource_type", "resource_type_name", "resource", "resource_name", "unit",
            "stock", "reorder_level", "unit_cost", "is_low", "issued_out",
        ]

    def get_issued_out(self, obj):
        return sum(i.quantity for i in obj.issuances.all() if i.status == "issued")


class IssuanceSerializer(serializers.ModelSerializer):
    consumable_name = serializers.CharField(source="consumable.name", read_only=True)
    consumable_kind = serializers.CharField(source="consumable.kind", read_only=True)
    unit = serializers.CharField(source="consumable.unit", read_only=True)
    user_name = serializers.CharField(source="user.get_full_name", read_only=True)
    booking_reference = serializers.CharField(source="booking.reference", read_only=True, default=None)

    class Meta:
        model = Issuance
        fields = [
            "id", "consumable", "consumable_name", "consumable_kind", "unit", "booking", "booking_reference", "user",
            "user_name", "quantity", "returned_quantity", "status", "issued_at", "returned_at",
        ]
        read_only_fields = ["user", "returned_quantity", "status", "issued_at", "returned_at"]


class ConsumableViewSet(viewsets.ModelViewSet):
    serializer_class = ConsumableSerializer
    permission_classes = [ReadOnlyOrManager]
    search_fields = ["name", "sku"]
    filterset_fields = ["kind", "resource", "resource_type"]

    def get_queryset(self):
        qs = Consumable.objects.select_related("resource", "resource_type").prefetch_related("issuances")
        p = self.request.query_params
        if p.get("low") == "1":
            qs = qs.filter(stock__lte=F("reorder_level"))
        if rid := p.get("for_resource"):
            from apps.catalogue.models import Resource

            r = get_object_or_404(Resource, pk=rid)
            qs = qs.filter(Q(resource=r) | Q(resource_type_id=r.type_id, resource__isnull=True))
        return qs

    @action(detail=True, methods=["post"], permission_classes=[IsManager])
    def restock(self, request, pk=None):
        qty = int(request.data.get("quantity", 0))
        Consumable.objects.filter(pk=pk).update(stock=F("stock") + max(qty, 0))
        return Response(ConsumableSerializer(self.get_queryset().get(pk=pk)).data)


class IssuanceViewSet(mixins.ListModelMixin, mixins.CreateModelMixin, viewsets.GenericViewSet):
    serializer_class = IssuanceSerializer

    def get_queryset(self):
        qs = Issuance.objects.select_related("consumable", "user", "booking")
        u = self.request.user
        if not u.is_manager:
            qs = qs.filter(user=u)
        if b := self.request.query_params.get("booking"):
            qs = qs.filter(booking_id=b)
        if self.request.query_params.get("open") == "1":
            qs = qs.filter(status="issued")
        return qs

    def create(self, request):
        booking = None
        if bid := request.data.get("booking"):
            booking = get_object_or_404(Booking, pk=bid)
            if booking.user_id != request.user.pk and not request.user.is_manager:
                return Response({"error": "forbidden", "message": "Not your booking."}, status=403)
        user = booking.user if booking else request.user
        iss = issue(int(request.data["consumable"]), int(request.data.get("quantity", 1)), user, booking)
        return Response(IssuanceSerializer(iss).data, status=201)

    @action(detail=True, methods=["post"], url_path="return", permission_classes=[IsManager])
    def do_return(self, request, pk=None):
        iss = get_object_or_404(Issuance.objects.select_related("consumable"), pk=pk)
        return Response(IssuanceSerializer(return_issuance(iss, request.data.get("quantity"))).data)
