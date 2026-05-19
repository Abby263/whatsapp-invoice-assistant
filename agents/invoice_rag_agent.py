"""
Agentic RAG retrieval for approved invoice and receipt data.

The upload workflow keeps unapproved WhatsApp files out of invoices, items, and
embeddings. This retriever intentionally reads only those finalized tables, so
pending or rejected uploads cannot affect answers.
"""

import logging
import re
import time
from typing import Any, Dict, List, Optional, Union

from sqlalchemy import text

from constants.vector_search_configs import DEFAULT_VECTOR_SEARCH_CONFIG
from utils.vector_utils import get_embedding_generator

logger = logging.getLogger(__name__)


class InvoiceRAGAgent:
    """
    Retrieval-augmented agent for querying finalized invoice data.

    The retrieval plan combines:
    - full-document invoice embeddings
    - line-item embeddings
    - keyword fallback over invoice/item text

    All retrieval branches are scoped by user_id and read only finalized invoice
    rows, which are created after validation, extraction, and HITL approval.
    """

    def __init__(self, llm_factory=None):
        self.start_time = 0.0
        self.llm_factory = llm_factory
        self.default_limit = int(DEFAULT_VECTOR_SEARCH_CONFIG.get("max_results", 10))
        logger.info("InvoiceRAGAgent initialized")

    async def process(
        self,
        query_text: str,
        user_id: Union[str, int],
        conversation_id: str = None,
        db_session=None,
        **kwargs,
    ) -> Dict[str, Any]:
        """Retrieve approved receipt/invoice evidence for a natural-language query."""

        self.start_time = time.time()
        plan = self._plan_retrieval(query_text, kwargs.get("limit"))
        logger.info("[WORKFLOW STEP] Starting agentic RAG process for query: %s", query_text)

        try:
            query_embedding = self._generate_query_embedding(query_text)
            if query_embedding:
                logger.info(
                    "[WORKFLOW STEP] Generated query embedding with %s dimensions",
                    len(query_embedding),
                )
            else:
                logger.warning(
                    "[WORKFLOW STEP] Query embedding unavailable; using keyword-only RAG fallback"
                )

            results = await self._perform_vector_search(
                query_embedding,
                user_id,
                db_session,
                query_text=query_text,
                plan=plan,
            )

            execution_time = round(time.time() - self.start_time, 2)
            if results:
                vendors = sorted(
                    {str(item.get("vendor") or "Unknown") for item in results}
                )
                logger.info(
                    "[WORKFLOW STEP] Agentic RAG completed in %.2f seconds with %s results from vendors: %s",
                    execution_time,
                    len(results),
                    ", ".join(vendors[:5]),
                )
            else:
                logger.info("[WORKFLOW STEP] Agentic RAG completed with no results")

            return {
                "success": True,
                "results": results,
                "execution_time": execution_time,
                "row_count": len(results),
                "source": "agentic_rag",
                "retrieval_plan": plan,
                "checks": {
                    "user_scoped": True,
                    "approved_data_only": True,
                    "finalized_tables_only": ["invoices", "items", "invoice_embeddings"],
                    "uses_pending_uploads": False,
                },
            }
        except Exception as exc:
            logger.exception("[WORKFLOW STEP] Error processing agentic RAG query: %s", exc)
            return {
                "success": False,
                "error": str(exc),
                "results": [],
                "source": "agentic_rag",
                "retrieval_plan": plan,
            }

    async def _perform_vector_search(
        self,
        query_embedding: Optional[List[float]],
        user_id: Union[str, int],
        db_session=None,
        query_text: str = "",
        plan: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Run document-vector, item-vector, and keyword retrieval branches."""

        start_time = time.time()
        plan = plan or self._plan_retrieval(query_text)
        user_id_value = self._coerce_user_id(user_id)
        should_close_session = False

        if db_session is None:
            from database.connection import SessionLocal

            db_session = SessionLocal()
            should_close_session = True
            logger.debug("Created database session for agentic RAG")

        try:
            embedding_param = self._format_embedding(query_embedding)
            results: List[Dict[str, Any]] = []

            if embedding_param:
                results.extend(
                    self._search_invoice_embeddings(
                        db_session,
                        user_id_value,
                        embedding_param,
                        plan["limit"],
                    )
                )
                results.extend(
                    self._search_item_embeddings(
                        db_session,
                        user_id_value,
                        embedding_param,
                        plan["limit"],
                    )
                )

            results.extend(
                self._search_keywords(
                    db_session,
                    user_id_value,
                    query_text,
                    plan["limit"],
                )
            )

            combined = self._combine_results(results, query_text=query_text)
            logger.info(
                "[WORKFLOW STEP] Agentic RAG retrieval branches returned %s raw rows, %s after ranking in %.2f seconds",
                len(results),
                len(combined),
                time.time() - start_time,
            )
            return combined[: plan["limit"]]
        except Exception as exc:
            logger.exception("[WORKFLOW STEP] Error performing agentic RAG search: %s", exc)
            return []
        finally:
            if should_close_session:
                db_session.close()
                logger.debug("Closed database session for agentic RAG")

    async def _perform_item_vector_search(
        self,
        query_embedding: List[float],
        user_id: Union[str, int],
        db_session=None,
    ) -> List[Dict[str, Any]]:
        """Backward-compatible wrapper around the combined RAG search."""

        return await self._perform_vector_search(query_embedding, user_id, db_session)

    def _generate_query_embedding(self, query_text: str) -> Optional[List[float]]:
        if not query_text or not query_text.strip():
            return None
        try:
            return get_embedding_generator().generate_embedding(query_text)
        except Exception as exc:
            logger.warning("Could not generate query embedding: %s", exc)
            return None

    def _search_invoice_embeddings(
        self,
        session,
        user_id: int,
        embedding_param: str,
        limit: int,
    ) -> List[Dict[str, Any]]:
        sql = text(
            """
            SELECT
                inv.id AS invoice_id,
                inv.invoice_number,
                inv.vendor,
                inv.invoice_date,
                inv.total_amount,
                inv.currency,
                inv.file_url,
                emb.content_text,
                1 - (emb.embedding <=> CAST(:query_embedding AS vector)) AS relevance_score
            FROM invoice_embeddings emb
            JOIN invoices inv ON emb.invoice_id = inv.id
            WHERE
                emb.user_id = :user_id
                AND inv.user_id = :user_id
                AND emb.embedding IS NOT NULL
                AND emb.embedding_type = 'invoice_full'
            ORDER BY emb.embedding <=> CAST(:query_embedding AS vector)
            LIMIT :limit
            """
        )
        rows = session.execute(
            sql,
            {
                "user_id": user_id,
                "query_embedding": embedding_param,
                "limit": limit,
            },
        )
        return [
            self._row_to_result(row, result_type="invoice_vector", match_field="document")
            for row in rows
        ]

    def _search_item_embeddings(
        self,
        session,
        user_id: int,
        embedding_param: str,
        limit: int,
    ) -> List[Dict[str, Any]]:
        sql = text(
            """
            SELECT
                it.id AS item_id,
                inv.id AS invoice_id,
                inv.invoice_number,
                inv.vendor,
                inv.invoice_date,
                inv.total_amount,
                inv.currency,
                inv.file_url,
                it.description,
                it.quantity,
                it.unit_price,
                it.total_price,
                it.item_category,
                1 - (it.description_embedding <=> CAST(:query_embedding AS vector)) AS relevance_score
            FROM items it
            JOIN invoices inv ON it.invoice_id = inv.id
            WHERE
                inv.user_id = :user_id
                AND it.description_embedding IS NOT NULL
            ORDER BY it.description_embedding <=> CAST(:query_embedding AS vector)
            LIMIT :limit
            """
        )
        rows = session.execute(
            sql,
            {
                "user_id": user_id,
                "query_embedding": embedding_param,
                "limit": limit,
            },
        )
        return [
            self._row_to_result(row, result_type="item_vector", match_field="item")
            for row in rows
        ]

    def _search_keywords(
        self,
        session,
        user_id: int,
        query_text: str,
        limit: int,
    ) -> List[Dict[str, Any]]:
        terms = self._keyword_terms(query_text)
        if not terms:
            return []

        params: Dict[str, Any] = {"user_id": user_id, "limit": limit}
        conditions = []
        for index, term_value in enumerate(terms[:6]):
            param_name = f"term_{index}"
            params[param_name] = f"%{term_value}%"
            conditions.append(
                " OR ".join(
                    [
                        f"inv.vendor ILIKE :{param_name}",
                        f"inv.invoice_number ILIKE :{param_name}",
                        f"COALESCE(inv.notes, '') ILIKE :{param_name}",
                        f"COALESCE(it.description, '') ILIKE :{param_name}",
                        f"CAST(inv.raw_data AS text) ILIKE :{param_name}",
                    ]
                )
            )

        sql = text(
            f"""
            SELECT
                it.id AS item_id,
                inv.id AS invoice_id,
                inv.invoice_number,
                inv.vendor,
                inv.invoice_date,
                inv.total_amount,
                inv.currency,
                inv.file_url,
                it.description,
                it.quantity,
                it.unit_price,
                it.total_price,
                it.item_category,
                0.75 AS relevance_score
            FROM invoices inv
            LEFT JOIN items it ON it.invoice_id = inv.id
            WHERE
                inv.user_id = :user_id
                AND (({" ) OR ( ".join(conditions)}))
            ORDER BY inv.invoice_date DESC NULLS LAST, inv.created_at DESC
            LIMIT :limit
            """
        )
        rows = session.execute(sql, params)
        return [
            self._row_to_result(row, result_type="keyword", match_field="text")
            for row in rows
        ]

    def _row_to_result(
        self,
        row: Any,
        result_type: str,
        match_field: str,
    ) -> Dict[str, Any]:
        mapping = row._mapping if hasattr(row, "_mapping") else row

        def get_value(name: str, default: Any = None) -> Any:
            if isinstance(mapping, dict):
                return mapping.get(name, default)
            return getattr(mapping, name, default)

        invoice_date = get_value("invoice_date")
        relevance = get_value("relevance_score")
        try:
            relevance = round(float(relevance), 3) if relevance is not None else None
        except (TypeError, ValueError):
            relevance = None

        return {
            "result_type": result_type,
            "match_field": match_field,
            "invoice_id": str(get_value("invoice_id")),
            "item_id": str(get_value("item_id")) if get_value("item_id") is not None else None,
            "invoice_number": get_value("invoice_number"),
            "vendor": get_value("vendor"),
            "date": invoice_date.isoformat() if hasattr(invoice_date, "isoformat") else invoice_date,
            "total_amount": get_value("total_amount"),
            "currency": get_value("currency"),
            "file_url": get_value("file_url"),
            "description": get_value("description"),
            "quantity": get_value("quantity"),
            "unit_price": get_value("unit_price"),
            "total_price": get_value("total_price"),
            "item_category": get_value("item_category"),
            "content_text": get_value("content_text"),
            "relevance_score": relevance,
            "similarity": relevance,
        }

    def _combine_results(
        self,
        results: List[Dict[str, Any]],
        query_text: str = "",
    ) -> List[Dict[str, Any]]:
        """Deduplicate, boost exact text matches, and rank retrieved evidence."""

        combined: Dict[str, Dict[str, Any]] = {}
        terms = self._keyword_terms(query_text)

        for result in results:
            key = result.get("item_id") or f"invoice:{result.get('invoice_id')}"
            if not key:
                continue

            candidate = dict(result)
            candidate["match_types"] = [candidate.get("result_type")]
            candidate["ranking_score"] = self._ranking_score(candidate, terms)

            existing = combined.get(key)
            if existing is None:
                combined[key] = candidate
                continue

            existing["match_types"] = sorted(
                set(existing.get("match_types", [])) | set(candidate.get("match_types", []))
            )
            if candidate["ranking_score"] > existing.get("ranking_score", 0):
                candidate["match_types"] = existing["match_types"]
                combined[key] = candidate

        ranked = list(combined.values())
        ranked.sort(
            key=lambda item: (
                item.get("ranking_score", 0),
                str(item.get("date") or ""),
            ),
            reverse=True,
        )
        return ranked

    def _ranking_score(self, result: Dict[str, Any], terms: List[str]) -> float:
        score = result.get("relevance_score")
        try:
            score = float(score) if score is not None else 0.0
        except (TypeError, ValueError):
            score = 0.0

        searchable = " ".join(
            str(result.get(key) or "")
            for key in ("vendor", "invoice_number", "description", "content_text", "item_category")
        ).lower()
        exact_matches = sum(1 for term_value in terms if term_value in searchable)
        if exact_matches:
            score += min(0.35, exact_matches * 0.08)
        if "keyword" in (result.get("match_types") or [result.get("result_type")]):
            score += 0.05
        return round(score, 4)

    def _plan_retrieval(self, query_text: str, limit: Optional[int] = None) -> Dict[str, Any]:
        return {
            "query": query_text,
            "branches": ["invoice_vector", "item_vector", "keyword"],
            "limit": self._coerce_limit(limit),
            "dedupe": "item_or_invoice",
            "ranking": "vector_relevance_plus_keyword_boost",
            "approval_gate": "finalized_invoice_rows_only",
        }

    def _keyword_terms(self, query_text: str) -> List[str]:
        stop_words = {
            "about",
            "all",
            "and",
            "any",
            "did",
            "for",
            "from",
            "have",
            "how",
            "invoice",
            "invoices",
            "last",
            "me",
            "my",
            "of",
            "on",
            "receipt",
            "receipts",
            "show",
            "spend",
            "spent",
            "the",
            "what",
            "when",
            "where",
            "with",
        }
        terms = []
        for token in re.findall(r"[A-Za-z0-9][A-Za-z0-9_-]{2,}", query_text.lower()):
            if token not in stop_words and token not in terms:
                terms.append(token)
        return terms

    def _format_embedding(self, embedding: Optional[List[float]]) -> Optional[str]:
        if not embedding:
            return None
        return "[" + ",".join(str(float(value)) for value in embedding) + "]"

    def _coerce_user_id(self, user_id: Union[str, int]) -> int:
        try:
            return int(str(user_id))
        except (TypeError, ValueError):
            raise ValueError("Agentic RAG requires an integer user_id for scoped retrieval")

    def _coerce_limit(self, limit: Optional[int]) -> int:
        try:
            value = int(limit or self.default_limit)
        except (TypeError, ValueError):
            value = self.default_limit
        return max(1, min(value, 20))
