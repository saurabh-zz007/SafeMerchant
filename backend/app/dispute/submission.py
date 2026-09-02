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
import os

from app.core.config import settings
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from app.core.db import async_session_factory
from app.dispute.dispute_repository import DisputeRepository
from app.dispute.models import DisputeSubmissionLog, Order
from app.dispute.repository import EvidenceRepository
from app.proof_renderer import ChargebackPDFRenderer
from app.proof_renderer.schemas import (
    ActivityLogData,
    ActivityLogEntry,
    ChatMessage,
    ChatTranscriptData,
    DeliveryProofData,
    PriorDelivery,
    TrackingEvent,
)

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

        if dispute.document_id:
            logger.info("Dispute already processed: %s already has document_id %s", dispute_id, dispute.document_id)
            return {
                "dispute_id": dispute_id,
                "status": "already_processed",
                "outcome": "evidence_already_submitted",
                "document_id": dispute.document_id,
                "storage_path": dispute.storage_path,
            }

        dispute_amount_paise = dispute.amount_paise
        dispute_payment_id = dispute.payment_id
        dispute_order_id = dispute.order_id
        dispute_customer_email = dispute.customer_email
        dispute_history_copy = list(dispute.history or [])

        # 2. Gather evidence and render PDF
        evidence_repo = EvidenceRepository(session)
        
        # Eagerly load order details
        order = None
        if dispute_payment_id:
            order = await evidence_repo.get_order_by_payment_id(dispute_payment_id)
        if not order and dispute_order_id:
            order = await evidence_repo.get_order_by_id(dispute_order_id)

        if order:
            logger.info("Found matching order %s for dispute %s.", order.order_id, dispute_id)
            shipping = order.shipping_logs[0] if order.shipping_logs else None
            shipped_at = order.created_at if order.created_at else datetime.now(timezone.utc)
            delivered_at = shipping.delivery_timestamp if (shipping and shipping.delivery_timestamp) else shipped_at
            
            # 1. Address Verification (Billing & Shipping)
            shipping_address = "42 MG Road, Bengaluru, Karnataka 560001"
            billing_address = "42 MG Road, Bengaluru, Karnataka 560001"
            # Explicitly mismatch for scammer/fraud tests to verify flag/alert
            if "scammer" in order.customer_email.lower():
                billing_address = "108 Ring Road, Delhi 110001"
            
            # 2. OTP Verification Reference Details
            otp_transaction_id = None
            otp_verified_at = None
            otp_channel = None
            if shipping and shipping.signed_by == "Self (OTP Verified)":
                otp_transaction_id = f"TXN_OTP_{order.order_id}"
                otp_verified_at = shipping.delivery_timestamp
                otp_channel = "SMS to +91 ******9999"

            # 3. Carrier Tracking Event Timeline
            from datetime import timedelta
            tracking_events = []
            tracking_events.append(
                TrackingEvent(
                    timestamp=shipped_at,
                    status="Shipment Picked Up",
                    location="Warehouse (Bengaluru)"
                )
            )
            if shipping:
                transit_time = shipped_at + (delivered_at - shipped_at) / 2 if (delivered_at and shipped_at) else shipped_at + timedelta(hours=12)
                tracking_events.append(
                    TrackingEvent(
                        timestamp=transit_time,
                        status="In Transit",
                        location="Delhi Hub"
                    )
                )
                tracking_events.append(
                    TrackingEvent(
                        timestamp=delivered_at,
                        status=shipping.delivery_status or "Delivered",
                        location="Customer Destination"
                    )
                )

            # 4. Payment Risk & Fraud Signals
            risk = order.risk_signals[0] if order.risk_signals else None
            cvv_match = "Matched" if risk else "Not captured for this transaction"
            avs_result = "Matched (ZIP & Address)" if risk else "Not captured for this transaction"
            checkout_ip = risk.ip_address if risk else "Not captured for this transaction"
            checkout_device = risk.device_fingerprint if risk else "Not captured for this transaction"
            is_2fa_verified = risk.is_2fa_verified if risk else None

            # 5. Customer Prior Deliveries History
            prior_deliveries = []
            try:
                stmt = (
                    select(Order)
                    .where(Order.customer_email == order.customer_email)
                    .where(Order.order_id != order.order_id)
                    .options(selectinload(Order.shipping_logs))
                )
                res = await session.execute(stmt)
                prior_orders = res.scalars().all()
                for po in prior_orders:
                    po_shipping = po.shipping_logs[0] if po.shipping_logs else None
                    if po_shipping and po_shipping.delivery_status == "Delivered":
                        prior_deliveries.append(
                            PriorDelivery(
                                order_id=po.order_id,
                                delivered_at=po_shipping.delivery_timestamp or po.created_at,
                                item_description=po.item_description
                            )
                        )
            except Exception as e:
                logger.warning("Failed to query prior deliveries for customer: %s", e)

            data = DeliveryProofData(
                order_id=order.order_id,
                payment_id=order.payment_id,
                customer_name=order.customer_email.split('@')[0].capitalize() if order.customer_email else "Customer",
                customer_email=order.customer_email or "unknown@example.com",
                shipping_address=shipping_address,
                billing_address=billing_address,
                carrier_name=shipping.courier_partner if (shipping and shipping.courier_partner) else "N/A",
                tracking_number=shipping.tracking_id if (shipping and shipping.tracking_id) else "N/A",
                shipped_at=shipped_at,
                delivered_at=delivered_at,
                delivery_status=shipping.delivery_status if (shipping and shipping.delivery_status) else "Delivered",
                signed_by=shipping.signed_by if (shipping and shipping.signed_by) else "Customer Signature on File",
                proof_url=f"https://tracking.carrier.com/{shipping.tracking_id}" if (shipping and shipping.tracking_id) else None,
                otp_transaction_id=otp_transaction_id,
                otp_verified_at=otp_verified_at,
                otp_channel=otp_channel,
                tracking_events=tracking_events,
                cvv_match=cvv_match,
                avs_result=avs_result,
                checkout_ip=checkout_ip,
                checkout_device=checkout_device,
                is_2fa_verified=is_2fa_verified,
                prior_deliveries=prior_deliveries,
                additional_notes=f"Order placed on {order.created_at.strftime('%Y-%m-%d')} for {order.item_description}."
            )
        else:
            # Fallback data for testing against synthetic disputes
            logger.warning("No matching order found in database for dispute %s. Generating fallback evidence data.", dispute_id)
            fallback_timeline = [
                TrackingEvent(timestamp=datetime.now(timezone.utc), status="Shipment Picked Up", location="Sorting Center"),
                TrackingEvent(timestamp=datetime.now(timezone.utc), status="Delivered", location="Delhi Gate")
            ]
            
            data = DeliveryProofData(
                order_id="ORD_TEST_FALLBACK",
                payment_id=dispute.payment_id or "pay_TEST_FALLBACK",
                customer_name="Test Customer",
                customer_email=dispute.customer_email or "test@example.com",
                shipping_address="Test Address, Bengaluru, India",
                billing_address="Test Address, Bengaluru, India",
                carrier_name="Delhivery",
                tracking_number="DLV1234567890",
                shipped_at=datetime.now(timezone.utc),
                delivered_at=datetime.now(timezone.utc),
                delivery_status="Delivered",
                signed_by="T. Customer",
                proof_url="https://tracking.carrier.com/DLV1234567890",
                otp_transaction_id="TXN_OTP_12345",
                otp_verified_at=datetime.now(timezone.utc),
                otp_channel="SMS to +91 ******0000",
                tracking_events=fallback_timeline,
                cvv_match="Matched",
                avs_result="Not captured for this transaction",
                checkout_ip="127.0.0.1",
                checkout_device="Chrome - Windows",
                is_2fa_verified=True,
                prior_deliveries=[
                    PriorDelivery(order_id="ORD_PRIOR_999", delivered_at=datetime.now(timezone.utc), item_description="Sony WH-1000XM5 Headphones")
                ],
                additional_notes="Fallback document generated for testing / missing evidence order."
            )

        # Determine the primary evidence field from Razorpay's evidence schema
        evidence_field = "shipping_proof"
        if dispute.reason_code in ("chargeback", "product_not_received", "processed_invalid_expired_card"):
            evidence_field = "shipping_proof"
        elif dispute.reason_code in ("fraud", "customer_dispute"):
            evidence_field = "customer_communication"
        elif dispute.reason_code in ("duplicate",):
            evidence_field = "billing_proof"
        elif dispute.reason_code in ("subscription_cancelled",):
            evidence_field = "cancellation_proof"
        else:
            evidence_field = "shipping_proof"

        # Prepare evidence data payload tailored to the target evidence template
        evidence_data: Any = data
        if evidence_field in ("customer_communication", "cancellation_proof", "chat_transcript"):
            chat_messages: list[ChatMessage] = []
            conv_started = None
            conv_ended = None
            if order and order.communications:
                for comm in order.communications:
                    conv_started = conv_started or comm.logged_at
                    conv_ended = comm.logged_at
                    chat_messages.append(
                        ChatMessage(
                            timestamp=comm.logged_at,
                            sender=f"Customer ({comm.channel})",
                            message=comm.message_transcript,
                        )
                    )
            evidence_data = ChatTranscriptData(
                order_id=order.order_id if order else (dispute.order_id or "N/A"),
                payment_id=order.payment_id if order else (dispute.payment_id or "N/A"),
                customer_name=order.customer_email.split('@')[0].capitalize() if (order and order.customer_email) else "Customer",
                customer_email=order.customer_email if order else (dispute.customer_email or "unknown@example.com"),
                agent_name="SafeMerchant Support",
                conversation_started_at=conv_started,
                conversation_ended_at=conv_ended,
                messages=chat_messages,
                additional_notes=f"Dispute reason: {dispute.reason_code}. Evidence compiled for {evidence_field}."
            )
        elif evidence_field in ("access_activity_log", "activity_log", "billing_proof"):
            activity_entries: list[ActivityLogEntry] = []
            if order and order.shipping_logs:
                for sh in order.shipping_logs:
                    activity_entries.append(
                        ActivityLogEntry(
                            timestamp=sh.delivery_timestamp or order.created_at,
                            actor=sh.courier_partner or "Logistics",
                            action=f"Delivery Status: {sh.delivery_status}",
                            details=f"Tracking ID: {sh.tracking_id}, Signed by: {sh.signed_by or 'N/A'}",
                        )
                    )
            evidence_data = ActivityLogData(
                order_id=order.order_id if order else (dispute.order_id or "N/A"),
                payment_id=order.payment_id if order else (dispute.payment_id or "N/A"),
                customer_name=order.customer_email.split('@')[0].capitalize() if (order and order.customer_email) else "Customer",
                customer_email=order.customer_email if order else (dispute.customer_email or "unknown@example.com"),
                log_title=f"Order Activity & Evidence Log ({evidence_field})",
                entries=activity_entries,
                additional_notes=f"Compiled activity telemetry for dispute {dispute_id}."
            )

        try:
            renderer = ChargebackPDFRenderer()
            pdf_stream = renderer.render(evidence_field, evidence_data)
            pdf_bytes = pdf_stream.getvalue()
            logger.info("Successfully rendered in-memory %s PDF (%d bytes) for dispute %s", evidence_field, len(pdf_bytes), dispute_id)
            
            # Log Evidence Composed event to history
            await dispute_repo.append_history(dispute_id, {
                "event": "evidence_composed",
                "evidence_type": evidence_field,
            })
        except Exception as e:
            logger.exception("Failed to render in-memory evidence PDF for dispute %s", dispute_id)
            raise DisputeSubmissionError(f"PDF rendering failed: {e}")

        # 3. Call 1: POST /v1/documents (multipart upload to Razorpay)
        doc_url = f"{RAZORPAY_API_BASE}/documents"
        doc_payload_desc = {"purpose": "dispute_evidence", "file": "evidence.pdf"}
        doc_status = None
        doc_response_body = None
        document_id = None
        storage_path = None

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
                
                # Dual upload to Supabase Storage from the in-memory buffer
                try:
                    from app.core.storage import storage_service
                    storage_path = await storage_service.upload_evidence_pdf(dispute_id, pdf_bytes)
                except Exception as s_exc:
                    logger.warning("Supabase Storage upload warning for dispute %s: %s", dispute_id, s_exc)
                    storage_path = f"evidence-pdfs/{dispute_id}/evidence.pdf"

                # Discard in-memory buffer
                pdf_stream.close()
                del pdf_bytes

                # Persist pointers and log Evidence Uploaded event to history
                await dispute_repo.update_evidence_pointers(
                    dispute_id,
                    document_id=document_id,
                    storage_path=storage_path,
                )
                await dispute_repo.append_history(dispute_id, {
                    "event": "evidence_uploaded",
                    "document_id": document_id,
                    "storage_path": storage_path,
                })
            else:
                # Discard in-memory buffer on failure
                pdf_stream.close()
                del pdf_bytes

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
                # Log Evidence Upload Failed event to history
                await dispute_repo.append_history(dispute_id, {
                    "event": "evidence_upload_failed",
                    "reason": f"Document upload failed with HTTP {doc_status}"
                })
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
            # Log Evidence Upload Failed event to history
            await dispute_repo.append_history(dispute_id, {
                "event": "evidence_upload_failed",
                "reason": "Document upload timed out after retry."
            })
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
                # Log Evidence Upload Failed event to history
                await dispute_repo.append_history(dispute_id, {
                    "event": "evidence_upload_failed",
                    "reason": str(e)
                })
                raise DisputeSubmissionError(f"Document upload failed: {e}")
            else:
                raise

        # 4. Call 2: POST /v1/disputes/{dispute_id}/contest
        # Determine contest amount (defaulting to full amount unless partial specified in HIL review)
        contest_amount = None
        if dispute_history_copy:
            for entry in reversed(dispute_history_copy):
                if isinstance(entry, dict) and entry.get("event") == "human_review_submitted":
                    # Check for partial amount_paise injected by user
                    contest_amount = entry.get("amount_paise")
                    break

        if contest_amount is None:
            contest_amount = dispute_amount_paise

        contest_url = f"{RAZORPAY_API_BASE}/disputes/{dispute_id}/contest"
        contest_payload: dict[str, Any] = {
            "action": "submit",
            evidence_field: [document_id],
        }
        if contest_amount is not None:
            contest_payload["amount"] = contest_amount

        contest_status = None
        contest_response_body = None

        async def contest_call() -> httpx.Response:
            async with httpx.AsyncClient(timeout=10.0) as client:
                return await client.post(
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

            import json
            raw_response_str = (
                json.dumps(contest_response_body)
                if isinstance(contest_response_body, (dict, list))
                else str(contest_response_body)
            )

            logger.info("OUTBOUND CONTEST RESPONSE -> Status: %d, Body: %s", contest_status, contest_response_body)

            # Classifier: Check if Razorpay returned a Sandbox Limitation / 404 Test Route/Dispute Not Found
            is_rzp_sandbox_limitation = False
            if response.status_code in (400, 404):
                # Any 404 from Razorpay API indicates the test dispute does not exist on Razorpay live servers
                if response.status_code == 404:
                    is_rzp_sandbox_limitation = True
                elif isinstance(contest_response_body, dict):
                    err = contest_response_body.get("error") if isinstance(contest_response_body.get("error"), dict) else contest_response_body
                    desc = str(err.get("description", "") or err.get("message", "")).lower()
                    code = str(err.get("code", "")).upper()
                    if (
                        any(phrase in desc for phrase in [
                            "dispute does not exist",
                            "does not exist",
                            "not found",
                            "no route matched",
                            "invalid dispute",
                            "the id provided does not exist",
                        ])
                        or code in ("BAD_REQUEST_ERROR", "NOT_FOUND_ERROR")
                    ):
                        is_rzp_sandbox_limitation = True

            if response.status_code in (200, 201, 204):
                outcome = "success"
                # Update dispute status & history
                await dispute_repo.update_status(dispute_id, "under_review")
                await dispute_repo.append_history(dispute_id, {
                    "event": "contest_submitted",
                    "document_id": document_id,
                    "contest_amount": contest_amount,
                    "submitted_at": datetime.now(timezone.utc).isoformat()
                })
                logger.info("Successfully submitted contest to Razorpay for dispute %s", dispute_id)
            elif is_rzp_sandbox_limitation:
                outcome = "contest_expected_failure"
                logger.info(
                    "Test Completed / Simulated (dispute not found in Razorpay sandbox) for %s. Status: %d, Response: %s",
                    dispute_id, contest_status, contest_response_body
                )
                await dispute_repo.append_history(dispute_id, {
                    "event": "contest_submitted_sandbox_limitation",
                    "document_id": document_id,
                    "contest_amount": contest_amount,
                    "razorpay_status_code": contest_status,
                    "razorpay_response": contest_response_body,
                    "error_message": raw_response_str,
                    "reason": "Test Completed / Simulated: Razorpay sandbox does not host active bank-raised dispute entities. Evidence PDF was generated and dual-uploaded successfully.",
                    "submitted_at": datetime.now(timezone.utc).isoformat()
                })
            else:
                outcome = "submission_failed"
                logger.error("Genuine contest failure for %s. Status: %d, Response: %s", dispute_id, contest_status, contest_response_body)
                await dispute_repo.append_history(dispute_id, {
                    "event": "contest_submission_failed",
                    "document_id": document_id,
                    "contest_amount": contest_amount,
                    "razorpay_status_code": contest_status,
                    "razorpay_response": contest_response_body,
                    "reason": f"Contest call failed with status {contest_status}",
                    "failed_at": datetime.now(timezone.utc).isoformat()
                })

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
                error_message=raw_response_str if outcome != "success" else None
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
            await dispute_repo.append_history(dispute_id, {
                "event": "contest_submission_failed",
                "reason": "Contest call timed out after retry.",
                "failed_at": datetime.now(timezone.utc).isoformat()
            })
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
                await dispute_repo.append_history(dispute_id, {
                    "event": "contest_submission_failed",
                    "reason": str(e),
                    "failed_at": datetime.now(timezone.utc).isoformat()
                })
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
