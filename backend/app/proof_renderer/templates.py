"""
Template functions for proof-document PDF pages.

Each template function receives a ReportLab ``Canvas`` (or a list of
``Flowable`` objects) plus typed data and draws / appends the content
for one document type.

Adding a new template:
  1. Create a function with signature
         def render_<name>(data: <Model>, styles: StyleSheet1) -> list[Flowable]
  2. Register it in ``TEMPLATE_REGISTRY`` at the bottom of this file.
"""

from __future__ import annotations

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm, mm
from reportlab.platypus import (
    Flowable,
    HRFlowable,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

from app.proof_renderer.schemas import (
    ActivityLogData,
    ChatTranscriptData,
    DeliveryProofData,
)

# ─── colour palette ────────────────────────────────────────────────
BRAND_DARK = colors.HexColor("#1a1a2e")
BRAND_PRIMARY = colors.HexColor("#16213e")
BRAND_ACCENT = colors.HexColor("#0f3460")
BRAND_HIGHLIGHT = colors.HexColor("#e94560")
HEADER_BG = colors.HexColor("#f0f4f8")
ROW_ALT_BG = colors.HexColor("#f7f9fc")
BORDER_COLOR = colors.HexColor("#d1d9e6")
TEXT_DARK = colors.HexColor("#2d3748")
TEXT_MID = colors.HexColor("#4a5568")
TEXT_LIGHT = colors.HexColor("#718096")


# ─── shared style helpers ──────────────────────────────────────────
def _base_styles() -> dict[str, ParagraphStyle]:
    """Return a dict of reusable ParagraphStyles."""
    ss = getSampleStyleSheet()
    return {
        "doc_title": ParagraphStyle(
            "doc_title",
            parent=ss["Title"],
            fontName="Helvetica-Bold",
            fontSize=18,
            leading=22,
            textColor=BRAND_DARK,
            spaceAfter=4 * mm,
        ),
        "section": ParagraphStyle(
            "section",
            parent=ss["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=12,
            leading=15,
            textColor=BRAND_ACCENT,
            spaceBefore=6 * mm,
            spaceAfter=3 * mm,
        ),
        "body": ParagraphStyle(
            "body",
            parent=ss["Normal"],
            fontName="Helvetica",
            fontSize=10,
            leading=14,
            textColor=TEXT_DARK,
        ),
        "body_small": ParagraphStyle(
            "body_small",
            parent=ss["Normal"],
            fontName="Helvetica",
            fontSize=8,
            leading=11,
            textColor=TEXT_MID,
        ),
        "label": ParagraphStyle(
            "label",
            fontName="Helvetica-Bold",
            fontSize=9,
            leading=12,
            textColor=TEXT_MID,
        ),
        "value": ParagraphStyle(
            "value",
            fontName="Helvetica",
            fontSize=10,
            leading=13,
            textColor=TEXT_DARK,
        ),
        "footer": ParagraphStyle(
            "footer",
            fontName="Helvetica",
            fontSize=7,
            leading=9,
            textColor=TEXT_LIGHT,
            alignment=TA_CENTER,
        ),
        "timestamp": ParagraphStyle(
            "timestamp",
            fontName="Helvetica",
            fontSize=8,
            leading=10,
            textColor=TEXT_LIGHT,
            alignment=TA_RIGHT,
        ),
    }


def _divider() -> HRFlowable:
    return HRFlowable(
        width="100%",
        thickness=0.5,
        color=BORDER_COLOR,
        spaceBefore=3 * mm,
        spaceAfter=3 * mm,
    )


def _kv_table(pairs: list[tuple[str, str]], styles: dict) -> Table:
    """Render label/value pairs as a two-column table."""
    data = [
        [Paragraph(label, styles["label"]), Paragraph(value, styles["value"])]
        for label, value in pairs
    ]
    page_width = A4[0] - 4 * cm  # usable width inside margins
    tbl = Table(data, colWidths=[page_width * 0.35, page_width * 0.65])
    tbl.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("LINEBELOW", (0, 0), (-1, -1), 0.25, BORDER_COLOR),
            ]
        )
    )
    return tbl


