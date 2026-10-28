"""Kurs çegirmasi: sahifalarda körinadigan va tölovda olinadigan yagona narx."""
from dataclasses import dataclass
from typing import Optional

from django.db.models import Q
from django.utils import timezone

from .models import Discount, Profession

# Tezcheck va kurs formasi qabul qiladigan eng kam narx.
MIN_COURSE_PRICE = 1000


@dataclass(frozen=True)
class CoursePrice:
    original: int
    price: int
    discount: Optional[Discount] = None

    @property
    def has_discount(self):
        return self.discount is not None

    @property
    def saving(self):
        return self.original - self.price

    @property
    def percent(self):
        return round(self.saving * 100 / self.original) if self.original else 0

    @property
    def ends_at(self):
        return self.discount.valid_until if self.discount else None


def valid_discounts(now=None):
    now = now or timezone.now()
    return Discount.objects.filter(is_active=True).filter(
        Q(valid_from__isnull=True) | Q(valid_from__lte=now),
        Q(valid_until__isnull=True) | Q(valid_until__gt=now),
    )


def discounted_price(original, discount):
    value = int(discount.discount_value)
    if discount.discount_type == 'price':
        price = value
    elif discount.discount_type == 'percentage':
        price = original - original * min(value, 99) // 100
    else:
        price = original - value
    # Çegirma narxni oşirmaydi va eng kam tölovdan pastga tuşirmaydi.
    return min(original, max(MIN_COURSE_PRICE, price))


def best_price(profession, discounts):
    original = int(profession.one_time_price)
    result = CoursePrice(original, original)
    if not profession.is_sold_once:
        return result
    for discount in discounts:
        if discount.profession_id not in (None, profession.pk):
            continue
        price = discounted_price(original, discount)
        if price < result.price:
            result = CoursePrice(original, price, discount)
    return result


def course_price(profession):
    if not profession.is_sold_once:
        return best_price(profession, [])
    discounts = valid_discounts().filter(Q(profession__isnull=True) | Q(profession_id=profession.pk))
    return best_price(profession, list(discounts))


def discounted_courses(exclude_ids=(), limit=4):
    """Boş sahifa bloki: hozir çegirmadagi, hali sotib olinmagan kurslar."""
    discounts = list(valid_discounts())
    if not discounts:
        return []
    courses = Profession.objects.filter(
        is_paid=True, one_time_payment=True, one_time_price__gt=0, is_blocked=False, is_mandatory=False,
    ).exclude(pk__in=exclude_ids)
    if not any(d.profession_id is None for d in discounts):
        courses = courses.filter(pk__in=[d.profession_id for d in discounts])
    result = []
    for course in courses.order_by('-created_at'):
        course._sale = best_price(course, discounts)
        if course._sale.has_discount:
            result.append(course)
    # Tez tugaydiganlari oldinda, muddatsizlari oxirida.
    result.sort(key=lambda c: (c._sale.ends_at is None, c._sale.ends_at or 0))
    return result[:limit]


def attach_prices(professions):
    """Röyxat sahifalari uçun: barça kurs narxini bitta sörov bilan hisoblaydi."""
    professions = list(professions)
    discounts = list(valid_discounts()) if any(p.is_sold_once for p in professions) else []
    for profession in professions:
        profession._sale = best_price(profession, discounts)
    return professions
