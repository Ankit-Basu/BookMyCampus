from django.conf import settings
from django.db import models


class Consumable(models.Model):
    class Kind(models.TextChoices):
        CONSUMABLE = "consumable", "Consumable (used up)"
        ACCESSORY = "accessory", "Accessory (returned)"

    name = models.CharField(max_length=120)
    sku = models.CharField(max_length=32, unique=True)
    kind = models.CharField(max_length=10, choices=Kind.choices, default=Kind.CONSUMABLE)
    resource_type = models.ForeignKey(
        "catalogue.ResourceType", null=True, blank=True, on_delete=models.SET_NULL, related_name="consumables"
    )
    resource = models.ForeignKey(
        "catalogue.Resource", null=True, blank=True, on_delete=models.SET_NULL, related_name="consumables"
    )
    unit = models.CharField(max_length=20, default="pcs")
    stock = models.IntegerField(default=0)
    reorder_level = models.PositiveIntegerField(default=5)
    unit_cost = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["name"]
        constraints = [models.CheckConstraint(condition=models.Q(stock__gte=0), name="stock_non_negative")]

    @property
    def is_low(self):
        return self.stock <= self.reorder_level

    def __str__(self):
        return self.name


class Issuance(models.Model):
    class Status(models.TextChoices):
        ISSUED = "issued", "Issued"
        RETURNED = "returned", "Returned"
        CONSUMED = "consumed", "Consumed"

    consumable = models.ForeignKey(Consumable, on_delete=models.PROTECT, related_name="issuances")
    booking = models.ForeignKey("bookings.Booking", null=True, blank=True, on_delete=models.SET_NULL, related_name="issuances")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="issuances")
    quantity = models.PositiveIntegerField()
    returned_quantity = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ISSUED)
    issued_at = models.DateTimeField(auto_now_add=True)
    returned_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-issued_at"]
