"""
FastAPI REST routes for the dispute feature.

Endpoints:
  POST /webhook                       — Receive Razorpay dispute webhooks
  GET  /disputes                      — List historical disputes (paginated)
  POST /disputes/{dispute_id}/review  — Submit HITL review decision & resume graph
  GET  /health                        — Health check
"""


import asyncio
import hashlib
import hmac
import logging
import time
from datetime import datetime, timezone
from typing import Any
from sqlalchemy import text

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, status
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.db import async_session_factory
from app.dispute.dispute_repository import DisputeRepository
from app.dispute.metrics_repository import MetricsRepository
from app.dispute.schemas.review import DisputeListItem, ReviewDecision
from app.dispute.schemas.webhook import DisputeWebhookEvent
from app.dispute.service import dispute_service
from app.dispute.websocket import manager
from app.dispute import metrics_service
from app.dispute.models import Dispute
from app.dispute.submission import submit_dispute_evidence

logger = logging.getLogger(__name__)
router = APIRouter()


# ── Helpers ──────────────────────────────────────────────────────────


def _get_graph(request: Request):
    """Retrieve the compiled graph from app.state (set during lifespan)."""
    graph = getattr(request.app.state, "graph", None)
    if graph is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Dispute graph not initialised — server is starting up.",
        )
    return graph


def _make_config(dispute_id: str) -> dict[str, Any]:
    """Build the LangGraph config with the dispute as the thread_id."""
    return {"configurable": {"thread_id": dispute_id}}


