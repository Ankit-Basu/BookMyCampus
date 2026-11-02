import uuid

from django.conf import settings
from django.contrib.postgres.fields import ArrayField
from django.db import models
from django.utils.text import slugify


class Location(models.Model):
    campus = models.CharField(max_length=80, default="Main Campus")
    building = models.CharField(max_length=120)
    floor = models.CharField(max_length=20, blank=True)
    room = models.CharField(max_length=40, blank=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)

    class Meta:
        ordering = ["building", "floor", "room"]

    def __str__(self):
        parts = [self.building, f"Floor {self.floor}" if self.floor else "", self.room]
        return " · ".join(p for p in parts if p)


class ResourceType(models.Model):
    name = models.CharField(max_length=80, unique=True)
    slug = models.SlugField(max_length=80, unique=True, blank=True)
    description = models.TextField(blank=True)
    icon = models.CharField(max_length=40, default="cube", help_text="Icon key used by the frontend")
    color = models.CharField(max_length=9, default="#F5B544")
    # Which roles may book resources of this type at all. Empty = everyone.
    allowed_roles = ArrayField(models.CharField(max_length=24), default=list, blank=True)
    requires_checkin = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class Resource(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        DOWN = "down", "Out of service"
        RETIRED = "retired", "Retired"

    saved_by = models.ManyToManyField(settings.AUTH_USER_MODEL, blank=True, related_name="saved_resources")
    type = models.ForeignKey(ResourceType, on_delete=models.PROTECT, related_name="resources")
    code = models.CharField(max_length=32, unique=True)
    name = models.CharField(max_length=160)
    description = models.TextField(blank=True)
    department = models.ForeignKey(
        "accounts.Department", null=True, blank=True, on_delete=models.SET_NULL, related_name="resources"
    )
    location = models.ForeignKey(Location, null=True, blank=True, on_delete=models.SET_NULL, related_name="resources")
    capacity = models.PositiveIntegerField(default=1)
    features = ArrayField(models.CharField(max_length=60), default=list, blank=True)
    image = models.ImageField(upload_to="resources/", null=True, blank=True)
    image_url = models.URLField(blank=True, max_length=500)
    # Replacement value — used by the idle-capacity report to surface expensive, unused assets.
    value_inr = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.ACTIVE)
    # Printed on the QR poster at the resource; scanning it proves physical presence at check-in.
    checkin_token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    custodians = models.ManyToManyField(settings.AUTH_USER_MODEL, through="Custodian", related_name="custodied")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["type__name", "name"]

    def __str__(self):
        return f"{self.code} — {self.name}"

    @property
    def cover(self):
        if self.image:
            return self.image.url
        first = self.images.first()
        if first:
            return first.src
        return self.image_url


class ResourceImage(models.Model):
    resource = models.ForeignKey(Resource, on_delete=models.CASCADE, related_name="images")
    image = models.ImageField(upload_to="resources/", null=True, blank=True)
    url = models.URLField(blank=True, max_length=500)
    caption = models.CharField(max_length=120, blank=True)
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["order", "id"]

    @property
    def src(self):
        return self.image.url if self.image else self.url


class ResourceAttribute(models.Model):
    """Free-form typed attributes — e.g. 'Magnification: 1000x' for a microscope."""

    resource = models.ForeignKey(Resource, on_delete=models.CASCADE, related_name="attributes")
    key = models.CharField(max_length=60)
    value = models.CharField(max_length=200)

    class Meta:
        unique_together = [("resource", "key")]
        ordering = ["key"]


class Custodian(models.Model):
    resource = models.ForeignKey(Resource, on_delete=models.CASCADE)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    is_primary = models.BooleanField(default=False)

    class Meta:
        unique_together = [("resource", "user")]
