from django.contrib import admin

from .models import Booking, BookingSlot, BookingAttempt, RecurrenceRule, CheckIn, NoShow

for m in (Booking, BookingSlot, BookingAttempt, RecurrenceRule, CheckIn, NoShow,):
    admin.site.register(m)