def _build_auto_decision_explanation(
    state_values: dict[str, Any],
    gate_action: str | None,
    outcome: str,
) -> dict[str, Any]:
    """Build a comprehensive, rule-based decision explanation context for automated outcomes."""
    from app.core.config import settings

    score = state_values.get("winnability_score", 0.0)
    amount = state_values.get("disputed_amount_inr", 0)
    legitimacy = state_values.get("customer_legitimacy_signal", False)
    legitimacy_reasoning = state_values.get("legitimacy_reasoning") or ""
    triage_reasoning = state_values.get("triage_reasoning") or ""
    recommended = state_values.get("recommended_action") or gate_action or outcome
    risk_factors = state_values.get("risk_factors") or []
    draft_letter = (
        state_values.get("draft_response_letter")
        or state_values.get("verified_explanation_letter")
        or state_values.get("draft_explanation_letter")
    )
    refund_id = state_values.get("refund_id")
    refund_status = state_values.get("refund_status")
    existing_rationale = state_values.get("auto_decision_rationale")
    rules_triggered = list(state_values.get("rules_triggered") or [])

    score_pct = f"{score:.0%}" if score is not None else "N/A"

    if not rules_triggered:
        if outcome == "auto_refund" or gate_action == "auto_refund":
            rules_triggered = [
                "Customer legitimacy signal confirmed (genuine claim / lost transit / merchant defect)",
                f"Disputed amount (₹{amount:,}) within auto-refund threshold (<= ₹{settings.auto_refund_amount_ceiling_inr:,})",
            ]
            if refund_id:
                rules_triggered.append(f"Razorpay Refund API executed (Refund ID: {refund_id}, Status: {refund_status})")
        elif outcome == "accept_loss" or gate_action == "accept_loss":
            rules_triggered = [
                f"Winnability score ({score_pct}) below viable defense threshold (< 30%)",
                "Insufficient merchant documentation or high representment loss risk",
                "Economic non-viability: cost of defense exceeds expected recovery value",
            ]
        elif outcome == "auto_submit" or gate_action == "auto_submit":
            rules_triggered = [
                f"High-confidence winnability score ({score_pct} >= {settings.auto_submit_score_threshold:.0%})",
                f"Disputed amount (₹{amount:,}) within auto-contest ceiling (<= ₹{settings.auto_submit_amount_ceiling_inr:,})",
                "Complete evidentiary proof package compiled (delivery verification, transcript, ledger)",
            ]

    auto_rationale = existing_rationale
    if not auto_rationale:
        if outcome == "auto_refund" or gate_action == "auto_refund":
            auto_rationale = (
                f"**Automated Decision:** Refund automatically issued to customer.\n\n"
                f"**Rule Rationale:**\n"
                f"- **Customer Legitimacy:** Verified genuine claim ({legitimacy_reasoning or 'Legitimate customer claim detected by triage'}).\n"
                f"- **Amount Threshold:** Disputed amount of ₹{amount:,} is within the merchant's automatic refund ceiling (₹{settings.auto_refund_amount_ceiling_inr:,}).\n"
                f"- **Action:** Bypassed manual review queue and executed immediate refund via Razorpay API to maintain customer trust and eliminate chargeback penalties."
            )
        elif outcome == "accept_loss" or gate_action == "accept_loss":
            auto_rationale = (
                f"**Automated Decision:** Dispute loss automatically accepted (no representment).\n\n"
                f"**Rule Rationale:**\n"
                f"- **Winnability Assessment:** Calculated score of {score_pct} indicates low probability of reversal.\n"
                f"- **Economic Viability:** Contesting this claim would incur operational overhead and potential arbitration fees greater than the disputed amount (₹{amount:,}).\n"
                f"- **Triage Summary:** {triage_reasoning or 'Merchant records lack definitive proof of fulfillment or delivery confirmation.'}\n"
                f"- **Action:** Loss accepted to preserve merchant chargeback standing and avoid dispute filing penalties."
            )
        elif outcome == "auto_submit" or gate_action == "auto_submit":
            auto_rationale = (
                f"**Automated Decision:** Evidence automatically submitted for representment.\n\n"
                f"**Rule Rationale:**\n"
                f"- **Confidence Score:** Winnability score of {score_pct} meets or exceeds the automated submission threshold ({settings.auto_submit_score_threshold:.0%}).\n"
                f"- **Amount Ceiling:** Disputed amount of ₹{amount:,} is within the low-risk automated ceiling (₹{settings.auto_submit_amount_ceiling_inr:,}).\n"
                f"- **Evidence Summary:** {triage_reasoning or 'Merchant fulfilled order with verifiable tracking and proof of delivery.'}\n"
                f"- **Action:** Auto-generated defense package queued for Razorpay submission without human bottleneck."
            )
        else:
            auto_rationale = triage_reasoning or f"Automated outcome '{outcome}' applied by rule engine."

    return {
        "decision_type": "automated",
        "gate_action": gate_action,
        "outcome": outcome,
        "winnability_score": score,
        "recommended_action": recommended,
        "customer_legitimacy_signal": legitimacy,
        "legitimacy_reasoning": legitimacy_reasoning,
        "triage_reasoning": triage_reasoning,
        "auto_decision_rationale": auto_rationale,
        "rules_triggered": rules_triggered,
        "risk_factors": risk_factors,
        "draft_response_letter": draft_letter,
        "refund_id": refund_id,
        "refund_status": refund_status,
        "disputed_amount_inr": amount,
    }


# ── Background processing ────────────────────────────────────────────


