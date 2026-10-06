# Acme Generative API — integration notes

Excerpt of the provider's documentation that matters for our integration.
Locally the provider is replaced by the simulator in `provider_mock/`, which
follows this document.

## Authentication

Every request carries `Authorization: Bearer <api key>`.

## Create a generation

```
POST /v1/generations
{
  "model": "flux-fast",
  "prompt": "a lighthouse at dawn",
  "num_outputs": 2,
  "webhook_url": "https://example.com/hooks/acme"
}
```

Responds `202 Accepted` with the generation object:

```json
{"id": "gen_3f1c...", "model": "flux-fast", "status": "queued",
 "output_urls": [], "error": null, "created_at": "2026-05-04T10:00:00+00:00"}
```

The call returns as soon as the generation is queued, normally well under a
second. The work itself takes from under a second to several minutes
depending on the model.

**Billing.** A generation is billed to our account when it is accepted (`202`).
Failed generations are credited back automatically. Generations cancelled
before the model started are not billed.

**Idempotency.** Send an `Idempotency-Key` header (any string up to 64
characters) to make creation safe to repeat. A repeated request with the same
key returns the original generation instead of creating a new one. Keys are
kept for 24 hours.

**Errors.**

| Status | Meaning | Retry? |
|---|---|---|
| 400 | Request rejected, e.g. `content_policy_violation` | No |
| 401 | Bad API key | No |
| 422 | Invalid parameters, e.g. `unknown_model` | No |
| 429 | Rate limited. `Retry-After` header gives seconds to wait | Yes, after the delay |
| 5xx | Temporary failure | Yes, with backoff |

## Get a generation

`GET /v1/generations/{id}` returns the current generation object. Statuses:
`queued`, `processing`, `succeeded`, `failed`, `canceled`.

## Cancel a generation

`POST /v1/generations/{id}/cancel`

- `200` with the generation object: the cancellation was accepted.
- `409` `already_finished`: the generation is already in a final status.

Cancellation is best-effort. If the model has already started, the generation
may still run to completion; in that case a `succeeded` (or `failed`) event is
delivered after the cancel call returned `200`, and the generation is billed
as usual. Otherwise a `canceled` event is delivered.

## Webhooks

If `webhook_url` is set, the provider POSTs an event on every status change:

```json
{
  "event_id": "evt_9a0b...",
  "generation_id": "gen_3f1c...",
  "status": "succeeded",
  "output_urls": ["https://cdn.acme-gen.example/gen_3f1c/0.png"],
  "error": null,
  "occurred_at": "2026-05-04T10:00:07.412+00:00"
}
```

`status` is one of `processing`, `succeeded`, `failed`, `canceled`.

Delivery guarantees:

- **At least once.** The same event (same `event_id`) may be delivered more
  than once.
- **No ordering.** Events for one generation may arrive in any order; use
  `occurred_at` if you need to order them.
- **Fast generations.** The first webhook may be sent before the response to
  `POST /v1/generations` has reached you.
- **Retries.** A delivery that times out (5 s) or gets a `5xx` response is
  retried up to three times over roughly 15 seconds. Any `2xx` or `4xx`
  response ends delivery of that event; `4xx` is treated as a permanent
  rejection.

**Signature.** Each delivery has an `X-Provider-Signature` header:
`sha256=` followed by the hex HMAC-SHA256 of the raw request body, keyed with
the webhook secret from the provider dashboard.
