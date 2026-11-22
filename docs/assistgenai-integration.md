# AssistGenAI invoice review

The AssistGenAI adapter accepts caller-supplied invoice and purchase order totals. It compares amounts in integer cents when currencies match and marks a currency mismatch for review. The operation is read-only and requires no database, model provider, invoice uploads, or WhatsApp access. Document extraction and purchase order lookup belong to separate workflows.

- `GET /api/assistgenai/v1/openapi.json` serves the contract.
- `POST /api/assistgenai/v1/invoice-review` accepts the comparison input and returns a decision and a signed variance in cents. A currency mismatch returns a null variance.
- Configure `ASSISTGENAI_INVOICE_SERVICE_TOKEN` on this service and in the AssistGenAI gateway. The gateway sends the token as an HTTP bearer credential. Generate one dedicated 32–128-character URL-safe token per environment and provision it outside source control. Until configured, the route returns HTTP 503.
- The gateway passes `X-Request-ID` for correlation. The service returns the ID without recording request contents.

Use synthetic invoice totals to verify the deployed route before enabling customer traffic.