async def process_dispute_and_broadcast(
    event: DisputeWebhookEvent,
    dispute_id: str,
    compiled_graph,
) -> None:
    config = _make_config(dispute_id)
    dispute_entity = event.payload.dispute.entity

    # Safeguard idempotency check before running the LangGraph workflow
    async with async_session_factory() as session:
        repo = DisputeRepository(session)
        existing = await repo.get_dispute(dispute_id)
        if existing:
            phase = (existing.phase or "").lower()
            if (phase in ("chargeback", "contested") and existing.status in ("under_review", "resolved")) or existing.document_id:
                logger.info("Dispute already processed: %s", dispute_id)
                return

    try:
        # ==========================================
        # 🥩 THE MEAT (LangGraph - ZERO DB Connections)
        # ==========================================
        error_msg = None
        is_paused = False
        graph_state = None
        
        try:
            async for update in dispute_service.stream_dispute(event, compiled_graph, config):
                await manager.broadcast_system_event({
                    "event": "node_update",
                    "dispute_id": dispute_id,
                    **update,
                })

            graph_state = await compiled_graph.aget_state(config)
            is_paused = bool(graph_state.next)
            
        except Exception as exc:
            logger.exception("Background processing failed for dispute %s", dispute_id)
            error_msg = str(exc)

        # ==========================================
        # 🍞 BOTTOM BUN (Fast DB Update - 1 Connection)
        # ==========================================
        async with async_session_factory() as session:
            repo = DisputeRepository(session)
            
            if error_msg:
                # Handle Error State
                await repo.update_status(dispute_id, "error")
                await repo.append_history(dispute_id, {
                    "event": "execution_error",
                    "error": error_msg,
                })
                await session.commit()
                
                await manager.broadcast_system_event({
                    "event": "execution_error",
                    "dispute_id": dispute_id,
                    "error": error_msg,
                })
                
            elif is_paused:
                # Handle HITL Paused State
                paused_node = graph_state.next[0] if graph_state.next else "unknown"
                logger.info("Dispute %s paused at interrupt: %s", dispute_id, paused_node)
                
                state_values = _safe_serialise(graph_state.values)
                review_context = {
                    "paused_node": paused_node,
                    "recommended_action": state_values.get("recommended_action"),
                    "gate_action": state_values.get("gate_action") or paused_node,
                    "winnability_score": state_values.get("winnability_score"),
                    "risk_factors": state_values.get("risk_factors") or [],
                    "triage_reasoning": state_values.get("triage_reasoning"),
                    "customer_legitimacy_signal": state_values.get("customer_legitimacy_signal"),
                    "legitimacy_reasoning": state_values.get("legitimacy_reasoning"),
                    "human_review_reason": state_values.get("human_review_reason"),
                    "draft_summary": state_values.get("draft_summary"),
                    "draft_response_letter": (
                        state_values.get("draft_response_letter")
                        or state_values.get("verified_explanation_letter")
                        or state_values.get("draft_explanation_letter")
                    ),
                    "draft_explanation_letter": state_values.get("draft_explanation_letter"),
                    "verified_explanation_letter": state_values.get("verified_explanation_letter"),
                    "verification_report": state_values.get("verification_report"),
                }
                
                await repo.update_status(dispute_id, "awaiting_review", review_context=review_context)
                await repo.append_history(dispute_id, {
                    "event": "human_review_required",
                    "paused_node": paused_node,
                    "data": review_context,
                })
                await session.commit()
                
                await manager.broadcast_system_event({
                    "event": "human_review_required",
                    "dispute_id": dispute_id,
                    "paused_node": paused_node,
                    "data": state_values,
                })
                
            else:
                state_values = _safe_serialise(graph_state.values) if graph_state else {}
                gate_action = state_values.get("gate_action")
                case_resolution = state_values.get("case_resolution")

                # Specific granular outcome: auto_refund | auto_submit | accept_loss
                outcome = gate_action if gate_action in ("auto_refund", "auto_submit", "accept_loss") else {
                    "resolved_contested": "auto_submit",
                    "resolved_refunded": "auto_refund",
                    "resolved_accepted_loss": "accept_loss",
                }.get(case_resolution or "", "open")

                # Generate automated decision rationale & rule triggers
                review_context = _build_auto_decision_explanation(state_values, gate_action, outcome)

                final_status = "under_review" if case_resolution == "resolved_contested" else "resolved"
                job_enqueued = False
                
                # Enqueue asynchronous evidence generation job if contested
                if case_resolution == "resolved_contested":
                    try:
                        job = await repo.create_evidence_job(dispute_id)
                        await repo.append_history(dispute_id, {
                            "event": "job_queued",
                            "job_id": job.id,
                            "queued_at": datetime.now(timezone.utc).isoformat(),
                        })
                        job_enqueued = True
                        logger.info("Enqueued evidence job #%d for dispute %s upon completion", job.id, dispute_id)
                    except Exception as exc:
                        logger.exception("Failed to enqueue evidence job for dispute %s: %s", dispute_id, exc)

                await repo.update_status(
                    dispute_id,
                    final_status,
                    case_resolution=case_resolution,
                    outcome=outcome,
                    gate_action=gate_action,
                    review_context=review_context,
                )
                await repo.append_history(dispute_id, {
                    "event": "execution_completed",
                    "data": {
                        "gate_action": gate_action,
                        "case_resolution": case_resolution,
                        "outcome": outcome,
                        "review_context": review_context,
                    }
                })
                await session.commit()

                if job_enqueued:
                    from app.dispute.worker import evidence_worker
                    evidence_worker.notify()

                await manager.broadcast_system_event({
                    "event": "execution_completed",
                    "dispute_id": dispute_id,
                    "data": {
                        "gate_action": gate_action,
                        "case_resolution": case_resolution,
                        "outcome": outcome,
                        "review_context": review_context,
                    }
                })
                
                metrics_outcome = {"resolved_contested": "won", "resolved_refunded": "lost", 
                           "resolved_accepted_loss": "accepted_loss"}.get(case_resolution or "", "open")
                
                try:
                    await metrics_service.on_dispute_resolved(
                        dispute_id=dispute_id,
                        outcome=metrics_outcome,
                        amount_paise=dispute_entity.amount or 0,
                    )
                except Exception as m_exc:
                    logger.warning("Metrics update failed for dispute %s: %s", dispute_id, m_exc)

    except Exception as global_exc:
        logger.exception("Unhandled global exception in process_dispute_and_broadcast for dispute %s: %s", dispute_id, global_exc)
        try:
            async with async_session_factory() as session:
                repo = DisputeRepository(session)
                await repo.update_status(dispute_id, "error")
                await repo.append_history(dispute_id, {
                    "event": "execution_error",
                    "error": str(global_exc),
                })
                await session.commit()

            await manager.broadcast_system_event({
                "event": "execution_error",
                "dispute_id": dispute_id,
                "error": str(global_exc),
            })
        except Exception as inner_err:
            logger.exception("Fatal failure recording error boundary for dispute %s: %s", dispute_id, inner_err)

