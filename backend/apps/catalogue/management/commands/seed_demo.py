"""
Seed a realistic campus: 7 resource types, ~30 resources with photos, rules, quotas, approval
workflows, a published timetable, consumables, maintenance, and four weeks of booking history so
every analytics view has something true to say.

    python manage.py seed_demo --reset
"""
import random
from datetime import datetime, time, timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import Department, Role, User
from apps.analytics.models import UtilisationSnapshot
from apps.approvals.models import Approval, ApprovalStep, ApprovalWorkflow
from apps.bookings.exceptions import BookingError
from apps.bookings.models import Booking, BookingAttempt, BookingSlot, CheckIn, NoShow, RecurrenceRule
from apps.bookings.services import _insert, tsrange
from apps.catalogue.models import Custodian, Location, Resource, ResourceAttribute, ResourceType
from apps.consumables.models import Consumable, Issuance
from apps.maintenance.models import MaintenanceWindow
from apps.maintenance.services import schedule as schedule_maintenance
from apps.notifications.models import Notification
from apps.rules.models import AvailabilityRule, Blackout, Policy, Quota
from apps.timetable.models import TimetableEntry, TimetableVersion
from apps.timetable.services import publish

U = "https://images.unsplash.com/photo-{}?w=1200&q=70&auto=format&fit=crop"
IMG = {
    "campus": U.format("1562774053-701939374585"),
    "classroom": U.format("1580582932707-520aed937b7b"),
    "lecture": U.format("1524178232363-1fb2b075b655"),
    "students": U.format("1571260899304-425eee4c7efc"),
    "glass": U.format("1532094349884-543bc11b234d"),
    "lab": U.format("1581093450021-4a7360e9a6b5"),
    "confocal": U.format("1576086213369-97a306d36557"),
    "pipette": U.format("1614935151651-0bea6508db6b"),
    "goggles": U.format("1581093588401-fbb62a02f120"),
    "plasma": U.format("1507413245164-6160d8298b31"),
    "robotics": U.format("1581091226825-a6a2a5aee158"),
    "pcb": U.format("1518770660439-4636190af475"),
    "arduino": U.format("1555664424-778a1e5e1b48"),
    "workbench": U.format("1581092160562-40aa08e78837"),
    "complab": U.format("1606857521015-7f9fcf423740"),
    "cowork": U.format("1559136555-9303baea8ebd"),
    "laptop": U.format("1516321318423-f06f85e504b3"),
    "camera": U.format("1502920917128-1aa500764cbd"),
    "vr": U.format("1530825894095-9c184b068fcb"),
    "auditorium": U.format("1540575467063-178a50c2df87"),
    "seminar": U.format("1505373877841-8d25f7d46678"),
    "meeting": U.format("1517048676732-d65bc937f952"),
    "boardroom": U.format("1431540015161-0bf868a2d407"),
    "openmeet": U.format("1497366811353-6870744d04b2"),
    "lounge": U.format("1586023492125-27b2c045efd7"),
    "corridor": U.format("1497366216548-37526070297c"),
    "basketball": U.format("1546519638-68e109498ffc"),
    "football": U.format("1574629810360-7efbbe195018"),
    "badminton": U.format("1626224583764-f87db24ac4ea"),
    "gym": U.format("1599058917765-a780eda07a3e"),
    "court": U.format("1544919982-b61976f0ba43"),
    "bus": U.format("1570125909232-eb263c188f7e"),
    "car": U.format("1502877338535-766e1452684a"),
}

WEEKDAYS = [0, 1, 2, 3, 4]
ALLDAYS = [0, 1, 2, 3, 4, 5, 6]


