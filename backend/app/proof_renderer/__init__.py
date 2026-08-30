"""
Proof Renderer – standalone PDF generation utility for chargeback evidence.

Accepts pre-verified data and produces PDF byte-streams ready for
the Razorpay Document Upload API.
"""

from app.proof_renderer.renderer import ChargebackPDFRenderer

__all__ = ["ChargebackPDFRenderer"]