async def resume_dispute_and_broadcast(
    dispute_id: str,
    compiled_graph,
) -> None:
    """Resume a paused graph after HITL review and broadcast updates.

    Called as a background task from the review endpoint.
    """
    config = _make_config(dispute_id)

    try:
        async for update in dispute_service.stream_resume(compiled_graph, config):
            await manager.broadcast_system_event({
                "event": "node_update",
                "dispute_id": dispute_id,
                **update,
            })

        # Check final state
        graph_state = await compiled_graph.aget_state(config)

        if graph_state.next:
            # Still paused (shouldn't normally happen after accept/reject)
            paused_node = graph_state.next[0]
            logger.warning(
                "Dispute %s still paused after resume at: %s",
                dispute_id, paused_node,
            )
            async with async_session_factory() as session:
                repo = DisputeRepository(session)
                await repo.update_status(dispute_id, "awaiting_review")
        else:
            # 1. Serialize the final LangGraph memory state
            state_values = _safe_serialise(graph_state.values)
            gate_action = state_values.get("gate_action")
            case_resolution = state_values.get("case_resolution")

            final_status = "under_review" if case_resolution == "resolved_contested" else "resolved"
            job_enqueued = False
            async with async_session_factory() as session:
                repo = DisputeRepository(session)
                
                # Enqueue asynchronous evidence generation job if contested
                if case_resolution == "resolved_contested":
                    try:
                        job = await repo.create_evidence_job(dispute_id)
                        from datetime import datetime, timezone
                        await repo.append_history(dispute_id, {
                            "event": "job_queued",
                            "job_id": job.id,
                            "queued_at": datetime.now(timezone.utc).isoformat(),
                        })
                        job_enqueued = True
                        logger.info("Enqueued evidence job #%d for dispute %s after HIL accept", job.id, dispute_id)
                    except Exception as exc:
                        logger.exception("Failed to enqueue evidence job for dispute %s: %s", dispute_id, exc)

                # Determine granular outcome for post-review resolution
                outcome = {
                    "resolved_contested": "auto_submit",
                    "resolved_refunded": "refund_review",
                    "resolved_accepted_loss": "accept_loss",
                }.get(case_resolution or "", "open")
                # Preserve existing review context and append reviewer decision
                dispute_obj = await repo.get_dispute(dispute_id)
                post_review_ctx = dict(dispute_obj.review_context or {}) if dispute_obj and dispute_obj.review_context else {}
                user_decision = state_values.get("user_decision") or {}
                post_review_ctx.update({
                    "gate_action": gate_action,
                    "outcome": outcome,
                    "reviewer_decision": user_decision.get("action"),
                    "reviewer_note": user_decision.get("reason"),
                })

                await repo.update_status(
                    dispute_id,
                    final_status,
                    case_resolution=case_resolution,
                    outcome=outcome,
                    gate_action=gate_action,
                    review_context=post_review_ctx,
                )
                
                # 2. Inject the LangGraph decisions into the history log!
                await repo.append_history(dispute_id, {
                    "event": "execution_completed_after_review",
                    "data": {
                        "gate_action": gate_action,
                        "case_resolution": case_resolution,
                        "outcome": outcome,
                        "review_context": post_review_ctx,
                    }
                })
                await session.commit()

            if job_enqueued:
                from app.dispute.worker import evidence_worker
                evidence_worker.notify()

            # 3. Broadcast the decisions to the real-time dashboard
            await manager.broadcast_system_event({
                "event": "execution_completed",
                "dispute_id": dispute_id,
                "data": {
                    "gate_action": gate_action,
                    "case_resolution": case_resolution,
                    "outcome": outcome,
                    "review_context": post_review_ctx,
                }
            })

            # 4. Trigger background metrics update
            # Fetch dispute to get amount_paise for metrics
            async with async_session_factory() as session:
                repo = DisputeRepository(session)
                dispute = await repo.get_dispute(dispute_id)
                amt = dispute.amount_paise if dispute else 0

            metrics_outcome = {"resolved_contested": "won", "resolved_refunded": "lost",
                       "resolved_accepted_loss": "accepted_loss"}.get(
                           case_resolution or "", "open")
            await metrics_service.on_dispute_resolved(
                dispute_id=dispute_id,
                outcome=metrics_outcome,
                amount_paise=amt or 0,
            )

    except Exception as exc:
        logger.exception("Resume failed for dispute %s", dispute_id)

        async with async_session_factory() as session:
            repo = DisputeRepository(session)
            await repo.update_status(dispute_id, "error")
            await repo.append_history(dispute_id, {
                "event": "resume_error",
                "error": str(exc),
            })

        await manager.broadcast_system_event({
            "event": "execution_error",
            "dispute_id": dispute_id,
            "error": str(exc),
        })