def _watermark_text() -> str:
    return (
        "This document was auto-generated for chargeback evidence purposes. "
        "It is not a legal certificate."
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  TEMPLATE: delivery_proof
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def render_delivery_proof(data: DeliveryProofData) -> list[Flowable]:
    """Render a delivery-confirmation proof document."""
    s = _base_styles()
    elements: list[Flowable] = []

    # Title
    elements.append(Paragraph("Delivery Confirmation Proof", s["doc_title"]))
    elements.append(
        Paragraph(
            f"Generated for dispute evidence — Order {data.order_id}",
            s["body_small"],
        )
    )
    elements.append(_divider())

    # Order details
    elements.append(Paragraph("Order &amp; Payment Details", s["section"]))
    elements.append(
        _kv_table(
            [
                ("Order ID", data.order_id),
                ("Payment ID", data.payment_id),
                ("Customer", data.customer_name),
                ("Email", data.customer_email),
            ],
            s,
        )
    )

    # Addresses (Shipping vs Billing comparison)
    elements.append(Paragraph("Address Verification Details", s["section"]))
    if data.billing_address:
        page_width = A4[0] - 4 * cm
        address_table = Table(
            [
                [Paragraph("Billing Address", s["label"]), Paragraph("Shipping Address", s["label"])],
                [Paragraph(data.billing_address, s["value"]), Paragraph(data.shipping_address, s["value"])]
            ],
            colWidths=[page_width * 0.5, page_width * 0.5]
        )
        address_table.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LINEBELOW", (0, 0), (-1, -1), 0.25, BORDER_COLOR),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
        ]))
        elements.append(address_table)
        
        # Flag mismatch explicitly
        if data.billing_address.strip().lower() != data.shipping_address.strip().lower():
            mismatch_style = ParagraphStyle(
                "mismatch_alert",
                parent=s["body"],
                textColor=colors.HexColor("#e94560"),
                fontName="Helvetica-Bold",
                spaceBefore=2 * mm,
                spaceAfter=2 * mm
            )
            elements.append(Paragraph("⚠️ WARNING: Address Mismatch Detected! Shipping address differs from Billing address.", mismatch_style))
    else:
        elements.append(_kv_table([("Shipping Address", data.shipping_address)], s))

    # Shipping details
    elements.append(Paragraph("Shipping Information", s["section"]))
    elements.append(
        _kv_table(
            [
                ("Carrier", data.carrier_name),
                ("Tracking #", data.tracking_number),
                ("Shipped At", data.shipped_at.strftime("%d %b %Y, %I:%M %p %Z")),
                ("Delivered At", data.delivered_at.strftime("%d %b %Y, %I:%M %p %Z")),
                ("Delivery Status", data.delivery_status),
            ]
            + ([("Signed By", data.signed_by)] if data.signed_by else [])
            + (
                [("Tracking Page", data.proof_url)]
                if data.proof_url
                else []
            ),
            s,
        )
    )

    # Verification Reference Details (OTP Reference)
    elements.append(Paragraph("Delivery Verification (OTP Reference)", s["section"]))
    if data.otp_transaction_id:
        elements.append(
            _kv_table(
                [
                    ("OTP Transaction ID", data.otp_transaction_id),
                    ("Verification Timestamp", data.otp_verified_at.strftime("%d %b %Y, %I:%M %p %Z") if data.otp_verified_at else "N/A"),
                    ("Verification Channel", data.otp_channel or "N/A")
                ],
                s,
            )
        )
    else:
        elements.append(Paragraph("Not captured for this transaction / Hand-signed delivery only", s["body_small"]))

    # Tracking Event Timeline
    elements.append(Paragraph("Carrier Tracking Timeline (Captured)", s["section"]))
    if data.tracking_events:
        rows = [[Paragraph("Timestamp", s["label"]), Paragraph("Status", s["label"]), Paragraph("Location", s["label"])]]
        for event in data.tracking_events:
            ts_str = event.timestamp.strftime("%d %b %Y, %I:%M %p %Z")
            rows.append([
                Paragraph(ts_str, s["value"]),
                Paragraph(event.status, s["value"]),
                Paragraph(event.location or "—", s["value"])
            ])
        page_width = A4[0] - 4 * cm
        timeline_table = Table(rows, colWidths=[page_width * 0.35, page_width * 0.35, page_width * 0.3])
        timeline_table.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("BACKGROUND", (0, 0), (-1, 0), HEADER_BG),
            ("LINEBELOW", (0, 0), (-1, -1), 0.25, BORDER_COLOR),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
        ]))
        elements.append(timeline_table)
    else:
        elements.append(Paragraph("Not captured for this transaction", s["body_small"]))

    # Payment Risk & Fraud Signals
    elements.append(Paragraph("Payment Security & Fraud Risk Signals", s["section"]))
    risk_rows = [
        ("CVV Match Result", data.cvv_match or "Not captured for this transaction"),
        ("AVS Match Result", data.avs_result or "Not captured for this transaction"),
        ("Checkout IP Address", data.checkout_ip or "Not captured for this transaction"),
        ("Checkout Device Fingerprint", data.checkout_device or "Not captured for this transaction"),
        ("3D-Secure/2FA Verified", "Yes" if data.is_2fa_verified is True else ("No" if data.is_2fa_verified is False else "Not captured for this transaction"))
    ]
    elements.append(_kv_table(risk_rows, s))

    # Customer Delivery History
    elements.append(Paragraph("Customer Account Prior Successful Deliveries", s["section"]))
    if data.prior_deliveries:
        rows = [[Paragraph("Order ID", s["label"]), Paragraph("Delivered Date", s["label"]), Paragraph("Item Description", s["label"])]]
        for deliv in data.prior_deliveries:
            ts_str = deliv.delivered_at.strftime("%d %b %Y")
            rows.append([
                Paragraph(deliv.order_id, s["value"]),
                Paragraph(ts_str, s["value"]),
                Paragraph(deliv.item_description or "—", s["value"])
            ])
        page_width = A4[0] - 4 * cm
        history_table = Table(rows, colWidths=[page_width * 0.35, page_width * 0.35, page_width * 0.3])
        history_table.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("BACKGROUND", (0, 0), (-1, 0), HEADER_BG),
            ("LINEBELOW", (0, 0), (-1, -1), 0.25, BORDER_COLOR),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
        ]))
        elements.append(history_table)
    else:
        elements.append(Paragraph("Not captured for this transaction / No prior delivery history found", s["body_small"]))

    # Additional notes
    if data.additional_notes:
        elements.append(Paragraph("Additional Notes", s["section"]))
        elements.append(Paragraph(data.additional_notes, s["body"]))

    # Footer
    elements.append(Spacer(1, 12 * mm))
    elements.append(_divider())
    elements.append(Paragraph(_watermark_text(), s["footer"]))

    return elements


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  TEMPLATE: chat_transcript
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def render_chat_transcript(data: ChatTranscriptData) -> list[Flowable]:
    """Render a customer-support chat transcript proof document."""
    s = _base_styles()
    elements: list[Flowable] = []

    # Title
    elements.append(Paragraph("Chat Transcript – Support Interaction", s["doc_title"]))
    elements.append(
        Paragraph(
            f"Generated for dispute evidence — Order {data.order_id}",
            s["body_small"],
        )
    )
    elements.append(_divider())

    # Duration calculation with fallbacks
    if data.conversation_started_at and data.conversation_ended_at:
        duration_str = (
            f"{data.conversation_started_at.strftime('%d %b %Y, %I:%M %p')}"
            f" → {data.conversation_ended_at.strftime('%I:%M %p %Z')}"
        )
    elif data.conversation_started_at:
        duration_str = data.conversation_started_at.strftime('%d %b %Y, %I:%M %p')
    else:
        duration_str = "Support Transcript on File"

    # Conversation metadata
    elements.append(Paragraph("Conversation Details", s["section"]))
    elements.append(
        _kv_table(
            [
                ("Order ID", data.order_id),
                ("Payment ID", data.payment_id),
                ("Customer", f"{data.customer_name or 'Customer'} ({data.customer_email or 'N/A'})"),
                ("Support Agent", data.agent_name or "SafeMerchant Support"),
                ("Duration", duration_str),
            ],
            s,
        )
    )

    # Messages table
    elements.append(Paragraph("Messages", s["section"]))

    sender_style = ParagraphStyle(
        "sender",
        fontName="Helvetica-Bold",
        fontSize=9,
        leading=12,
        textColor=BRAND_ACCENT,
    )

    header = [
        Paragraph("<b>Time</b>", s["label"]),
        Paragraph("<b>Sender</b>", s["label"]),
        Paragraph("<b>Message</b>", s["label"]),
    ]
    rows = [header]
    if data.messages:
        for msg in data.messages:
            ts_str = msg.timestamp.strftime("%H:%M:%S") if msg.timestamp else "--:--:--"
            rows.append(
                [
                    Paragraph(ts_str, s["timestamp"]),
                    Paragraph(msg.sender or "Support", sender_style),
                    Paragraph(msg.message, s["body_small"]),
                ]
            )
    else:
        rows.append(
            [
                Paragraph("--:--:--", s["timestamp"]),
                Paragraph("System", sender_style),
                Paragraph("Customer interaction records and verified telemetry on file.", s["body_small"]),
            ]
        )

    page_width = A4[0] - 4 * cm
    msg_table = Table(
        rows,
        colWidths=[page_width * 0.15, page_width * 0.2, page_width * 0.65],
        repeatRows=1,
    )
    msg_table.setStyle(
        TableStyle(
            [
                # Header row
                ("BACKGROUND", (0, 0), (-1, 0), HEADER_BG),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, 0), 9),
                # Body rows
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("LINEBELOW", (0, 0), (-1, -1), 0.25, BORDER_COLOR),
                # Alternating row colours
                *[
                    ("BACKGROUND", (0, i), (-1, i), ROW_ALT_BG)
                    for i in range(2, len(rows), 2)
                ],
            ]
        )
    )
    elements.append(msg_table)

    # Resolution
    if data.resolution_summary:
        elements.append(Paragraph("Resolution Summary", s["section"]))
        elements.append(Paragraph(data.resolution_summary, s["body"]))

    # Additional notes
    if data.additional_notes:
        elements.append(Paragraph("Additional Notes", s["section"]))
        elements.append(Paragraph(data.additional_notes, s["body"]))

    # Footer
    elements.append(Spacer(1, 12 * mm))
    elements.append(_divider())
    elements.append(Paragraph(_watermark_text(), s["footer"]))

    return elements


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  TEMPLATE: activity_log
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def render_activity_log(data: ActivityLogData) -> list[Flowable]:
    """Render an order activity / audit-log proof document."""
    s = _base_styles()
    elements: list[Flowable] = []

    # Title
    elements.append(Paragraph(data.log_title, s["doc_title"]))
    elements.append(
        Paragraph(
            f"Generated for dispute evidence — Order {data.order_id}",
            s["body_small"],
        )
    )
    elements.append(_divider())

    # Order details
    elements.append(Paragraph("Order Details", s["section"]))
    elements.append(
        _kv_table(
            [
                ("Order ID", data.order_id),
                ("Payment ID", data.payment_id),
                ("Customer", f"{data.customer_name} ({data.customer_email})"),
            ],
            s,
        )
    )

    # Activity entries table
    elements.append(Paragraph("Activity Timeline", s["section"]))

    header = [
        Paragraph("<b>Timestamp</b>", s["label"]),
        Paragraph("<b>Actor</b>", s["label"]),
        Paragraph("<b>Action</b>", s["label"]),
        Paragraph("<b>Details</b>", s["label"]),
    ]
    rows = [header]
    for entry in data.entries:
        rows.append(
            [
                Paragraph(
                    entry.timestamp.strftime("%d %b %Y %H:%M:%S"), s["body_small"]
                ),
                Paragraph(entry.actor, s["body_small"]),
                Paragraph(entry.action, s["body_small"]),
                Paragraph(entry.details or "—", s["body_small"]),
            ]
        )

    page_width = A4[0] - 4 * cm
    log_table = Table(
        rows,
        colWidths=[
            page_width * 0.22,
            page_width * 0.18,
            page_width * 0.28,
            page_width * 0.32,
        ],
        repeatRows=1,
    )
    log_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), HEADER_BG),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, 0), 9),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("LINEBELOW", (0, 0), (-1, -1), 0.25, BORDER_COLOR),
                *[
                    ("BACKGROUND", (0, i), (-1, i), ROW_ALT_BG)
                    for i in range(2, len(rows), 2)
                ],
            ]
        )
    )
    elements.append(log_table)

    # Additional notes
    if data.additional_notes:
        elements.append(Paragraph("Additional Notes", s["section"]))
        elements.append(Paragraph(data.additional_notes, s["body"]))

    # Footer
    elements.append(Spacer(1, 12 * mm))
    elements.append(_divider())
    elements.append(Paragraph(_watermark_text(), s["footer"]))

    return elements


# ─── Registry ──────────────────────────────────────────────────────
# Maps template_type strings → (render_fn, expected_data_model)
# Supports both Razorpay's exact dispute.entity.evidence field names and legacy aliases.
TEMPLATE_REGISTRY: dict[str, tuple] = {
    # Razorpay exact dispute.entity.evidence schema keys
    "shipping_proof": (render_delivery_proof, DeliveryProofData),
    "customer_communication": (render_chat_transcript, ChatTranscriptData),
    "access_activity_log": (render_activity_log, ActivityLogData),
    "billing_proof": (render_delivery_proof, DeliveryProofData),
    "cancellation_proof": (render_chat_transcript, ChatTranscriptData),
    "proof_of_service": (render_delivery_proof, DeliveryProofData),
    "refund_confirmation": (render_activity_log, ActivityLogData),
    "refund_cancellation_policy": (render_activity_log, ActivityLogData),
    "term_and_conditions": (render_activity_log, ActivityLogData),
    "others": (render_activity_log, ActivityLogData),

    # Legacy / alias keys
    "delivery_proof": (render_delivery_proof, DeliveryProofData),
    "chat_transcript": (render_chat_transcript, ChatTranscriptData),
    "activity_log": (render_activity_log, ActivityLogData),
}
