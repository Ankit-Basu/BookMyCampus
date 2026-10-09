"""
Reporting. All figures are computed from first principles over a date range:

  supply   = opening hours − blackouts             (rules.services.bookable_windows)
  teaching = timetabled class minutes in the ledger
  booked   = minutes held by bookings (incl. no-shows — they blocked others)
  used     = minutes actually checked-in / completed
  utilisation      = (used + teaching) / supply
  idle value (INR) = asset value × (1 − utilisation)  → the "expensive thing nobody uses" ranking
"""
from collections import defaultdict
from datetime import datetime, time, timedelta

from django.db.models import Count, Q
from django.utils import timezone

from apps.accounts.models import Department
from apps.approvals.models import Approval
from apps.bookings.models import Booking, BookingAttempt, BookingSlot, NoShow
from apps.catalogue.models import Resource
from apps.maintenance.models import MaintenanceWindow
from apps.rules.models import Quota
from apps.rules.services import bookable_windows, merge, subtract, total_minutes

USED = (Booking.Status.CHECKED_IN, Booking.Status.COMPLETED)
HELD = USED + (Booking.Status.CONFIRMED, Booking.Status.RELEASED)


def _bounds(start_date, end_date):
    tz = timezone.get_current_timezone()
    return (
        timezone.make_aware(datetime.combine(start_date, time(0)), tz),
        timezone.make_aware(datetime.combine(end_date, time(0)), tz),
    )


def _clip(period, lo, hi):
    s, e = max(period.lower, lo), min(period.upper, hi)
    return (s, e) if s < e else None


def _collect(start_date, end_date, resources):
    """One pass over the ledger: per-resource interval sets for supply / teaching / booked / used."""
    lo, hi = _bounds(start_date, end_date)
    rows = {}
    for r in resources:
        rows[r.id] = {
            "resource": r, "supply_iv": bookable_windows(r, start_date, end_date), "booked": [], "used": [],
            "teaching": [], "maint": [], "bookings": 0, "no_shows": 0,
        }
    ids = list(rows)
    for b in Booking.objects.filter(resource_id__in=ids, status__in=HELD, period__overlap=(lo, hi)).only("resource_id", "period", "status"):
        iv = _clip(b.period, lo, hi)
        if not iv:
            continue
        row = rows[b.resource_id]
        row["bookings"] += 1
        row["booked"].append(iv)
        if b.status in USED:
            row["used"].append(iv)
        elif b.status == Booking.Status.RELEASED:
            row["no_shows"] += 1
    for s in BookingSlot.objects.filter(resource_id__in=ids, kind=BookingSlot.Kind.TIMETABLE, period__overlap=(lo, hi)).only("resource_id", "period"):
        iv = _clip(s.period, lo, hi)
        if iv:
            rows[s.resource_id]["teaching"].append(iv)
    for m in MaintenanceWindow.objects.filter(resource_id__in=ids, period__overlap=(lo, hi)).exclude(status="cancelled").only("resource_id", "period"):
        iv = _clip(m.period, lo, hi)
        if iv:
            rows[m.resource_id]["maint"].append(iv)
    for row in rows.values():
        supply = subtract(row["supply_iv"], row["maint"])
        row["supply"] = supply
        # only activity inside supply (open hours, not under maintenance) counts — A ∩ B = A − (A − B)
        row["teaching_in"] = subtract(supply, subtract(supply, merge(row["teaching"])))
        row["used_in"] = subtract(supply, subtract(supply, merge(row["used"])))
        row["booked_in"] = subtract(supply, subtract(supply, merge(row["booked"])))
        row["active_in"] = subtract(supply, subtract(supply, merge(row["used"] + row["teaching"])))
    return rows


def _rows_out(rows):
    out = []
    for row in rows.values():
        r = row["resource"]
        supply = total_minutes(row["supply"])
        teaching = total_minutes(row["teaching_in"])
        used = total_minutes(row["used_in"])
        booked = total_minutes(row["booked_in"])
        util = total_minutes(row["active_in"]) / supply if supply else 0.0
        out.append(
            {
                "resource_id": r.id, "code": r.code, "name": r.name,
                "type": r.type.name, "type_id": r.type_id, "type_color": r.type.color,
                "department": r.department.code if r.department else None,
                "image": r.cover, "value_inr": r.value_inr,
                "supply_hours": round(supply / 60, 1), "teaching_hours": round(teaching / 60, 1),
                "booked_hours": round(booked / 60, 1), "used_hours": round(used / 60, 1),
                "maintenance_hours": round(total_minutes(merge(row["maint"])) / 60, 1),
                "utilisation": round(util, 4),
                "idle_value_inr": int(r.value_inr * (1 - min(util, 1.0))),
                "bookings": row["bookings"], "no_shows": row["no_shows"],
            }
        )
    return out


