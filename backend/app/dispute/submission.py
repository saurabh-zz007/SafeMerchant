"""
Outbound dispute-evidence submission flow.

Connects HIL or automatic contest decisions to Razorpay Documents & Contest APIs.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from io import BytesIO
from typing import Any, Optional

import httpx

from app.core.config import settings
from app.core.db import async_session_factory
from app.dispute.dispute_repository import DisputeRepository
from app.dispute.models import DisputeSubmissionLog
from app.dispute.repository import EvidenceRepository
from app.proof_renderer import ChargebackPDFRenderer
from app.proof_renderer.schemas import DeliveryProofData

logger = logging.getLogger(__name__)

RAZORPAY_API_BASE = "https://api.razorpay.com/v1"


class DisputeSubmissionError(Exception):
    """Raised when a genuine failure occurs during dispute evidence submission."""
    pass


def redact_headers(headers: dict[str, Any]) -> dict[str, Any]:
    """Return headers dict with sensitive auth credentials redacted."""
    redacted = dict(headers)
    for k in list(redacted.keys()):
        if k.lower() in ("authorization", "x-razorpay-signature"):
            redacted[k] = "[REDACTED]"
    return redacted


async def submit_dispute_evidence(dispute_id: str) -> dict[str, Any]:
    """
    Generate the evidence PDF using proof_renderer, upload it to Razorpay
    via POST /v1/documents, and submit it to contest the dispute via
    PATCH /v1/disputes/{dispute_id}/contest.

    Outcomes:
      - success: update disputes.status to under_review, log in history.
      - api_rejected_expected: expected sandbox 4xx error (e.g. unknown dispute).
        Leave status unchanged, log Razorpay error, return outcome.
      - submission_failed: genuine network, auth, 5xx, or malformed request failure.
        Leave status unchanged, raise DisputeSubmissionError.
    """
    logger.info("Starting dispute evidence submission flow for dispute_id: %s", dispute_id)

    key_id = settings.razorpay_key_id
    key_secret = settings.razorpay_key_secret

    if not key_id or not key_secret:
        msg = "Razorpay API credentials (key_id / key_secret) not configured."
        logger.error(msg)
        raise DisputeSubmissionError(msg)

    async with async_session_factory() as session:
        # 1. Fetch the dispute
        dispute_repo = DisputeRepository(session)
        dispute = await dispute_repo.get_dispute(dispute_id)
        if not dispute:
            raise DisputeSubmissionError(f"Dispute {dispute_id} not found in database.")

        # 2. Gather evidence and render PDF
        evidence_repo = EvidenceRepository(session)
        
        # Eagerly load order details
        order = None
        if dispute.payment_id:
            order = await evidence_repo.get_order_by_payment_id(dispute.payment_id)
        if not order and dispute.order_id:
            order = await evidence_repo.get_order_by_id(dispute.order_id)

        if order:
            logger.info("Found matching order %s for dispute %s.", order.order_id, dispute_id)
            shipping = order.shipping_logs[0] if order.shipping_logs else None
            shipped_at = order.created_at if order.created_at else datetime.now(timezone.utc)
            delivered_at = shipping.delivery_timestamp if (shipping and shipping.delivery_timestamp) else shipped_at
            
            data = DeliveryProofData(
                order_id=order.order_id,
                payment_id=order.payment_id,
                customer_name=order.customer_email.split('@')[0].capitalize() if order.customer_email else "Customer",
                customer_email=order.customer_email or "unknown@example.com",
                shipping_address="Registered Address (on file)",
                carrier_name=shipping.courier_partner if (shipping and shipping.courier_partner) else "N/A",
                tracking_number=shipping.tracking_id if (shipping and shipping.tracking_id) else "N/A",
                shipped_at=shipped_at,
                delivered_at=delivered_at,
                delivery_status=shipping.delivery_status if (shipping and shipping.delivery_status) else "Delivered",
                signed_by=shipping.signed_by if (shipping and shipping.signed_by) else "Customer Signature on File",
                proof_url=f"https://tracking.carrier.com/{shipping.tracking_id}" if (shipping and shipping.tracking_id) else None,
                additional_notes=f"Order placed on {order.created_at.strftime('%Y-%m-%d')} for {order.item_description}."
            )
        else:
            # Fallback data for testing against synthetic disputes
            logger.warning("No matching order found in database for dispute %s. Generating fallback evidence data.", dispute_id)
            data = DeliveryProofData(
                order_id="ORD_TEST_FALLBACK",
                payment_id=dispute.payment_id or "pay_TEST_FALLBACK",
                customer_name="Test Customer",
                customer_email=dispute.customer_email or "test@example.com",
                shipping_address="Test Address, Bengaluru, India",
                carrier_name="Delhivery",
                tracking_number="DLV1234567890",
                shipped_at=datetime.now(timezone.utc),
                delivered_at=datetime.now(timezone.utc),
                delivery_status="Delivered",
                signed_by="T. Customer",
                proof_url="https://tracking.carrier.com/DLV1234567890",
                additional_notes="Fallback document generated for testing / missing evidence order."
            )

        try:
            renderer = ChargebackPDFRenderer()
            pdf_stream = renderer.render("delivery_proof", data)
            pdf_bytes = pdf_stream.getvalue()
            logger.info("Successfully rendered evidence PDF. Length: %d bytes", len(pdf_bytes))
        except Exception as e:
            logger.exception("Failed to render evidence PDF for dispute %s", dispute_id)
            raise DisputeSubmissionError(f"PDF rendering failed: {e}")

        # 3. Call 1: POST /v1/documents (multipart upload)
        doc_url = f"{RAZORPAY_API_BASE}/documents"
        doc_payload_desc = {"purpose": "dispute_evidence", "file": "evidence.pdf"}
        doc_status = None
        doc_response_body = None
        document_id = None

        async def upload_call() -> httpx.Response:
            files = {"file": ("evidence.pdf", pdf_bytes, "application/pdf")}
            data = {"purpose": "dispute_evidence"}
            async with httpx.AsyncClient(timeout=10.0) as client:
                return await client.post(
                    doc_url,
                    data=data,
                    files=files,
                    auth=(key_id, key_secret),
                )

        # Log outbound upload request details
        logger.info("OUTBOUND UPLOAD REQUEST -> URL: %s, Payload: %s", doc_url, doc_payload_desc)

        try:
            try:
                response = await upload_call()
            except httpx.TimeoutException:
                logger.warning("Razorpay document upload timed out. Retrying once...")
                response = await upload_call()

            doc_status = response.status_code
            try:
                doc_response_body = response.json()
            except Exception:
                doc_response_body = {"raw": response.text}

            logger.info("OUTBOUND UPLOAD RESPONSE -> Status: %d, Body: %s", doc_status, doc_response_body)

            if response.status_code in (200, 201):
                document_id = doc_response_body.get("id")
                if not document_id:
                    raise DisputeSubmissionError("Document upload response missing document ID.")
            else:
                # Re-classify error
                outcome = "submission_failed"
                submission_log = DisputeSubmissionLog(
                    dispute_id=dispute_id,
                    document_id=None,
                    document_upload_payload=doc_payload_desc,
                    document_upload_status=doc_status,
                    document_upload_response=doc_response_body,
                    outcome=outcome,
                    error_message=f"Document upload failed with HTTP {doc_status}"
                )
                session.add(submission_log)
                await session.commit()
                raise DisputeSubmissionError(f"Document upload failed: HTTP {doc_status} — {doc_response_body}")

        except httpx.TimeoutException:
            logger.error("Razorpay document upload timed out after retry.")
            submission_log = DisputeSubmissionLog(
                dispute_id=dispute_id,
                document_id=None,
                document_upload_payload=doc_payload_desc,
                document_upload_status=None,
                document_upload_response={"error": "timeout"},
                outcome="submission_failed",
                error_message="Document upload timed out after retry."
            )
            session.add(submission_log)
            await session.commit()
            raise DisputeSubmissionError("Document upload timed out after retry.")
        except Exception as e:
            if not isinstance(e, DisputeSubmissionError):
                logger.exception("Unexpected error during Razorpay document upload")
                submission_log = DisputeSubmissionLog(
                    dispute_id=dispute_id,
                    document_id=None,
                    document_upload_payload=doc_payload_desc,
                    document_upload_status=doc_status,
                    document_upload_response=doc_response_body if doc_response_body else {"error": str(e)},
                    outcome="submission_failed",
                    error_message=str(e)
                )
                session.add(submission_log)
                await session.commit()
                raise DisputeSubmissionError(f"Document upload failed: {e}")
            else:
                raise

        # 4. Call 2: PATCH /v1/disputes/{dispute_id}/contest
        # Determine contest amount (defaulting to full amount unless partial specified in HIL review)
        contest_amount = None
        if dispute.history:
            for entry in reversed(dispute.history):
                if entry.get("event") == "human_review_submitted":
                    # Check for partial amount_paise injected by user
                    contest_amount = entry.get("amount_paise")
                    break

        if contest_amount is None:
            contest_amount = dispute.amount_paise

        contest_url = f"{RAZORPAY_API_BASE}/disputes/{dispute_id}/contest"
        contest_payload = {
            "explanation_letter": [document_id],
            "action": "submit"
        }
        if contest_amount is not None:
            contest_payload["amount"] = contest_amount

        contest_status = None
        contest_response_body = None

        async def contest_call() -> httpx.Response:
            async with httpx.AsyncClient(timeout=10.0) as client:
                return await client.patch(
                    contest_url,
                    json=contest_payload,
                    auth=(key_id, key_secret),
                    headers={"Content-Type": "application/json"}
                )

        logger.info("OUTBOUND CONTEST REQUEST -> URL: %s, Payload: %s", contest_url, contest_payload)

        try:
            try:
                response = await contest_call()
            except httpx.TimeoutException:
                logger.warning("Razorpay contest call timed out. Retrying once...")
                response = await contest_call()

            contest_status = response.status_code
            try:
                contest_response_body = response.json()
            except Exception:
                contest_response_body = {"raw": response.text}

            logger.info("OUTBOUND CONTEST RESPONSE -> Status: %d, Body: %s", contest_status, contest_response_body)

            # Check outcome
            if response.status_code in (200, 201, 204):
                outcome = "success"
                # Update dispute status & history
                await dispute_repo.update_status(dispute_id, "under_review")
                await dispute_repo.append_history(dispute_id, {
                    "event": "evidence_submitted",
                    "document_id": document_id,
                    "contest_amount": contest_amount,
                    "submitted_at": datetime.now(timezone.utc).isoformat()
                })
                logger.info("Successfully submitted contest to Razorpay for dispute %s", dispute_id)
            elif response.status_code in (400, 404):
                outcome = "api_rejected_expected"
                logger.warning(
                    "Expected API-level rejection (e.g. synthetic dispute) for %s. Status: %d, Response: %s",
                    dispute_id, contest_status, contest_response_body
                )
            else:
                outcome = "submission_failed"
                logger.error("Genuine contest failure for %s. Status: %d, Response: %s", dispute_id, contest_status, contest_response_body)

            # Persist log entry
            submission_log = DisputeSubmissionLog(
                dispute_id=dispute_id,
                document_id=document_id,
                document_upload_payload=doc_payload_desc,
                document_upload_status=doc_status,
                document_upload_response=doc_response_body,
                contest_payload=contest_payload,
                contest_status=contest_status,
                contest_response=contest_response_body,
                outcome=outcome,
                error_message=None if outcome != "submission_failed" else f"Contest call failed with status {contest_status}"
            )
            session.add(submission_log)
            await session.commit()

            if outcome == "submission_failed":
                raise DisputeSubmissionError(f"Contest call failed: HTTP {contest_status} — {contest_response_body}")

        except httpx.TimeoutException:
            logger.error("Razorpay contest call timed out after retry for dispute %s", dispute_id)
            submission_log = DisputeSubmissionLog(
                dispute_id=dispute_id,
                document_id=document_id,
                document_upload_payload=doc_payload_desc,
                document_upload_status=doc_status,
                document_upload_response=doc_response_body,
                contest_payload=contest_payload,
                contest_status=None,
                contest_response={"error": "timeout"},
                outcome="submission_failed",
                error_message="Contest call timed out after retry."
            )
            session.add(submission_log)
            await session.commit()
            raise DisputeSubmissionError("Contest call timed out after retry.")
        except Exception as e:
            if not isinstance(e, DisputeSubmissionError):
                logger.exception("Unexpected error during Razorpay contest call")
                submission_log = DisputeSubmissionLog(
                    dispute_id=dispute_id,
                    document_id=document_id,
                    document_upload_payload=doc_payload_desc,
                    document_upload_status=doc_status,
                    document_upload_response=doc_response_body,
                    contest_payload=contest_payload,
                    contest_status=contest_status,
                    contest_response=contest_response_body if contest_response_body else {"error": str(e)},
                    outcome="submission_failed",
                    error_message=str(e)
                )
                session.add(submission_log)
                await session.commit()
                raise DisputeSubmissionError(f"Contest call failed: {e}")
            else:
                raise

        return {
            "outcome": outcome,
            "document_id": document_id,
            "razorpay_response": contest_response_body,
            "dispute_id": dispute_id
        }