def _safe_serialise(obj: Any) -> Any:
    """Best-effort JSON-safe serialisation of graph state values."""
    if isinstance(obj, dict):
        return {k: _safe_serialise(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_safe_serialise(v) for v in obj]
    if hasattr(obj, "isoformat"):
        return obj.isoformat()
    try:
        import json
        json.dumps(obj)
        return obj
    except (TypeError, ValueError):
        return str(obj)


# ── Routes ───────────────────────────────────────────────────────────


@router.get("/health", tags=["system"])
async def health_check():
    """Liveness probe."""
    return {"status": "healthy", "service": "safemerchant-risk-agent"}

@router.delete(
    "/admin/reset",
    status_code=status.HTTP_200_OK,
    tags=["admin"],
    summary="Clear all disputes and broadcast UI refresh",
)
async def reset_system_database():
    """
    Clears all dispute records from the PostgreSQL database using the 
    async session, then broadcasts a WebSocket event to refresh the UI.
    """
    # 1. Open the async session just like your GET endpoint
    async with async_session_factory() as session:
        await session.execute(text("""
            TRUNCATE TABLE 
                disputes, 
                dispute_events, 
                dispute_audit_log, 
                dispute_metrics_daily, 
                dispute_breakdowns,
                checkpoints,
                checkpoint_blobs,
                checkpoint_writes
            RESTART IDENTITY CASCADE;
        """))
        await session.commit()

    # 2. Broadcast the reset event to connected Flutter clients
    await manager.broadcast_system_event({
        "event": "database_reset",
        "action": "refresh_ui",
    })

    # 3. Return success response
    return {
        "status": "success",
        "message": "Database wiped and frontend refresh triggered."
    }


@router.post(
    "/webhook",
    status_code=status.HTTP_202_ACCEPTED,
    tags=["disputes"],
    summary="Receive Razorpay payment.dispute.created webhook",
)
async def receive_dispute_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
):
    """
    Ingests a Razorpay dispute webhook after validating HMAC-SHA256 signature,
    broadcasts a *dispute_received* event to all connected dashboards, and
    starts the LangGraph pipeline as a background task.

    Returns **202 Accepted** immediately. Real-time progress is pushed
    to clients connected to ``/ws/dashboard``.
    """
    t_start = time.perf_counter()
    raw_body = await request.body()
    signature = request.headers.get("X-Razorpay-Signature") or request.headers.get("x-razorpay-signature")
    secret = settings.razorpay_webhook_secret

    if not signature or not secret:
        logger.warning("Rejecting webhook: missing signature header or webhook secret not set.")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing X-Razorpay-Signature header or secret not configured",
        )

    t_sig_start = time.perf_counter()
    expected_sig = hmac.new(
        secret.encode("utf-8"),
        raw_body,
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(expected_sig, signature):
        logger.warning("Rejecting webhook: HMAC-SHA256 signature mismatch.")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid webhook signature",
        )
    t_sig_ms = (time.perf_counter() - t_sig_start) * 1000

    try:
        event = DisputeWebhookEvent.model_validate_json(raw_body)
    except Exception as exc:
        logger.warning("Malformed dispute webhook JSON payload: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Malformed webhook payload: {exc}",
        )

    if event.event != "payment.dispute.created":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported event type: {event.event}",
        )

    # Extract identifiers and entities from the nested payload
    dispute_entity = event.payload.dispute.entity
    payment_entity = event.payload.payment.entity
    dispute_id = dispute_entity.id
    order_id = payment_entity.order_id or "UNKNOWN_ORDER"
    webhook_payload = event.model_dump(mode="json")
    respond_by_dt = (
        datetime.fromtimestamp(dispute_entity.respond_by, tz=timezone.utc)
        if dispute_entity.respond_by
        else None
    )

    # 0. Idempotency Check & Synchronous Persistence (Single DB Session)
    t_db_start = time.perf_counter()
    async with async_session_factory() as session:
        repo = DisputeRepository(session)
        existing_dispute = await repo.get_dispute(dispute_id)
        if existing_dispute:
            phase = (existing_dispute.phase or "").lower()
            if phase in ("chargeback", "contested") or existing_dispute.document_id:
                logger.info("Dispute already processed: %s", dispute_id)
                return JSONResponse(
                    status_code=status.HTTP_200_OK,
                    content={
                        "status": "already_processed",
                        "dispute_id": dispute_id,
                        "message": "Dispute already processed",
                    },
                )

        compiled_graph = _get_graph(request)

        metrics_repo = MetricsRepository(session)
        await metrics_repo.record_event(
            dispute_id=dispute_id,
            event_type="webhook_received",
            payload=webhook_payload,
        )

        await repo.create_or_update_dispute(
            dispute_id=dispute_id,
            webhook_payload=webhook_payload,
            amount_paise=dispute_entity.amount,
            amount_deducted=dispute_entity.amount_deducted,
            respond_by=respond_by_dt,
            reason_code=dispute_entity.reason_code,
            customer_email=payment_entity.email,
            payment_id=payment_entity.id,
            order_id=order_id,
            phase=dispute_entity.phase,
            status="processing",
        )
    t_db_ms = (time.perf_counter() - t_db_start) * 1000

    # 1. Trigger incremental daily metrics update in background
    t_bg_start = time.perf_counter()
    asyncio.create_task(
        metrics_service.on_dispute_ingested(
            dispute_id=dispute_id,
            webhook_payload=webhook_payload,
            amount_paise=dispute_entity.amount,
        )
    )

    # 2. Broadcast dispute_received with FULL core fields so frontend never shows 'Unknown'
    t_ws_start = time.perf_counter()
    now_iso = datetime.now(timezone.utc).isoformat()
    await manager.broadcast_system_event({
        "event": "dispute_received",
        "dispute_id": dispute_id,
        "order_id": order_id,
        "payment_id": payment_entity.id,
        "customer_email": payment_entity.email or "Customer",
        "amount_paise": dispute_entity.amount,
        "amount_deducted": dispute_entity.amount_deducted or 0,
        "reason_code": dispute_entity.reason_code,
        "phase": dispute_entity.phase,
        "status": "processing",
        "created_at": now_iso,
        "updated_at": now_iso,
    })
    t_ws_ms = (time.perf_counter() - t_ws_start) * 1000

    # 3. Offload the heavy LangGraph pipeline to a background task
    asyncio.create_task(
        process_dispute_and_broadcast(
            event,
            dispute_id,
            compiled_graph,
        )
    )
    t_bg_ms = (time.perf_counter() - t_bg_start) * 1000
    t_total_ms = (time.perf_counter() - t_start) * 1000

    logger.info(
        "[WEBHOOK TIMING] dispute_id=%s | total=%.2fms | sig=%.2fms | db_upsert=%.2fms | ws_broadcast=%.2fms | bg_spawn=%.2fms",
        dispute_id, t_total_ms, t_sig_ms, t_db_ms, t_ws_ms, t_bg_ms,
    )

    # 4. Return immediately
    return {
        "dispute_id": dispute_id,
        "status": "accepted",
        "message": "Dispute received — processing in background.",
    }