def resource_utilisation(start_date, end_date, resources=None):
    resources = list(resources if resources is not None else Resource.objects.exclude(status="retired").select_related("type", "department"))
    return _rows_out(_collect(start_date, end_date, resources))


def _rollup(rows, key, label_key=None):
    agg = defaultdict(lambda: {"supply_hours": 0, "used_hours": 0, "teaching_hours": 0, "booked_hours": 0, "resources": 0})
    for r in rows:
        k = r[key] or "—"
        a = agg[k]
        a["label"] = r[label_key] if label_key else k
        a["resources"] += 1
        for f in ("supply_hours", "used_hours", "teaching_hours", "booked_hours"):
            a[f] += r[f]
    out = []
    for k, a in agg.items():
        a["key"] = k
        a["utilisation"] = round((a["used_hours"] + a["teaching_hours"]) / a["supply_hours"], 4) if a["supply_hours"] else 0
        for f in ("supply_hours", "used_hours", "teaching_hours", "booked_hours"):
            a[f] = round(a[f], 1)
        out.append(a)
    return sorted(out, key=lambda x: -x["utilisation"])


def utilisation_report(start_date, end_date, type_id=None, department_id=None):
    qs = Resource.objects.exclude(status="retired").select_related("type", "department")
    if type_id:
        qs = qs.filter(type_id=type_id)
    if department_id:
        qs = qs.filter(department_id=department_id)
    collected = _collect(start_date, end_date, list(qs))
    rows = _rows_out(collected)
    totals = {
        "supply_hours": round(sum(r["supply_hours"] for r in rows), 1),
        "used_hours": round(sum(r["used_hours"] for r in rows), 1),
        "teaching_hours": round(sum(r["teaching_hours"] for r in rows), 1),
        "booked_hours": round(sum(r["booked_hours"] for r in rows), 1),
        "idle_value_inr": sum(r["idle_value_inr"] for r in rows),
    }
    totals["utilisation"] = round((totals["used_hours"] + totals["teaching_hours"]) / totals["supply_hours"], 4) if totals["supply_hours"] else 0
    return {
        "from": start_date, "to": end_date, "totals": totals,
        "by_resource": sorted(rows, key=lambda r: -r["utilisation"]),
        "by_type": _rollup(rows, "type"),
        "by_department": _rollup(rows, "department"),
        "idle_ranking": sorted(rows, key=lambda r: (-r["idle_value_inr"], r["utilisation"]))[:15],
        "daily": daily_series(start_date, end_date, collected),
    }


def daily_series(start_date, end_date, collected):
    tz = timezone.get_current_timezone()
    out = []
    d = start_date
    while d < end_date:
        lo = timezone.make_aware(datetime.combine(d, time(0)), tz)
        day = [(lo, lo + timedelta(days=1))]
        supply = active = 0
        for row in collected.values():
            supply += total_minutes(subtract(day, subtract(day, row["supply"])))
            active += total_minutes(subtract(day, subtract(day, row["active_in"])))
        out.append({"date": d, "utilisation": round(active / supply, 4) if supply else 0, "used_hours": round(active / 60, 1)})
        d += timedelta(days=1)
    return out


