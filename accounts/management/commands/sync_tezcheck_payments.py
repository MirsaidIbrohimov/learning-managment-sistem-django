from datetime import timedelta

from django.core.management.base import BaseCommand
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from accounts.models import TezCheckPaymentOrder
from accounts import inpay
from accounts.payment_gateways import fetch_bill
from accounts.tezcheck import TezCheckError
from accounts.tezcheck_views import _apply_successful_payment


class Command(BaseCommand):
    help = 'Kutilayotgan Tezcheck va inPAY to‘lovlarini API bilan solishtiradi.'

    def handle(self, *args, **options):
        gateways = []
        if settings.TEZCHECK_API_TOKEN and settings.TEZCHECK_CASH_DESK_CODE:
            gateways.append(TezCheckPaymentOrder.GATEWAY_TEZCHECK)
        if inpay.configured():
            gateways.append(TezCheckPaymentOrder.GATEWAY_INPAY)
        if not gateways:
            self.stderr.write(self.style.ERROR('Tezcheck ham, inPAY ham sozlanmagan.'))
            return

        cutoff = timezone.now() - timedelta(minutes=5)
        orders = TezCheckPaymentOrder.objects.filter(
            status=TezCheckPaymentOrder.STATUS_PENDING,
            bill_id__gt='',
            gateway__in=gateways,
            created_at__lte=cutoff,
        ).order_by('created_at')[:100]
        checked = confirmed = expired = errors = 0
        for order in orders:
            checked += 1
            try:
                response_data = fetch_bill(order.bill_id, gateway=order.gateway)
            except TezCheckError as exc:
                errors += 1
                TezCheckPaymentOrder.objects.filter(pk=order.pk).update(last_error=str(exc)[:500])
                continue

            bill = response_data.get('bill') or {}
            payment = response_data.get('payment') or {}
            if order.purpose == 'coins':
                from coin.payments import reconcile_coin_order
                reconcile_coin_order(order, response_data)
                order.refresh_from_db()
                confirmed += int(order.status == 'paid')
                expired += int(order.status in ('expired', 'cancelled'))
                errors += int(order.status == 'review')
                continue
            with transaction.atomic():
                locked = TezCheckPaymentOrder.objects.select_for_update().get(pk=order.pk)
                if locked.status != TezCheckPaymentOrder.STATUS_PENDING:
                    continue
                if bill.get('external_reference') != locked.external_reference:
                    locked.status = TezCheckPaymentOrder.STATUS_REVIEW
                    locked.last_error = 'To‘lov tizimidagi tashqi raqam LMS buyurtmasiga mos emas.'
                    locked.save(update_fields=['status', 'last_error', 'updated_at'])
                    errors += 1
                elif bill.get('paid') is True and payment.get('state') == 'succeeded':
                    _apply_successful_payment(locked, {
                        'amount_minor': payment.get('amount_minor'),
                        'currency': payment.get('currency'),
                        'environment': payment.get('environment'),
                        'payment_id': payment.get('id'),
                        'fee_minor': payment.get('fee_minor'),
                        'net_minor': payment.get('net_minor'),
                        'provider_code': payment.get('provider_code'),
                    })
                    if locked.status == TezCheckPaymentOrder.STATUS_PAID:
                        confirmed += 1
                    else:
                        errors += 1
                elif bill.get('state') in ('expired', 'revoked', 'exhausted', 'canceled'):
                    locked.status = (TezCheckPaymentOrder.STATUS_CANCELLED if bill.get('state') == 'canceled'
                                     else TezCheckPaymentOrder.STATUS_EXPIRED)
                    locked.last_error = f"{locked.get_gateway_display()} holati: {bill.get('state')}"
                    locked.save(update_fields=['status', 'last_error', 'updated_at'])
                    expired += 1

        self.stdout.write(self.style.SUCCESS(
            f'Tekshirildi: {checked}; tasdiqlandi: {confirmed}; muddati tugadi: {expired}; muammo: {errors}.'
        ))
