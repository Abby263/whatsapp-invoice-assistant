"""Regression checks for the hosted service adapter's auth and exact totals."""

from app import app


TOKEN = "fixture_token_for_invoice_reviews_only"
VALID = {
    "invoiceTotalCents": 13500,
    "purchaseOrderTotalCents": 12000,
    "invoiceCurrency": "CAD",
    "purchaseOrderCurrency": "CAD",
}
PATH = "/api/assistgenai/v1/invoice-review"


def test_connector_is_disabled_without_a_token(monkeypatch):
    monkeypatch.delenv("ASSISTGENAI_INVOICE_SERVICE_TOKEN", raising=False)
    assert app.test_client().post(PATH, json=VALID).status_code == 503


def test_review_scope_and_input_validation(monkeypatch):
    monkeypatch.setenv("ASSISTGENAI_INVOICE_SERVICE_TOKEN", TOKEN)
    client = app.test_client()
    assert client.post(PATH, json=VALID).status_code == 401
    headers = {"Authorization": f"Bearer {TOKEN}", "X-Request-ID": "invoice-smoke"}
    response = client.post(PATH, json=VALID, headers=headers)
    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == "invoice-smoke"
    assert response.json == {"decision": "needs_review", "reason": "amount_mismatch", "varianceCents": 1500}
    assert client.post(PATH, json={**VALID, "invoiceTotalCents": True}, headers=headers).status_code == 400
    assert client.post(PATH, data=b" " * 4097, content_type="application/json", headers=headers).status_code == 413
    match = client.post(PATH, json={**VALID, "invoiceTotalCents": 12000}, headers=headers)
    assert match.json == {"decision": "matched", "reason": "totals_match", "varianceCents": 0}
    mismatch = client.post(PATH, json={**VALID, "invoiceCurrency": "USD"}, headers=headers)
    assert mismatch.json == {"decision": "needs_review", "reason": "currency_mismatch", "varianceCents": None}
    assert client.get("/api/assistgenai/v1/openapi.json").json["paths"][PATH]["post"]["operationId"] == "reviewInvoiceTotals"