# ── Historical Disputes ──────────────────────────────────────────────


@router.get(
    "/disputes",
    tags=["disputes"],
    summary="List historical disputes",
    response_model=list[DisputeListItem],
)
async def list_disputes(limit: int = 50):
    """
    Query PostgreSQL for past disputes, ordered by most recent first.
    Includes latest evidence job status for each dispute.
    """
    async with async_session_factory() as session:
        repo = DisputeRepository(session)
        disputes = await repo.list_disputes(limit=min(limit, 100))
        dispute_ids = [d.id for d in disputes]
        jobs_map = await repo.get_latest_evidence_jobs_map(dispute_ids)

    items = []
    for d in disputes:
        item = DisputeListItem.model_validate(d)
        job = jobs_map.get(d.id)
        if job:
            item.evidence_job_id = job.id
            item.evidence_job_status = job.status
            item.evidence_job_error = job.error_message
        if not item.review_context and d.history:
            for entry in reversed(d.history):
                if isinstance(entry, dict) and entry.get("event") == "human_review_required" and entry.get("data"):
                    item.review_context = entry.get("data")
                    break
        items.append(item)

    return items


@router.get(
    "/disputes/{dispute_id}",
    tags=["disputes"],
    summary="Get details of a single dispute",
    response_model=DisputeListItem,
)
async def get_dispute(dispute_id: str):
    """
    Query PostgreSQL for a single dispute by ID, including its latest evidence job status.
    """
    async with async_session_factory() as session:
        repo = DisputeRepository(session)
        dispute = await repo.get_dispute(dispute_id)
        if dispute is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Dispute {dispute_id} not found.",
            )
        latest_job = await repo.get_latest_evidence_job(dispute_id)

    item = DisputeListItem.model_validate(dispute)
    if latest_job:
        item.evidence_job_id = latest_job.id
        item.evidence_job_status = latest_job.status
        item.evidence_job_error = latest_job.error_message
    if not item.review_context and dispute.history:
        for entry in reversed(dispute.history):
            if isinstance(entry, dict) and entry.get("event") == "human_review_required" and entry.get("data"):
                item.review_context = entry.get("data")
                break
    return item


