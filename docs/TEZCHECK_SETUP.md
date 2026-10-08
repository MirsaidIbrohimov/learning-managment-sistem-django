# Tezcheck payment setup

## Environment values

Set these values in the server-side .env file. Never add the API token or webhook secret to frontend code or commit them.

- TEZCHECK_API_BASE_URL=https://api.tezcheck.uz/api/merchant/v1
- TEZCHECK_API_TOKEN: Tezcheck merchant API token.
- TEZCHECK_CASH_DESK_CODE: code for the cash desk enabled to accept payments.
- TEZCHECK_WEBHOOK_SECRET: signing secret shown when the webhook is registered.
- TEZCHECK_RETURN_URL: public HTTPS URL, for example https://your-domain.example/tezcheck/return/. Leave blank to use the LMS URL automatically.
- TEZCHECK_SIGN_REQUESTS=true
- TEZCHECK_LATE_GRACE_DAYS=5

In the Tezcheck dashboard, register the public HTTPS webhook URL:

https://your-domain.example/tezcheck/webhook/

Add the exact return URL to the cash desk's allowed return URL list. Both the webhook and return endpoints must be reachable from the public internet. A browser return is informational; only the signed webhook or a server-side status check confirms payment.

## Database and reconciliation

Deploy the code and apply migrations:

python manage.py migrate

Schedule this command every 10 minutes on the hosting platform to reconcile pending bills if webhook delivery was unavailable:

python manage.py sync_tezcheck_payments

The command checks pending bills that are at least five minutes old and safely ignores already finalized orders.

## Acceptance sequence

1. Configure Tezcheck credentials and register the webhook and return URLs.
2. Use Tezcheck's Test provider to check checkout, delayed return, repeated webhook delivery, failed payment, expiry, and refund handling.
3. Confirm test payments never update paid access; they are marked for review.
4. Switch the merchant configuration to live provider credentials and verify one small live payment before enabling the flow for students.

The payment flow currently charges the oldest recorded unpaid monthly period first. Contract students are directed to the existing administrator-managed process.
