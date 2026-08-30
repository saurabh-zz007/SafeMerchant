"""
Tests for the ChargebackPDFRenderer utility.

Run with:  pytest tests/test_proof_renderer.py -v
"""

from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO

import pytest

from app.proof_renderer import ChargebackPDFRenderer
from app.proof_renderer.renderer import ProofRendererError
from app.proof_renderer.schemas import (
    ActivityLogData,
    ActivityLogEntry,
    ChatMessage,
    ChatTranscriptData,
    DeliveryProofData,
)


@pytest.fixture
def renderer() -> ChargebackPDFRenderer:
    return ChargebackPDFRenderer()


# ─── sample data factories ────────────────────────────────────────

def _delivery_dict() -> dict:
    return {
        "order_id": "order_ORD123456",
        "payment_id": "pay_PAY789012",
        "customer_name": "Priya Sharma",
        "customer_email": "priya@example.com",
        "shipping_address": "42 MG Road, Bengaluru, Karnataka 560001",
        "carrier_name": "Delhivery",
        "tracking_number": "DLV9876543210",
        "shipped_at": datetime(2026, 8, 15, 10, 30, tzinfo=timezone.utc),
        "delivered_at": datetime(2026, 8, 18, 14, 45, tzinfo=timezone.utc),
        "delivery_status": "Delivered",
        "signed_by": "Priya S.",
        "proof_url": "https://tracking.delhivery.com/DLV9876543210",
        "additional_notes": "Customer confirmed receipt via SMS.",
    }


def _chat_dict() -> dict:
    return {
        "order_id": "order_ORD123456",
        "payment_id": "pay_PAY789012",
        "customer_name": "Priya Sharma",
        "customer_email": "priya@example.com",
        "agent_name": "Ravi K.",
        "conversation_started_at": datetime(2026, 8, 19, 9, 0, tzinfo=timezone.utc),
        "conversation_ended_at": datetime(2026, 8, 19, 9, 22, tzinfo=timezone.utc),
        "messages": [
            {
                "timestamp": datetime(2026, 8, 19, 9, 0, tzinfo=timezone.utc),
                "sender": "Customer",
                "message": "Hi, I didn't receive my order yet.",
            },
            {
                "timestamp": datetime(2026, 8, 19, 9, 2, tzinfo=timezone.utc),
                "sender": "Support Agent",
                "message": "Let me check the tracking for you. One moment please.",
            },
            {
                "timestamp": datetime(2026, 8, 19, 9, 5, tzinfo=timezone.utc),
                "sender": "Support Agent",
                "message": "It shows delivered on 18 Aug. Could you check with your neighbours?",
            },
            {
                "timestamp": datetime(2026, 8, 19, 9, 15, tzinfo=timezone.utc),
                "sender": "Customer",
                "message": "Oh wait, my brother picked it up. Sorry about that!",
            },
            {
                "timestamp": datetime(2026, 8, 19, 9, 17, tzinfo=timezone.utc),
                "sender": "Support Agent",
                "message": "No worries! Glad it's been found. Is there anything else I can help with?",
            },
            {
                "timestamp": datetime(2026, 8, 19, 9, 20, tzinfo=timezone.utc),
                "sender": "Customer",
                "message": "Nope, all good. Thanks!",
            },
        ],
        "resolution_summary": "Customer confirmed receipt after locating the package.",
    }


def _activity_dict() -> dict:
    return {
        "order_id": "order_ORD123456",
        "payment_id": "pay_PAY789012",
        "customer_name": "Priya Sharma",
        "customer_email": "priya@example.com",
        "log_title": "Order Activity Log",
        "entries": [
            {
                "timestamp": datetime(2026, 8, 14, 11, 0, tzinfo=timezone.utc),
                "actor": "System",
                "action": "Order placed",
                "details": "Payment captured via Razorpay.",
            },
            {
                "timestamp": datetime(2026, 8, 15, 10, 30, tzinfo=timezone.utc),
                "actor": "Warehouse",
                "action": "Shipped",
                "details": "Tracking: DLV9876543210",
            },
            {
                "timestamp": datetime(2026, 8, 18, 14, 45, tzinfo=timezone.utc),
                "actor": "Carrier",
                "action": "Delivered",
                "details": "Signed by Priya S.",
            },
        ],
    }