def heatmap(start_date, end_date, type_id=None):
    """Weekday × hour occupancy share — 'when is campus actually busy?'"""
    lo, hi = _bounds(start_date, end_date)
    grid = [[0.0] * 24 for _ in range(7)]
    qs = BookingSlot.objects.filter(period__overlap=(lo, hi))
    if type_id:
        qs = qs.filter(resource__type_id=type_id)
    for s in qs.only("period"):
        iv = _clip(s.period, lo, hi)
        if not iv:
            continue
        cur = timezone.localtime(iv[0])
        end = timezone.localtime(iv[1])
        while cur < end:
            nxt = min(end, (cur + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0))
            grid[cur.weekday()][cur.hour] += (nxt - cur).total_seconds() / 3600
            cur = nxt
    # Completed / used bookings no longer have a ledger slot — add them from Booking.
    bq = Booking.objects.filter(status__in=USED, period__overlap=(lo, hi), slot__isnull=True)
    if type_id:
        bq = bq.filter(resource__type_id=type_id)
    for b in bq.only("period"):
        iv = _clip(b.period, lo, hi)
        if not iv:
            continue
        cur, end = timezone.localtime(iv[0]), timezone.localtime(iv[1])
        while cur < end:
            nxt = min(end, (cur + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0))
            grid[cur.weekday()][cur.hour] += (nxt - cur).total_seconds() / 3600
            cur = nxt
    peak = max((v for row in grid for v in row), default=0) or 1
    return {"cells": [[round(v, 2) for v in row] for row in grid], "peak": round(peak, 2)}


def noshow_report(start_date, end_date):
    lo, hi = _bounds(start_date, end_date)
    ended = Booking.objects.filter(
        period__overlap=(lo, hi), resource__type__requires_checkin=True,
        status__in=(Booking.Status.CHECKED_IN, Booking.Status.COMPLETED, Booking.Status.RELEASED),
    )
    by_user = ended.values("user_id", "user__first_name", "user__last_name", "user__username", "user__restricted_until").annotate(
        total=Count("id"), noshows=Count("id", filter=Q(status=Booking.Status.RELEASED))
    )
    by_resource = ended.values("resource_id", "resource__code", "resource__name").annotate(
        total=Count("id"), noshows=Count("id", filter=Q(status=Booking.Status.RELEASED))
    )
    users = [
        {
            "user_id": u["user_id"],
            "name": f"{u['user__first_name']} {u['user__last_name']}".strip() or u["user__username"],
            "total": u["total"], "noshows": u["noshows"],
            "rate": round(u["noshows"] / u["total"], 3) if u["total"] else 0,
            "restricted_until": u["user__restricted_until"],
        }
        for u in by_user
    ]
    res = [
        {
            "resource_id": r["resource_id"], "code": r["resource__code"], "name": r["resource__name"],
            "total": r["total"], "noshows": r["noshows"], "rate": round(r["noshows"] / r["total"], 3) if r["total"] else 0,
        }
        for r in by_resource
    ]
    total = sum(u["total"] for u in users)
    noshows = sum(u["noshows"] for u in users)
    return {
        "rate": round(noshows / total, 3) if total else 0, "total": total, "noshows": noshows,
        "by_user": sorted(users, key=lambda x: (-x["noshows"], -x["rate"]))[:25],
        "by_resource": sorted(res, key=lambda x: -x["rate"])[:25],
    }


def demand_vs_supply(start_date, end_date):
    lo, hi = _bounds(start_date, end_date)
    util = resource_utilisation(start_date, end_date, Resource.objects.exclude(status="retired").select_related("type"))
    attempts = BookingAttempt.objects.filter(created_at__gte=lo, created_at__lt=hi)
    by_type = defaultdict(lambda: {"requests": 0, "booked": 0, "conflicts": 0, "rule_denied": 0, "supply_hours": 0.0, "booked_hours": 0.0})
    for a in attempts.values("resource__type__name", "outcome").annotate(n=Count("id")):
        t = by_type[a["resource__type__name"]]
        t["requests"] += a["n"]
        key = {"booked": "booked", "conflict": "conflicts", "rule": "rule_denied"}[a["outcome"]]
        t[key] += a["n"]
    for r in util:
        t = by_type[r["type"]]
        t["supply_hours"] += r["supply_hours"] - r["teaching_hours"]
        t["booked_hours"] += r["booked_hours"]
    out = []
    for name, t in by_type.items():
        t["type"] = name
        t["pressure"] = round(t["conflicts"] / t["requests"], 3) if t["requests"] else 0
        t["fill"] = round(t["booked_hours"] / t["supply_hours"], 3) if t["supply_hours"] else 0
        t["supply_hours"] = round(t["supply_hours"], 1)
        t["booked_hours"] = round(t["booked_hours"], 1)
        out.append(t)
    return sorted(out, key=lambda x: -x["pressure"])


