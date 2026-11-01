# Subscription Architecture (Revo-managed Astra)

This is the commercial path: the customer pays Revo, not OpenAI. Revo holds the
OpenAI key and meters usage through a backend gateway. The Revit add-in and the
local Python engine never see the OpenAI key.

## Plans

| Plan | Monthly | Yearly (10% off) | Seats |
| --- | ---: | ---: | --- |
| Personal | $35 | $378 | 1 |
| Commercial | $80 | $864 | Up to 3 |
| Enterprise | $250 | $2,700 | Organization-wide |

The Subscription page in the workspace shows these plans, a monthly/yearly
toggle and the yearly monthly-equivalent. Checkout is deliberately not connected
yet; selecting a plan does not charge the customer.

## Client side in this repository

Implemented:

- `provider = "astra_subscription"`.
- `reconstruction/astra_subscription.py` calls:
  - `REVOAI_ASTRA_GATEWAY_URL`
  - `REVOAI_SUBSCRIPTION_TOKEN`
- `POST <gateway>/v1/astra/plan` with scan metadata/segmentation and a bearer
  subscription token.
- Typed errors:
  - `SUBSCRIPTION_REQUIRED` (`-32029`)
  - `SUBSCRIPTION_QUOTA_EXCEEDED` (`-32030`)
  - `AI_PROVIDER_FAILED` (`-32028`)
- The returned plan uses the same validation and preview path as file/Astra
  plans.

Not implemented yet:

- Sign-in/device authorization UI.
- Secure token persistence (DPAPI or OS credential store).
- Subscription checkout, Stripe/payment webhooks, plan entitlements.
- Usage metering, quotas, invoices and admin console.
- Gateway backend itself.

## Backend contract

The Revo service must expose an authenticated endpoint:

```http
POST /v1/astra/plan
Authorization: Bearer <subscription-token>
Content-Type: application/json

{
  "client": "RevoAI.Revit",
  "capability": "bim-plan",
  "context": {
    "scanId": "...",
    "units": { "source": "meters" },
    "bounds": { "min": [...], "max": [...] },
    "pointCount": {...},
    "segmentation": {
      "method": "geometric-plane-baseline/1",
      "summary": {...},
      "elements": [...]
    }
  }
}
```

Success:

```json
{ "plan": { "levels": [], "floors": [], "walls": [] } }
```

The backend must:

1. Authenticate the token and check subscription status.
2. Check quota/usage and rate limits.
3. Call OpenAI `gpt-6-astra` with the OpenAI key server-side.
4. Meter input/output tokens and attribute them to the subscriber.
5. Return the plan or a typed 401/402/429/5xx error.
6. Avoid logging customer scan geometry or secrets beyond the documented audit
   policy.

## Security requirements

- Never ship the OpenAI key in the add-in, config or repository.
- Keep subscription tokens short-lived and scoped.
- Use TLS.
- Log request IDs and usage, not full scan geometry, by default.
- Require customer permission for uploading scan context.
- Provide a clear deletion/retention policy.

## Recommended next steps

1. Choose the backend stack and auth provider.
2. Implement subscription checkout and entitlement state.
3. Implement `/v1/astra/plan` and usage metering.
4. Add device-code or browser sign-in to the add-in.
5. Store the token with Windows DPAPI and pass it to the engine process.
6. Add quota/usage UI in Project setup.
7. Add payment, cancellation, refund and support flows.
8. Add a live integration test that never uses a real customer scan.

The direct `astra` provider with `OPENAI_API_KEY` remains an advanced/BYO option
for development and enterprise deployments.