@router.post(
    "/disputes/{dispute_id}/retry-evidence",
    tags=["disputes"],
    summary="Retry failed evidence generation job for a dispute",
)
async def retry_dispute_evidence(dispute_id: str):
    """
    Manually retry an evidence generation job for a dispute if previous attempts failed.
    """
    async with async_session_factory() as session:
        repo = DisputeRepository(session)
        dispute = await repo.get_dispute(dispute_id)
        if dispute is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Dispute {dispute_id} not found.",
            )
        
        job = await repo.create_evidence_job(dispute_id)
        from datetime import datetime, timezone
        now_iso = datetime.now(timezone.utc).isoformat()
        await repo.append_history(dispute_id, {
            "event": "job_queued",
            "job_id": job.id,
            "queued_at": now_iso,
            "retry": True,
        })
        await session.commit()

    from app.dispute.worker import evidence_worker
    evidence_worker.notify()

    await manager.broadcast_system_event({
        "event": "evidence_job_queued",
        "dispute_id": dispute_id,
        "job_id": job.id,
        "retry": True,
    })

    return {
        "status": "queued",
        "job_id": job.id,
        "dispute_id": dispute_id,
        "message": f"Evidence job #{job.id} enqueued for retry.",
    }


@router.get(
    "/disputes/{dispute_id}/evidence-url",
    tags=["disputes"],
    summary="Get short-lived signed URL for dispute evidence PDF",
)
async def get_dispute_evidence_url(dispute_id: str):
    """
    Returns a short-lived signed URL from Supabase Storage for the dispute's
    evidence PDF. The frontend loads and renders the PDF directly from Supabase CDN.
    The backend never proxies or streams the PDF bytes.
    """
    async with async_session_factory() as session:
        repo = DisputeRepository(session)
        dispute = await repo.get_dispute(dispute_id)

    if dispute is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dispute {dispute_id} not found.",
        )

    if not dispute.storage_path:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Evidence PDF has not been generated or uploaded for dispute {dispute_id}.",
        )

    from app.core.storage import storage_service, SupabaseStorageError

    try:
        signed_url = await storage_service.create_signed_url(dispute.storage_path, expires_in=3600)
    except SupabaseStorageError as exc:
        logger.exception("Failed to generate signed URL for dispute %s", dispute_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate signed URL: {exc}",
        )

    return {
        "dispute_id": dispute_id,
        "storage_path": dispute.storage_path,
        "signed_url": signed_url,
        "expires_in": 3600,
    }


