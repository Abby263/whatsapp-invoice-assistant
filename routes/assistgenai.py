"""Authenticated service API for AssistGenAI's invoice review connector."""

from __future__ import annotations

import hmac
import os
import re
from uuid import uuid4

from flask import Blueprint, Response, jsonify, request
from pydantic import BaseModel, ConfigDict, Field, ValidationError

bp = Blueprint("assistgenai", __name__, url_prefix="/api/assistgenai/v1")
MAX_REQUEST_BYTES = 4096
REVIEW_PATH = "/api/assistgenai/v1/invoice-review"


class ReviewInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    invoiceTotalCents: int = Field(ge=0, le=1_000_000_000_000)
    purchaseOrderTotalCents: int = Field(ge=0, le=1_000_000_000_000)
    invoiceCurrency: str = Field(pattern=r"^[A-Z]{3}$")
    purchaseOrderCurrency: str = Field(pattern=r"^[A-Z]{3}$")


@bp.get("/openapi.json")
def openapi() -> Response:
    return jsonify({
        "openapi": "3.1.1",
        "info": {"title": "Invoice Exception Review", "version": "1.0.0"},
        "servers": [{"url": "/"}],
        "components": {"securitySchemes": {"serviceBearer": {"type": "http", "scheme": "bearer"}}},
        "paths": {
            REVIEW_PATH: {"post": {
                "operationId": "reviewInvoiceTotals",
                "summary": "Compare invoice and purchase order totals",
                "security": [{"serviceBearer": []}],
                "requestBody": {"required": True, "content": {"application/json": {
                    "schema": ReviewInput.model_json_schema(),
                }}},
                "responses": {
                    "200": {"description": "Review decision", "content": {"application/json": {
                        "schema": {
                            "type": "object",
                            "additionalProperties": False,
                            "required": ["decision", "reason", "varianceCents"],
                            "properties": {
                                "decision": {"enum": ["matched", "needs_review"]},
                                "reason": {"enum": ["totals_match", "amount_mismatch", "currency_mismatch"]},
                                "varianceCents": {"type": ["integer", "null"]},
                            },
                        },
                    }}},
                    "400": {"description": "Invalid comparison input"},
                    "401": {"description": "Service credential required"},
                    "413": {"description": "Request body exceeds 4096 bytes"},
                    "415": {"description": "Send application/json"},
                    "503": {"description": "Connector is disabled"},
                },
            }},
        },
    })


@bp.post("/invoice-review")
def review_invoice() -> Response:
    request_id = request.headers.get("X-Request-ID", "")
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", request_id):
        request_id = uuid4().hex

    def respond(payload: dict, status: int = 200) -> Response:
        response = jsonify(payload)
        response.status_code = status
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Request-ID"] = request_id
        if status == 401:
            response.headers["WWW-Authenticate"] = "Bearer"
        return response

    secret = os.environ.get("ASSISTGENAI_INVOICE_SERVICE_TOKEN", "")
    if not re.fullmatch(r"[A-Za-z0-9_-]{32,128}", secret):
        return respond({"error": "Invoice review connector is disabled"}, 503)
    supplied = request.headers.get("Authorization", "")
    if not supplied.isascii() or not hmac.compare_digest(supplied, f"Bearer {secret}"):
        return respond({"error": "Service credential required"}, 401)
    if request.mimetype != "application/json":
        return respond({"error": "Send application/json"}, 415)
    if request.content_length is not None and request.content_length > MAX_REQUEST_BYTES:
        return respond({"error": "Request body exceeds 4096 bytes"}, 413)
    body = request.stream.read(MAX_REQUEST_BYTES + 1)
    if len(body) > MAX_REQUEST_BYTES:
        return respond({"error": "Request body exceeds 4096 bytes"}, 413)
    try:
        invoice = ReviewInput.model_validate_json(body)
    except ValidationError:
        return respond({"error": "Invalid comparison input"}, 400)

    if invoice.invoiceCurrency != invoice.purchaseOrderCurrency:
        return respond({"decision": "needs_review", "reason": "currency_mismatch", "varianceCents": None})
    variance = invoice.invoiceTotalCents - invoice.purchaseOrderTotalCents
    return respond({
        "decision": "needs_review" if variance else "matched",
        "reason": "amount_mismatch" if variance else "totals_match",
        "varianceCents": variance,
    })