def approval_turnaround(start_date, end_date):
    lo, hi = _bounds(start_date, end_date)
    qs = Approval.objects.filter(decided_at__gte=lo, decided_at__lt=hi, activated_at__isnull=False).select_related("booking__resource__type")
    agg = defaultdict(lambda: {"n": 0, "hours": 0.0, "approved": 0, "rejected": 0})
    for a in qs:
        k = (a.booking.resource.type.name, a.step_name)
        g = agg[k]
        g["n"] += 1
        g["hours"] += (a.decided_at - a.activated_at).total_seconds() / 3600
        g["approved" if a.status == "approved" else "rejected"] += 1
    return [
        {"type": t, "step": s, "decisions": g["n"], "avg_hours": round(g["hours"] / g["n"], 2), "approved": g["approved"], "rejected": g["rejected"]}
        for (t, s), g in sorted(agg.items())
    ]


def maintenance_downtime(start_date, end_date):
    lo, hi = _bounds(start_date, end_date)
    out = defaultdict(lambda: {"scheduled_hours": 0.0, "breakdown_hours": 0.0, "events": 0})
    names = {}
    for m in MaintenanceWindow.objects.filter(period__overlap=(lo, hi)).exclude(status="cancelled").select_related("resource"):
        iv = _clip(m.period, lo, hi)
        if not iv:
            continue
        h = (iv[1] - iv[0]).total_seconds() / 3600
        row = out[m.resource_id]
        row["events"] += 1
        row["scheduled_hours" if m.kind == "scheduled" else "breakdown_hours"] += h
        names[m.resource_id] = (m.resource.code, m.resource.name)
    return sorted(
        [
            {"resource_id": k, "code": names[k][0], "name": names[k][1], "events": v["events"],
             "scheduled_hours": round(v["scheduled_hours"], 1), "breakdown_hours": round(v["breakdown_hours"], 1)}
            for k, v in out.items()
        ],
        key=lambda x: -(x["scheduled_hours"] + x["breakdown_hours"]),
    )


def quota_consumption(week_of=None):
    now = timezone.localtime(week_of or timezone.now())
    monday = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    sunday = monday + timedelta(days=7)
    out = []
    for q in Quota.objects.filter(department__isnull=False, department_hours_per_week__gt=0).select_related("department", "resource_type"):
        qs = Booking.objects.filter(
            user__department=q.department, status__in=Booking.ACTIVE + (Booking.Status.COMPLETED,), period__overlap=(monday, sunday)
        )
        if q.resource_type_id:
            qs = qs.filter(resource__type_id=q.resource_type_id)
        used = 0.0
        for b in qs.only("period"):
            iv = _clip(b.period, monday, sunday)
            if iv:
                used += (iv[1] - iv[0]).total_seconds() / 3600
        out.append({
            "department": q.department.code, "department_name": q.department.name,
            "resource_type": q.resource_type.name if q.resource_type else "All resources",
            "limit_hours": q.department_hours_per_week, "used_hours": round(used, 1),
            "share": round(used / q.department_hours_per_week, 3),
        })
    return {"week_start": monday.date(), "rows": sorted(out, key=lambda x: -x["share"])}


def dashboard(user):
    now = timezone.now()
    today = timezone.localdate()
    lo, hi = _bounds(today, today + timedelta(days=1))
    live = Booking.objects.filter(status=Booking.Status.CHECKED_IN, period__contains=now).count()
    today_count = Booking.objects.filter(period__overlap=(lo, hi), status__in=Booking.ACTIVE + (Booking.Status.COMPLETED,)).count()
    week_ago = now - timedelta(days=7)
    from apps.consumables.models import Consumable
    from django.db.models import F

    return {
        "resources": Resource.objects.exclude(status="retired").count(),
        "down": Resource.objects.filter(status="down").count(),
        "bookings_today": today_count,
        "live_now": live,
        "pending_approvals": Approval.objects.filter(status="pending", booking__status="pending").count(),
        "noshows_week": NoShow.objects.filter(recorded_at__gte=week_ago, waived=False).count(),
        "restricted_users": type(user).objects.filter(restricted_until__gt=now).count(),
        "low_stock": Consumable.objects.filter(stock__lte=F("reorder_level")).count(),
        "departments": Department.objects.count(),
    }