class Command(BaseCommand):
    help = "Seed a realistic demo campus"

    def add_arguments(self, parser):
        parser.add_argument("--reset", action="store_true", help="Wipe domain data first")
        parser.add_argument("--if-empty", action="store_true", help="Do nothing if the catalogue already has data (safe to run on every deploy)")

    def handle(self, *args, reset=False, if_empty=False, **kw):
        if if_empty and Resource.objects.exists():
            self.stdout.write("Catalogue already has data, skipping the seed.")
            return
        random.seed(42)
        if reset:
            self.wipe()
        with transaction.atomic():
            self.people()
            self.catalogue()
            self.rules()
            self.workflows()
            self.consumables()
        self.timetable()
        self.history()
        self.upcoming()
        self.maintenance()
        # Seeding fires real notifications; keep only the demo personas' inboxes (the background
        # crowd has no email and nobody logs in as them), and mark seeded history as already read.
        Notification.objects.exclude(user__username__startswith="demo.").exclude(
            user__in=[self.custodian2, self.sports]
        ).delete()
        for uid in Notification.objects.values_list("user_id", flat=True).distinct():
            fresh = list(Notification.objects.filter(user_id=uid).order_by("-id").values_list("id", flat=True)[:3])
            Notification.objects.filter(user_id=uid).exclude(id__in=fresh).update(read_at=timezone.now())
        self.stdout.write(self.style.SUCCESS(
            f"Seeded {Resource.objects.count()} resources · {Booking.objects.count()} bookings · "
            f"{TimetableEntry.objects.count()} timetable entries. Demo password: {settings.DEMO_PASSWORD}"
        ))

    # ------------------------------------------------------------------ wipe
    def wipe(self):
        for m in (Notification, Issuance, Approval, CheckIn, NoShow, BookingSlot, BookingAttempt, Booking, RecurrenceRule,
                  MaintenanceWindow, TimetableEntry, TimetableVersion, UtilisationSnapshot, Consumable, ApprovalStep,
                  ApprovalWorkflow, AvailabilityRule, Blackout, Quota, ResourceAttribute, Custodian, Resource,
                  ResourceType, Location):
            m.objects.all().delete()
        Department.objects.update(head=None)
        User.objects.exclude(is_superuser=True, username__in=["admin"]).delete()
        Department.objects.all().delete()

    # ------------------------------------------------------------------ people
    def people(self):
        depts = {
            "CSE": "School of Computer Science & Engineering",
            "ECE": "School of Electronics & Electrical Engineering",
            "MEC": "School of Mechanical Engineering",
            "BIO": "School of Bioengineering & Biosciences",
            "MGT": "Mittal School of Business",
            "ADM": "Division of Estate & Administration",
        }
        self.depts = {c: Department.objects.get_or_create(code=c, defaults={"name": n})[0] for c, n in depts.items()}
        pw = settings.DEMO_PASSWORD

        def mk(username, first, last, role, dept, email=True, **extra):
            u, created = User.objects.get_or_create(username=username, defaults=dict(
                first_name=first, last_name=last, role=role, department=self.depts[dept],
                email=f"{username}@campus.test" if email else "", **extra))
            if created:
                u.set_password(pw)
                u.save()
            return u

        self.student = mk("demo.student", "Aarav", "Sharma", Role.STUDENT, "CSE")
        self.faculty = mk("demo.faculty", "Meera", "Iyer", Role.FACULTY, "CSE")
        self.staff = mk("demo.staff", "Imran", "Qureshi", Role.STAFF, "ECE")
        self.custodian = mk("demo.custodian", "Rohan", "Verma", Role.CUSTODIAN, "CSE")
        self.head = mk("demo.head", "Anil", "Kapoor", Role.DEPT_HEAD, "CSE")
        self.manager = mk("demo.manager", "Kavya", "Nair", Role.FACILITY_MANAGER, "ADM")
        self.admin = mk("demo.admin", "Sana", "Malik", Role.ADMIN, "ADM", is_staff=True, is_superuser=True)
        if not settings.DEBUG:
            for u in (self.manager, self.admin):
                u.set_password(settings.DEMO_ADMIN_PASSWORD or None)
                u.save(update_fields=["password"])
        self.custodian2 = mk("bio.custodian", "Priya", "Menon", Role.CUSTODIAN, "BIO")
        self.sports = mk("sports.custodian", "Harpreet", "Gill", Role.CUSTODIAN, "ADM")
        heads = {"ECE": ("Suresh", "Rao"), "MEC": ("Deepak", "Bhatia"), "BIO": ("Lakshmi", "Pillai"), "MGT": ("Neha", "Chawla")}
        for code, (f, l) in heads.items():
            h = mk(f"head.{code.lower()}", f, l, Role.DEPT_HEAD, code)
            self.depts[code].head = h
            self.depts[code].save()
        self.depts["CSE"].head = self.head
        self.depts["CSE"].save()

        firsts = ["Ishaan", "Diya", "Kabir", "Ananya", "Vihaan", "Saanvi", "Arjun", "Myra", "Reyansh", "Aadhya", "Advait",
                  "Kiara", "Dhruv", "Anika", "Rudra", "Tara", "Yash", "Zoya", "Nikhil", "Ira", "Manav", "Riya", "Kunal", "Pari"]
        lasts = ["Gupta", "Singh", "Reddy", "Joshi", "Mehta", "Das", "Bose", "Kulkarni", "Patel", "Saxena", "Thakur", "Arora"]
        self.crowd = []
        for i, f in enumerate(firsts):
            role = Role.FACULTY if i % 6 == 0 else Role.STUDENT
            dept = random.choice(["CSE", "CSE", "ECE", "MEC", "BIO", "MGT"])
            self.crowd.append(mk(f"user{i:02d}", f, random.choice(lasts), role, dept, email=False))

    # ------------------------------------------------------------------ catalogue
    def catalogue(self):
        T = {}
        types = [
            ("Classroom", "chalkboard", "#F5B544", "Lecture rooms with projection — faculty book freely, students need HOD approval.", [], False),
            ("Laboratory", "flask", "#3EE6C1", "Teaching and research labs.", [], True),
            ("Equipment", "microscope", "#8B7CFF", "High-value instruments and lendable kit. HOD approval required.", [], True),
            ("Seminar Hall", "presentation", "#FF7A59", "Halls and auditoria for events, talks and defences.", [Role.FACULTY, Role.STAFF, Role.CUSTODIAN, Role.DEPT_HEAD, Role.FACILITY_MANAGER, Role.ADMIN], True),
            ("Sports Facility", "basketball", "#5FD068", "Courts, turf and fitness spaces.", [], True),
            ("Meeting Room", "users-three", "#5AB2FF", "Bookable rooms for group work and meetings.", [], True),
            ("Vehicle", "van", "#E66BD3", "Campus transport for field trips and official travel.", [Role.FACULTY, Role.STAFF, Role.DEPT_HEAD, Role.FACILITY_MANAGER, Role.ADMIN], False),
        ]
        for name, icon, color, desc, roles, checkin in types:
            T[name], _ = ResourceType.objects.update_or_create(
                name=name, defaults=dict(icon=icon, color=color, description=desc, allowed_roles=roles, requires_checkin=checkin))
        self.types = T

        L = {}
        for key, b, fl, room, lat, lng in [
            ("b34", "Block 34 · School of CSE", "", "", 31.2551, 75.7049),
            ("b33", "Block 33 · Electronics & Electrical", "", "", 31.2546, 75.7042),
            ("b38", "Block 38 · Bioengineering", "", "", 31.2538, 75.7058),
            ("b26", "Block 26 · Mechanical", "", "", 31.2566, 75.7031),
            ("aud", "Main Auditorium", "", "", 31.2532, 75.7027),
            ("lib", "Central Library", "", "", 31.2557, 75.7019),
            ("spt", "Sports Complex · LPU Ground", "", "", 31.2561, 75.7105),
            ("yard", "Transport Office · Gate 1", "", "", 31.2518, 75.7004),
        ]:
            L[key] = (b, lat, lng)

        def loc(key, floor, room):
            b, lat, lng = L[key]
            return Location.objects.get_or_create(building=b, floor=floor, room=room, defaults={"latitude": lat, "longitude": lng, "campus": "LPU · Phagwara"})[0]

        D = self.depts
        R = []

        def res(code, name, tname, dept, location, cap, features, img, value, desc, attrs=None, custodians=()):
            r, _ = Resource.objects.update_or_create(code=code, defaults=dict(
                name=name, type=T[tname], department=D[dept], location=location, capacity=cap, features=features,
                image_url=IMG[img], value_inr=value, description=desc, status=Resource.Status.ACTIVE))
            for k, v in (attrs or {}).items():
                ResourceAttribute.objects.update_or_create(resource=r, key=k, defaults={"value": v})
            for i, c in enumerate(custodians):
                Custodian.objects.get_or_create(resource=r, user=c, defaults={"is_primary": i == 0})
            R.append(r)
            return r

        c, c2, sp, mgr = self.custodian, self.custodian2, self.sports, self.manager
        # Classrooms
        res("CR-34-201", "Room 34-201", "Classroom", "CSE", loc("b34", "2", "201"), 60, ["Projector", "Smart board", "AC"], "classroom", 450000, "Tiered lecture room with dual projection.", {"Seating": "Tiered", "Board": "Glass + smart"}, [c])
        res("CR-34-305", "Room 34-305", "Classroom", "CSE", loc("b34", "3", "305"), 40, ["Projector", "AC", "Lecture capture"], "lecture", 380000, "Flat-floor room, movable desks — ideal for tutorials.", {"Seating": "Movable"}, [c])
        res("CR-34-410", "Room 34-410", "Classroom", "CSE", loc("b34", "4", "410"), 90, ["Projector", "PA system", "AC"], "students", 520000, "Large lecture theatre on the top floor.", {"Seating": "Tiered"}, [c])
        res("CR-33-102", "Room 33-102", "Classroom", "ECE", loc("b33", "1", "102"), 50, ["Projector", "Whiteboard"], "classroom", 300000, "Ground-floor room next to the ECE labs.", {}, [c])
        res("CR-26-210", "Room 26-210", "Classroom", "MEC", loc("b26", "2", "210"), 70, ["Projector", "Drafting tables"], "lecture", 340000, "Drawing hall with 35 drafting stations.", {"Special": "Drafting tables"}, [c])
        # Labs
        res("LAB-34-AI", "AI & Deep Learning Lab", "Laboratory", "CSE", loc("b34", "5", "501"), 36, ["GPU workstations", "AC", "Projector"], "complab", 8500000, "36 workstations with RTX GPUs and a shared DGX node.", {"GPUs": "36 × RTX 4090 + DGX A100", "OS": "Ubuntu 22.04"}, [c])
        res("LAB-34-NET", "Networks & Security Lab", "Laboratory", "CSE", loc("b34", "5", "504"), 30, ["Cisco racks", "Isolated VLAN"], "cowork", 4200000, "Routers, switches and an isolated range for security exercises.", {"Racks": "6 × Cisco"}, [c])
        res("LAB-33-EMB", "Embedded Systems Lab", "Laboratory", "ECE", loc("b33", "2", "214"), 28, ["Oscilloscopes", "Soldering stations", "ESD benches"], "workbench", 3100000, "ESD-safe benches with scopes and dev boards.", {"Benches": "14 dual"}, [c])
        res("LAB-38-MOL", "Molecular Biology Lab", "Laboratory", "BIO", loc("b38", "3", "312"), 24, ["Fume hood", "PCR", "Biosafety L2"], "lab", 6400000, "BSL-2 teaching lab with PCR and gel documentation.", {"Biosafety": "BSL-2"}, [c2])
        res("LAB-26-ROB", "Robotics & Automation Lab", "Laboratory", "MEC", loc("b26", "1", "118"), 20, ["Industrial arms", "PLC trainers"], "robotics", 7200000, "Two 6-axis arms, PLC trainers, and a mobile robot arena.", {"Arms": "2 × 6-axis"}, [c])
        # Equipment — the expensive stuff
        res("EQ-CONFOCAL", "Confocal Microscope", "Equipment", "BIO", loc("b38", "3", "318"), 3, ["Fluorescence", "Live-cell", "Training required"], "confocal", 18500000, "Laser-scanning confocal for live-cell imaging. Induction required.", {"Lasers": "405 / 488 / 561 / 640 nm", "Objectives": "10× – 100× oil"}, [c2])
        res("EQ-PCR-02", "qPCR Thermocycler", "Equipment", "BIO", loc("b38", "3", "312"), 2, ["96-well", "Real-time"], "pipette", 2400000, "Real-time PCR, 96-well block.", {"Channels": "5-colour"}, [c2])
        res("EQ-SPEC-01", "UV-Vis Spectrophotometer", "Equipment", "BIO", loc("b38", "2", "205"), 2, ["190–1100 nm"], "glass", 1600000, "Double-beam UV-Vis.", {"Range": "190–1100 nm"}, [c2])
        res("EQ-3DP-01", "Industrial 3D Printer", "Equipment", "MEC", loc("b26", "1", "120"), 1, ["FDM", "Carbon-fibre capable"], "workbench", 1250000, "Large-format FDM printer with enclosed, heated chamber.", {"Build volume": "400 × 400 × 450 mm"}, [c])
        res("EQ-VR-KIT", "VR Development Kit", "Equipment", "CSE", loc("b34", "5", "506"), 4, ["4 headsets", "Tracking"], "vr", 600000, "Four standalone headsets with a tracked play-space.", {"Headsets": "4"}, [c])
        res("EQ-CAM-4K", "Cinema Camera Kit", "Equipment", "MGT", loc("lib", "G", "Media desk"), 1, ["4K", "Gimbal", "Lavalier mics"], "camera", 450000, "Camera, gimbal, lights and two lav mics for media projects.", {"Sensor": "Super 35"}, [c])
        res("EQ-SCOPE-01", "Mixed-Signal Oscilloscope", "Equipment", "ECE", loc("b33", "2", "214"), 1, ["1 GHz", "16 digital channels"], "pcb", 900000, "1 GHz MSO with protocol decoding.", {"Bandwidth": "1 GHz"}, [c])
        res("EQ-IOT-KIT", "IoT Prototyping Kit", "Equipment", "ECE", loc("b33", "2", "216"), 4, ["Arduino", "ESP32", "Sensors"], "arduino", 60000, "Boxed kits — microcontrollers, sensors, breadboards.", {"Kits": "12"}, [c])
        res("EQ-LAPTOP-POOL", "Loaner Laptop Cart", "Equipment", "ADM", loc("lib", "1", "Help desk"), 30, ["30 laptops", "Charging cart"], "laptop", 1800000, "A cart of 30 laptops for exams and workshops.", {"Units": "30"}, [c])
        # Seminar halls
        res("SH-AUD-1", "Central Auditorium", "Seminar Hall", "ADM", loc("aud", "G", "Main"), 600, ["Stage lighting", "PA system", "Recording"], "auditorium", 25000000, "600-seat auditorium with full AV and green room.", {"Seats": "600"}, [mgr])
        res("SH-34-SEM", "CSE Seminar Hall", "Seminar Hall", "CSE", loc("b34", "1", "Seminar"), 150, ["Projector", "Video conferencing", "Recording"], "seminar", 3500000, "150-seat hall used for talks, defences and hackathons.", {"Seats": "150"}, [c])
        res("SH-38-CONF", "Life Sciences Conference Room", "Seminar Hall", "BIO", loc("b38", "4", "Conf"), 60, ["Video conferencing"], "boardroom", 1200000, "Conference-style seating for 60.", {}, [c2])
        # Sports
        res("SP-BASK-1", "Basketball Court 1", "Sports Facility", "ADM", loc("spt", "", "Court 1"), 20, ["Floodlights", "Wooden floor"], "basketball", 2200000, "Indoor court with floodlights.", {"Surface": "Maple"}, [sp])
        res("SP-TURF", "Football Turf", "Sports Facility", "ADM", loc("spt", "", "Turf"), 30, ["Floodlights", "Artificial turf"], "football", 4500000, "7-a-side artificial turf.", {"Size": "7-a-side"}, [sp])
        res("SP-BADM-A", "Badminton Hall A", "Sports Facility", "ADM", loc("spt", "1", "Hall A"), 8, ["4 courts", "Synthetic mat"], "badminton", 1500000, "Four synthetic courts.", {"Courts": "4"}, [sp])
        res("SP-GYM", "Strength & Conditioning Room", "Sports Facility", "ADM", loc("spt", "G", "Gym"), 25, ["Free weights", "Trainer on duty"], "gym", 2800000, "Group-booking slots for teams.", {}, [sp])
        # Meeting rooms
        res("MR-LIB-1", "Library Discussion Room 1", "Meeting Room", "ADM", loc("lib", "2", "DR-1"), 8, ["Whiteboard", "TV screen"], "meeting", 150000, "Glass-walled group study room.", {}, [c])
        res("MR-LIB-2", "Library Discussion Room 2", "Meeting Room", "ADM", loc("lib", "2", "DR-2"), 6, ["Whiteboard"], "openmeet", 120000, "Quiet room for small groups.", {}, [c])
        res("MR-34-BOARD", "CSE Board Room", "Meeting Room", "CSE", loc("b34", "6", "Board"), 16, ["Video conferencing", "TV screen"], "boardroom", 900000, "Board room for faculty meetings and interviews.", {}, [c])
        res("MR-STARTUP", "Incubator Pod", "Meeting Room", "MGT", loc("lib", "3", "Pod"), 10, ["Whiteboard", "Coffee"], "lounge", 250000, "Casual pod in the incubation centre.", {}, [c])
        # Vehicles
        res("VH-BUS-01", "52-Seater Coach", "Vehicle", "ADM", loc("yard", "", "Bay 1"), 52, ["AC", "Driver included"], "bus", 4500000, "Air-conditioned coach for field trips.", {"Registration": "PB-08-XX-1101"}, [mgr])
        res("VH-CAR-03", "Sedan (Official)", "Vehicle", "ADM", loc("yard", "", "Bay 4"), 4, ["Driver included"], "car", 1400000, "Official travel within 200 km.", {"Registration": "PB-08-XX-3303"}, [mgr])
        self.resources = {r.code: r for r in R}

    # ------------------------------------------------------------------ rules
    def rules(self):
        T = self.types

        def rule(t, name, days, o, cl, mn, mx, lead, adv, slot=30):
            AvailabilityRule.objects.create(resource_type=T[t], name=name, weekdays=days, open_time=time(*o), close_time=time(*cl),
                                            min_duration_minutes=mn, max_duration_minutes=mx, min_lead_minutes=lead,
                                            max_advance_days=adv, slot_minutes=slot)

        rule("Classroom", "Teaching hours", WEEKDAYS, (8, 0), (20, 0), 30, 180, 0, 21)
        rule("Classroom", "Saturday", [5], (9, 0), (14, 0), 30, 180, 60, 21)
        rule("Laboratory", "Lab hours", WEEKDAYS, (8, 0), (21, 0), 60, 240, 0, 14)
        rule("Laboratory", "Weekend research", [5, 6], (10, 0), (17, 0), 60, 240, 120, 14)
        rule("Equipment", "Instrument hours", WEEKDAYS + [5], (9, 0), (18, 0), 30, 240, 60, 30)
        rule("Seminar Hall", "Events", ALLDAYS, (8, 0), (22, 0), 60, 480, 24 * 60, 60, 60)
        rule("Sports Facility", "Sports", ALLDAYS, (6, 0), (22, 0), 60, 120, 0, 7, 60)
        rule("Meeting Room", "Library hours", ALLDAYS, (8, 0), (23, 0), 30, 120, 0, 7)
        rule("Vehicle", "Transport", ALLDAYS, (6, 0), (22, 0), 120, 960, 24 * 60, 30, 60)
        # A per-resource override: the confocal needs a 2-hour block minimum and only runs 10–17.
        AvailabilityRule.objects.create(resource=self.resources["EQ-CONFOCAL"], name="Confocal sessions", weekdays=WEEKDAYS,
                                        open_time=time(10), close_time=time(17), min_duration_minutes=60,
                                        max_duration_minutes=180, min_lead_minutes=120, max_advance_days=21, slot_minutes=60)

        tz = timezone.get_current_timezone()
        today = timezone.localdate()
        d = today + timedelta(days=(4 - today.weekday()) % 7 + 14)  # a Friday ~2–3 weeks out
        Blackout.objects.create(title="Founders' Day — campus closed",
                                period=tsrange(timezone.make_aware(datetime.combine(d, time(0)), tz),
                                               timezone.make_aware(datetime.combine(d + timedelta(days=1), time(0)), tz)))
        e = today + timedelta(days=9)
        Blackout.objects.create(title="Mid-term practical exams", resource_type=self.types["Laboratory"],
                                period=tsrange(timezone.make_aware(datetime.combine(e, time(9)), tz),
                                               timezone.make_aware(datetime.combine(e, time(13)), tz)))

        Quota.objects.create(role=Role.STUDENT, user_hours_per_week=10, max_active_bookings=4)
        Quota.objects.create(role=Role.STUDENT, resource_type=self.types["Equipment"], user_hours_per_week=6, max_active_bookings=2)
        for code, hours in [("CSE", 260), ("ECE", 150), ("MEC", 110), ("BIO", 130), ("MGT", 90)]:
            Quota.objects.create(department=self.depts[code], department_hours_per_week=hours)
        Policy.get()

    # ------------------------------------------------------------------ workflows
    def workflows(self):
        T = self.types

        def wf(name, t, roles, steps, prio=0):
            w = ApprovalWorkflow.objects.create(name=name, resource_type=T[t], requester_roles=roles, priority=prio)
            for i, (n, r) in enumerate(steps, start=1):
                ApprovalStep.objects.create(workflow=w, order=i, name=n, approver_role=r, sla_hours=24)

        wf("Equipment — HOD sign-off", "Equipment", [], [("HOD approval", Role.DEPT_HEAD)])
        wf("Students in classrooms", "Classroom", [Role.STUDENT], [("HOD approval", Role.DEPT_HEAD)])
        wf("Seminar hall events", "Seminar Hall", [], [("HOD approval", Role.DEPT_HEAD)])
        wf("Vehicle requisition", "Vehicle", [], [("HOD approval", Role.DEPT_HEAD)])
        wf("Student lab access", "Laboratory", [Role.STUDENT], [("HOD approval", Role.DEPT_HEAD)])

    # ------------------------------------------------------------------ consumables
    def consumables(self):
        R, T = self.resources, self.types
        items = [
            ("PCR Master Mix (100 rxn)", "BIO-PCR-MM", "consumable", None, R["EQ-PCR-02"], "kits", 4, 3, 18000),
            ("Nitrile gloves (box)", "BIO-GLOVE", "consumable", T["Laboratory"], None, "boxes", 46, 10, 450),
            ("Immersion oil", "BIO-OIL", "consumable", None, R["EQ-CONFOCAL"], "ml", 35, 20, 90),
            ("PLA filament 1 kg", "MEC-PLA", "consumable", None, R["EQ-3DP-01"], "spools", 3, 4, 1800),
            ("Carbon-fibre nylon 1 kg", "MEC-CFN", "consumable", None, R["EQ-3DP-01"], "spools", 6, 2, 6500),
            ("Logic analyser probe set", "ECE-PROBE", "accessory", None, R["EQ-SCOPE-01"], "sets", 4, 1, 12000),
            ("ESP32 dev boards", "ECE-ESP32", "consumable", None, R["EQ-IOT-KIT"], "pcs", 22, 10, 650),
            ("HDMI / USB-C adapter", "AV-ADAPT", "accessory", T["Classroom"], None, "pcs", 12, 4, 1200),
            ("Wireless mic set", "AV-MIC", "accessory", T["Seminar Hall"], None, "sets", 6, 2, 9000),
            ("Basketballs", "SP-BALL", "accessory", None, R["SP-BASK-1"], "pcs", 8, 4, 1500),
            ("Badminton shuttles (tube)", "SP-SHUT", "consumable", None, R["SP-BADM-A"], "tubes", 5, 6, 900),
            ("Whiteboard marker pack", "GEN-MARK", "consumable", T["Meeting Room"], None, "packs", 30, 8, 250),
        ]
        for name, sku, kind, rtype, res, unit, stock, reorder, cost in items:
            Consumable.objects.update_or_create(sku=sku, defaults=dict(name=name, kind=kind, resource_type=rtype, resource=res,
                                                                        unit=unit, stock=stock, reorder_level=reorder, unit_cost=cost))

    # ------------------------------------------------------------------ timetable (P13)
    def timetable(self):
        today = timezone.localdate()
        term_start = today - timedelta(days=today.weekday() + 35)
        term_end = today + timedelta(days=70)
        courses = [("CSE326", "Internet Programming Lab"), ("INT253", "Database Systems"), ("CSE310", "Programming in Java"),
                   ("CSE408", "Design & Analysis of Algorithms"), ("ECE249", "Digital Electronics"), ("MEC101", "Engineering Graphics"),
                   ("CSE316", "Operating Systems"), ("INT306", "Database Management"), ("BTY208", "Molecular Biology"),
                   ("ECE315", "Embedded Systems"), ("CSE422", "Deep Learning"), ("MEC360", "Robotics")]
        faculty = ["Dr. Meera Iyer", "Prof. R. Kumar", "Dr. S. Banerjee", "Dr. P. Kaur", "Prof. V. Menon", "Dr. A. Thomas"]
        entries = []
        rooms = ["CR-34-201", "CR-34-305", "CR-34-410", "CR-33-102", "CR-26-210"]
        for room in rooms:
            for wd in WEEKDAYS:
                for start_h in random.sample([9, 10, 11, 13, 14, 15, 16], k=random.choice([3, 4, 4, 5])):
                    code, name = random.choice(courses[:8])
                    entries.append({"resource_code": room, "weekday": wd, "start": f"{start_h:02d}:00", "end": f"{start_h:02d}:50",
                                    "course_code": code, "course_name": name, "section": f"K{random.randint(21, 24)}{random.choice('ABCDE')}",
                                    "faculty": random.choice(faculty)})
        labs = {"LAB-34-AI": ("CSE422", "Deep Learning"), "LAB-34-NET": ("CSE316", "Operating Systems"),
                "LAB-33-EMB": ("ECE315", "Embedded Systems"), "LAB-38-MOL": ("BTY208", "Molecular Biology"),
                "LAB-26-ROB": ("MEC360", "Robotics")}
        for room, (code, name) in labs.items():
            for wd, (s, e) in zip(random.sample(WEEKDAYS, 3), [("10:00", "11:50"), ("14:00", "15:50"), ("09:00", "10:50")]):
                entries.append({"resource_code": room, "weekday": wd, "start": s, "end": e, "course_code": code,
                                "course_name": name + " (Practical)", "section": f"P{random.randint(1, 4)}", "faculty": random.choice(faculty)})
        publish({"label": f"Term timetable · v3 · published {today:%d %b}", "term_start": term_start.isoformat(),
                 "term_end": term_end.isoformat(), "entries": entries}, source="P13 · seed")

    # ------------------------------------------------------------------ history
    def _free(self, resource, s, e):
        return not BookingSlot.objects.filter(resource=resource, period__overlap=(s, e)).exists() and not Booking.objects.filter(
            resource=resource, period__overlap=(s, e)).exists()

    def history(self):
        """Four weeks of past bookings with realistic shapes: popular labs, idle microscope, a few no-shows."""
        tz = timezone.get_current_timezone()
        today = timezone.localdate()
        popularity = {"Laboratory": 0.65, "Meeting Room": 0.8, "Sports Facility": 0.75, "Classroom": 0.35,
                      "Equipment": 0.25, "Seminar Hall": 0.2, "Vehicle": 0.15}
        idle = {"EQ-CONFOCAL", "EQ-SPEC-01", "VH-CAR-03"}  # the expensive things nobody books
        titles = {"Laboratory": ["Project build", "Practice session", "Thesis experiments", "Club workshop"],
                  "Meeting Room": ["Group study", "Project sync", "Mock interview", "Startup pitch prep"],
                  "Sports Facility": ["Team practice", "Inter-hostel match", "Fitness session"],
                  "Classroom": ["Extra class", "Doubt session", "Club meeting"],
                  "Equipment": ["Sample run", "Prototype print", "Measurements", "Video shoot"],
                  "Seminar Hall": ["Guest lecture", "Hackathon finals", "Thesis defence"],
                  "Vehicle": ["Industrial visit", "Field trip", "Official travel"]}
        users = self.crowd + [self.student, self.faculty, self.staff]
        rows = []
        for back in range(28, 0, -1):
            d = today - timedelta(days=back)
            for r in self.resources.values():
                tname = r.type.name
                p = popularity[tname] * (0.08 if r.code in idle else 1)
                for slot_h in range(8, 21):
                    if random.random() > p * 0.42:
                        continue
                    dur = random.choice([1, 1, 2]) if tname not in ("Vehicle", "Seminar Hall") else random.choice([3, 4])
                    s = timezone.make_aware(datetime.combine(d, time(slot_h)), tz)
                    e = s + timedelta(hours=dur)
                    if tname == "Equipment" and slot_h < 9 or e.hour > 21 or not self._free(r, s, e):
                        continue
                    u = random.choice([x for x in users if not r.type.allowed_roles or x.role in r.type.allowed_roles] or [self.faculty])
                    roll = random.random()
                    noshow_rate = 0.22 if u in (self.crowd[3], self.crowd[7]) else 0.07
                    status = Booking.Status.RELEASED if (r.type.requires_checkin and roll < noshow_rate) else Booking.Status.COMPLETED
                    b = Booking.objects.create(resource=r, user=u, title=random.choice(titles[tname]), period=tsrange(s, e),
                                               status=status, attendees=min(r.capacity, random.randint(1, 12)))
                    Booking.objects.filter(pk=b.pk).update(created_at=s - timedelta(days=random.randint(1, 5)))
                    if status == Booking.Status.COMPLETED and r.type.requires_checkin:
                        ci = CheckIn.objects.create(booking=b, method=random.choice(["resource_qr", "resource_qr", "booking_qr"]),
                                                    checked_out_at=e)
                        CheckIn.objects.filter(pk=ci.pk).update(checked_in_at=s + timedelta(minutes=random.randint(-5, 12)))
                    elif status == Booking.Status.RELEASED:
                        ns = NoShow.objects.create(booking=b, user=u, resource=r)
                        NoShow.objects.filter(pk=ns.pk).update(recorded_at=s + timedelta(minutes=15))
                    if ApprovalWorkflow.objects.filter(resource_type=r.type).exists() and random.random() < 0.7:
                        act = s - timedelta(days=random.randint(1, 3), hours=random.randint(0, 6))
                        Approval.objects.create(booking=b, order=1, step_name="Custodian check", approver_role="custodian",
                                                status="approved", decided_by=self.custodian, activated_at=act,
                                                decided_at=act + timedelta(hours=random.uniform(0.3, 20)))
                    rows.append(BookingAttempt(resource=r, user=u, period=tsrange(s, e), outcome="booked"))
                    if tname in ("Laboratory", "Meeting Room", "Sports Facility") and random.random() < 0.45:
                        rows.append(BookingAttempt(resource=r, user=random.choice(users), period=tsrange(s, e), outcome="conflict",
                                                   reason="Already booked"))
        BookingAttempt.objects.bulk_create(rows)
        # Spread attempt timestamps over the window (auto_now_add sets "now").
        for a in BookingAttempt.objects.all().only("id", "period"):
            BookingAttempt.objects.filter(pk=a.pk).update(created_at=a.period.lower - timedelta(days=random.randint(0, 4)))

        # A repeat offender, already restricted, so the no-show monitor has a story.
        offender = self.crowd[3]
        offender.restricted_until = timezone.now() + timedelta(days=5)
        offender.restriction_reason = "4 no-shows in 30 days"
        offender.save()

    # ------------------------------------------------------------------ upcoming
    def upcoming(self):
        tz = timezone.get_current_timezone()
        now = timezone.now()
        today = timezone.localdate()
        R = self.resources

        def at(day_offset, h, m=0):
            return timezone.make_aware(datetime.combine(today + timedelta(days=day_offset), time(h, m)), tz)

        def put(user, code, s, e, title, **kw):
            r = R[code]
            if not self._free(r, s, e):
                return None
            try:
                with transaction.atomic():
                    return _insert(user, r, s, e, title=title, **kw)
            except Exception:
                return None

        # Live demo: a lab booking for the demo student that is checkable right now (check-in window open).
        start = now.replace(second=0, microsecond=0) - timedelta(minutes=5)
        live = put(self.student, "MR-LIB-1", start, start + timedelta(minutes=60), "Group study — DBMS revision", attendees=5)
        if live is None:
            # fall back to the other discussion room if a seeded booking already holds it
            put(self.student, "MR-LIB-2", start, start + timedelta(minutes=60), "Group study — DBMS revision", attendees=5)

        # Future bookings around campus for the next week.
        users = self.crowd + [self.faculty, self.staff]
        for day in range(0, 8):
            for r in R.values():
                for h in random.sample(range(9, 19), k=2):
                    if random.random() < 0.35:
                        s = at(day, h)
                        if s < now:
                            continue
                        u = random.choice([x for x in users if not r.type.allowed_roles or x.role in r.type.allowed_roles] or [self.faculty])
                        b = put(u, r.code, s, s + timedelta(hours=1), random.choice(["Project work", "Practice", "Team meeting", "Experiment"]))
                        if b is not None and b.status == Booking.Status.PENDING:
                            # background traffic: pretend these were approved already
                            for a in b.approvals.all():
                                act = now - timedelta(hours=random.uniform(2, 30))
                                a.status, a.decided_by = "approved", self.custodian
                                a.activated_at, a.decided_at = act, act + timedelta(hours=random.uniform(0.2, 9))
                                a.save()
                            Booking.objects.filter(pk=b.pk).update(status=Booking.Status.CONFIRMED, decided_at=now)

        # Demo student's own upcoming bookings
        put(self.student, "LAB-34-AI", at(1, 16), at(1, 18), "Capstone model training", attendees=3)
        put(self.student, "SP-BADM-A", at(2, 18), at(2, 19), "Badminton with hostel team", attendees=4)
        put(self.student, "EQ-VR-KIT", at(3, 11), at(3, 13), "Unity VR prototype", attendees=2)  # pending custodian approval

        # Pending approvals for the approver personas
        put(self.faculty, "SH-34-SEM", at(6, 10), at(6, 13), "Guest lecture: Systems at scale", attendees=140,
            purpose="Invited talk by an industry speaker, open to all CSE students.")
        put(self.faculty, "VH-BUS-01", at(9, 7), at(9, 18), "Industrial visit — Infosys Mohali", attendees=48, on_behalf_of="K22CS")
        put(self.crowd[1], "EQ-CONFOCAL", at(4, 10), at(4, 12), "Live-cell imaging — HeLa", attendees=2)
        put(self.crowd[2], "EQ-3DP-01", at(2, 14), at(2, 17), "Drone frame print", attendees=1)
        put(self.crowd[4], "CR-34-305", at(1, 17), at(1, 18), "Coding club meetup", attendees=30)

        # A recurring series by faculty (weekly tutorial), with one mid-series conflict handled.
        from apps.bookings.services import create_recurring

        try:
            first = at((7 - today.weekday()) % 7 or 7, 18)  # next Monday, 18:00
            create_recurring(self.faculty, R["CR-34-201"], first, first + timedelta(hours=1), title="DSA tutorial (extra)",
                             on_behalf_of="K22CS-B", attendees=45, freq="weekly", count=6, conflict_policy="skip")
        except Exception as exc:  # pragma: no cover - seed must not fail on a busy calendar
            self.stdout.write(f"recurring seed skipped: {exc}")

        # A couple of no-shows for the demo student so the warning shows up on their profile.
        for i, code in enumerate(["MR-LIB-2", "SP-TURF"]):
            past = timezone.make_aware(datetime.combine(today - timedelta(days=3 + i * 4), time(17)), tz)
            if not self._free(R[code], past, past + timedelta(hours=1)):
                continue
            b = Booking.objects.create(resource=R[code], user=self.student, title="Booked but missed", period=tsrange(past, past + timedelta(hours=1)),
                                       status=Booking.Status.RELEASED, status_note="Not checked in within 15 min")
            NoShow.objects.create(booking=b, user=self.student, resource=R[code])

    # ------------------------------------------------------------------ maintenance
    def maintenance(self):
        tz = timezone.get_current_timezone()
        today = timezone.localdate()
        R = self.resources

        def at(d, h):
            return timezone.make_aware(datetime.combine(today + timedelta(days=d), time(h)), tz)

        past = [("LAB-34-AI", -12, 8, 14, "GPU driver & CUDA upgrade", "scheduled"),
                ("SP-TURF", -9, 6, 22, "Turf re-infill", "scheduled"),
                ("EQ-3DP-01", -6, 9, 17, "Nozzle jam — hot-end replaced", "breakdown"),
                ("LAB-33-EMB", -4, 8, 12, "Annual ESD audit", "scheduled")]
        for code, d, h1, h2, title, kind in past:
            MaintenanceWindow.objects.create(resource=R[code], kind=kind, title=title, period=tsrange(at(d, h1), at(d, h2)),
                                             status="done", resolved_at=at(d, h2), reported_by=self.custodian)
        # Offsets from "today" can land on a timetabled class on some weekdays; a clash here only means
        # one less demo window, so it must never abort the seed.
        def try_schedule(*args, **kw):
            try:
                schedule_maintenance(*args, **kw)
            except BookingError as exc:
                self.stdout.write(f"maintenance demo skipped: {args[0].code}: {exc.message}")

                try_schedule(R["SP-BASK-1"], at(5, 6), at(5, 14), title="Floor re-varnish", notes="Court closed until the varnish cures.", by=self.sports)
        try_schedule(R["LAB-38-MOL"], at(11, 8), at(11, 13), title="Fume hood certification", by=self.custodian2)
        try_schedule(R["EQ-SCOPE-01"], at(0, 0), at(2, 18), title="Channel 3 noisy — sent for calibration",
                             kind=MaintenanceWindow.Kind.BREAKDOWN, by=self.custodian)
