from types import SimpleNamespace

import pytest

from agents import invoice_rag_agent
from agents.invoice_rag_agent import InvoiceRAGAgent


class FakeEmbeddingGenerator:
    def __init__(self, embedding=None):
        self.embedding = embedding

    def generate_embedding(self, text):
        return self.embedding


class FakeSession:
    def __init__(self):
        self.calls = []

    def execute(self, statement, params):
        sql = str(statement)
        self.calls.append({"sql": sql, "params": params})
        assert params["user_id"] == 7

        if "FROM invoice_embeddings" in sql:
            return [
                SimpleNamespace(
                    invoice_id=10,
                    invoice_number="INV-10",
                    vendor="Acme Office",
                    invoice_date=None,
                    total_amount=120.0,
                    currency="USD",
                    file_url="https://example.com/receipt-10",
                    content_text="Acme printer ink and copy paper",
                    relevance_score=0.78,
                )
            ]

        if "FROM items it" in sql and "description_embedding" in sql:
            return [
                SimpleNamespace(
                    item_id=20,
                    invoice_id=10,
                    invoice_number="INV-10",
                    vendor="Acme Office",
                    invoice_date=None,
                    total_amount=120.0,
                    currency="USD",
                    file_url="https://example.com/receipt-10",
                    description="Printer ink cartridge",
                    quantity=1,
                    unit_price=33.0,
                    total_price=33.0,
                    item_category="expense",
                    relevance_score=0.84,
                )
            ]

        if "FROM invoices inv" in sql and "LEFT JOIN items" in sql:
            return [
                SimpleNamespace(
                    item_id=21,
                    invoice_id=11,
                    invoice_number="INV-11",
                    vendor="Paper Mart",
                    invoice_date=None,
                    total_amount=45.0,
                    currency="USD",
                    file_url="https://example.com/receipt-11",
                    description="Copy paper",
                    quantity=3,
                    unit_price=15.0,
                    total_price=45.0,
                    item_category="expense",
                    relevance_score=0.75,
                )
            ]

        return []


@pytest.mark.asyncio
async def test_agentic_rag_searches_invoice_item_and_keyword_branches(monkeypatch):
    monkeypatch.setattr(
        invoice_rag_agent,
        "get_embedding_generator",
        lambda: FakeEmbeddingGenerator([0.1, 0.2, 0.3]),
    )
    session = FakeSession()
    agent = InvoiceRAGAgent()

    result = await agent.process("Find printing paper expenses", "7", db_session=session)

    assert result["success"] is True
    assert result["source"] == "agentic_rag"
    assert result["checks"]["approved_data_only"] is True
    assert result["checks"]["uses_pending_uploads"] is False
    assert result["retrieval_plan"]["branches"] == ["invoice_vector", "item_vector", "keyword"]
    assert len(result["results"]) == 3
    assert {call["params"]["user_id"] for call in session.calls} == {7}
    assert any("invoice_embeddings" in call["sql"] for call in session.calls)
    assert any("description_embedding" in call["sql"] for call in session.calls)
    assert any("LEFT JOIN items" in call["sql"] for call in session.calls)


@pytest.mark.asyncio
async def test_agentic_rag_uses_keyword_fallback_without_embeddings(monkeypatch):
    monkeypatch.setattr(
        invoice_rag_agent,
        "get_embedding_generator",
        lambda: FakeEmbeddingGenerator(None),
    )
    session = FakeSession()
    agent = InvoiceRAGAgent()

    result = await agent.process("Find paper expenses", 7, db_session=session)

    assert result["success"] is True
    assert len(result["results"]) == 1
    assert result["results"][0]["result_type"] == "keyword"
    assert not any("invoice_embeddings" in call["sql"] for call in session.calls)
    assert not any("description_embedding" in call["sql"] for call in session.calls)