# ─── render to BytesIO ────────────────────────────────────────────

class TestRenderToBytesIO:
    def test_delivery_proof_from_dict(self, renderer: ChargebackPDFRenderer):
        result = renderer.render("delivery_proof", _delivery_dict())
        assert isinstance(result, BytesIO)
        header = result.read(5)
        assert header == b"%PDF-"

    def test_delivery_proof_from_model(self, renderer: ChargebackPDFRenderer):
        model = DeliveryProofData(**_delivery_dict())
        result = renderer.render("delivery_proof", model)
        assert isinstance(result, BytesIO)
        assert result.read(5) == b"%PDF-"

    def test_chat_transcript(self, renderer: ChargebackPDFRenderer):
        result = renderer.render("chat_transcript", _chat_dict())
        assert isinstance(result, BytesIO)
        assert result.read(5) == b"%PDF-"

    def test_activity_log(self, renderer: ChargebackPDFRenderer):
        result = renderer.render("activity_log", _activity_dict())
        assert isinstance(result, BytesIO)
        assert result.read(5) == b"%PDF-"


# ─── render to file ───────────────────────────────────────────────

class TestRenderToFile:
    def test_delivery_proof_file(self, renderer: ChargebackPDFRenderer, tmp_path):
        path = renderer.render_to_file(
            "delivery_proof", _delivery_dict(), directory=tmp_path
        )
        assert path.exists()
        assert path.suffix == ".pdf"
        assert path.stat().st_size > 0
        # Verify it's a valid PDF
        assert path.read_bytes()[:5] == b"%PDF-"

    def test_chat_transcript_file(self, renderer: ChargebackPDFRenderer, tmp_path):
        path = renderer.render_to_file(
            "chat_transcript", _chat_dict(), directory=tmp_path
        )
        assert path.exists()
        assert path.read_bytes()[:5] == b"%PDF-"


# ─── error handling ───────────────────────────────────────────────

class TestErrorHandling:
    def test_unknown_template_raises(self, renderer: ChargebackPDFRenderer):
        with pytest.raises(ProofRendererError, match="Unknown template_type"):
            renderer.render("nonexistent_template", {})

    def test_invalid_data_raises(self, renderer: ChargebackPDFRenderer):
        with pytest.raises(ProofRendererError, match="does not match schema"):
            renderer.render("delivery_proof", {"bad": "data"})

    def test_wrong_data_type_raises(self, renderer: ChargebackPDFRenderer):
        with pytest.raises(ProofRendererError, match="Expected dict or BaseModel"):
            renderer.render("delivery_proof", "not a dict")  # type: ignore


# ─── extensibility ────────────────────────────────────────────────

class TestExtensibility:
    def test_available_templates(self, renderer: ChargebackPDFRenderer):
        templates = renderer.available_templates
        assert "delivery_proof" in templates
        assert "chat_transcript" in templates
        assert "activity_log" in templates

    def test_register_custom_template(self, renderer: ChargebackPDFRenderer):
        from pydantic import BaseModel as PydanticBaseModel
        from reportlab.platypus import Paragraph
        from reportlab.lib.styles import getSampleStyleSheet

        class DummyData(PydanticBaseModel):
            title: str

        def render_dummy(data: DummyData):
            ss = getSampleStyleSheet()
            return [Paragraph(data.title, ss["Title"])]

        renderer.register_template("dummy", render_dummy, DummyData)
        assert "dummy" in renderer.available_templates

        result = renderer.render("dummy", {"title": "Hello World"})
        assert isinstance(result, BytesIO)
        assert result.read(5) == b"%PDF-"