# ── HITL Review / Resume ─────────────────────────────────────────────


@router.post(
    "/disputes/{dispute_id}/review",
    status_code=status.HTTP_202_ACCEPTED,
    tags=["disputes"],
    summary="Submit HITL review decision and resume graph",
)
async def review_dispute(
    dispute_id: str,
    decision: ReviewDecision,
    background_tasks: BackgroundTasks,
    request: Request,
):
    """
    Accept or reject a dispute that is awaiting human review.

    - **accept**: Proceed with the graph flow (submit contest / approve refund).
    - **reject**: Accept the loss and close the dispute.

    Updates the graph state with the user's decision and spawns a background
    task to resume execution. Returns **202 Accepted** immediately.
    """
    compiled_graph = _get_graph(request)
    config = _make_config(dispute_id)

    # 1. Verify the dispute exists and is awaiting review
    async with async_session_factory() as session:
        repo = DisputeRepository(session)
        dispute = await repo.get_dispute(dispute_id)

    if dispute is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dispute {dispute_id} not found.",
        )

    if dispute.status != "awaiting_review":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Dispute {dispute_id} is not awaiting review (status={dispute.status}).",
        )

    # 2. Determine which node is paused
    graph_state = await compiled_graph.aget_state(config)
    if not graph_state.next:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Dispute {dispute_id} graph is not paused at any interrupt.",
        )

    paused_node = graph_state.next[0]
    logger.info(
        "Resuming dispute %s at node '%s' with action=%s",
        dispute_id, paused_node, decision.action,
    )

    # 3. Inject the user's decision into the graph state
    await compiled_graph.aupdate_state(
        config,
        {
            "user_decision": {
                "action": decision.action,
                "reason": decision.reason,
                "amount_paise": decision.amount_paise,
            }
        },
    )

    # 4. Record the review in the dispute history
    async with async_session_factory() as session:
        repo = DisputeRepository(session)
        await repo.update_status(dispute_id, "processing")
        
        history_entry = {
            "event": "human_review_submitted",
            "action": decision.action,
            "reason": decision.reason,
            "paused_node": paused_node,
        }
        if decision.amount_paise is not None:
            history_entry["amount_paise"] = decision.amount_paise

        await repo.append_history(dispute_id, history_entry)

    # 5. Broadcast review event
    await manager.broadcast_system_event({
        "event": "review_submitted",
        "dispute_id": dispute_id,
        "action": decision.action,
        "paused_node": paused_node,
    })

    # 6. Resume graph in background
    background_tasks.add_task(
        resume_dispute_and_broadcast,
        dispute_id,
        compiled_graph,
    )

    return {
        "dispute_id": dispute_id,
        "status": "resuming",
        "action": decision.action,
        "message": f"Review recorded — graph resuming from '{paused_node}'.",
    }
