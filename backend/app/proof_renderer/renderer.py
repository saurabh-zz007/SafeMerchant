"""
ChargebackPDFRenderer – the main rendering engine.

Usage::

    from app.proof_renderer import ChargebackPDFRenderer

    renderer = ChargebackPDFRenderer()

    # Using a dict
    pdf_bytes = renderer.render("delivery_proof", data_dict)

    # Using a Pydantic model directly
    pdf_bytes = renderer.render("delivery_proof", delivery_proof_model)

    # Write to a temp file instead of BytesIO
    path = renderer.render_to_file("delivery_proof", data_dict)
"""

from __future__ import annotations

import logging
import tempfile
from io import BytesIO
from pathlib import Path
from typing import Any, Union

from pydantic import BaseModel
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate

from app.proof_renderer.templates import TEMPLATE_REGISTRY

logger = logging.getLogger(__name__)


class ProofRendererError(Exception):
    """Raised when the renderer encounters an unrecoverable problem."""


class ChargebackPDFRenderer:
    """
    Standalone, zero-business-logic PDF renderer.

    Responsibilities
    ────────────────
    • Accept a ``template_type`` string and a data payload (dict or Pydantic model).
    • Resolve the matching template function from the registry.
    • Coerce raw dicts into the template's Pydantic model (structural validation only).
    • Produce a PDF as ``BytesIO`` or a temporary file path.

    The renderer **never** validates the truthfulness of data — it only
    ensures the data matches the expected schema shape.
    """

    def __init__(self) -> None:
        self._registry = dict(TEMPLATE_REGISTRY)

    # ── public API ─────────────────────────────────────────────────

    @property
    def available_templates(self) -> list[str]:
        """Return the list of registered template_type names."""
        return list(self._registry.keys())

    def register_template(
        self,
        template_type: str,
        render_fn,
        data_model: type[BaseModel],
    ) -> None:
        """
        Register a new template at runtime.

        Parameters
        ----------
        template_type : str
            Key used to select this template (e.g. ``"refund_receipt"``).
        render_fn : callable
            Function with signature ``(data_model_instance) -> list[Flowable]``.
        data_model : type[BaseModel]
            Pydantic model the incoming data will be validated / coerced against.
        """
        if template_type in self._registry:
            logger.warning("Overwriting existing template '%s'", template_type)
        self._registry[template_type] = (render_fn, data_model)

    def render(
        self,
        template_type: str,
        data: Union[dict[str, Any], BaseModel],
        *,
        filename_hint: str | None = None,
    ) -> BytesIO:
        """
        Render a proof document and return the PDF as an in-memory byte stream.

        Parameters
        ----------
        template_type : str
            One of the keys in the template registry.
        data : dict | BaseModel
            The evidence payload.  Dicts are coerced into the template's model.
        filename_hint : str, optional
            Metadata title embedded in the PDF properties.

        Returns
        -------
        BytesIO
            Seeked-to-zero PDF byte stream, ready for upload or writing.
        """
        render_fn, validated_data = self._resolve(template_type, data)

        buf = BytesIO()
        doc = self._make_doc(buf, filename_hint or f"{template_type}.pdf")
        flowables = render_fn(validated_data)
        doc.build(flowables)

        buf.seek(0)
        logger.info(
            "Rendered '%s' PDF (%d bytes)", template_type, buf.getbuffer().nbytes
        )
        return buf

    def render_to_file(
        self,
        template_type: str,
        data: Union[dict[str, Any], BaseModel],
        *,
        directory: str | Path | None = None,
        filename_hint: str | None = None,
    ) -> Path:
        """
        Render a proof document and write it to a temporary file.

        Parameters
        ----------
        template_type : str
            Template key.
        data : dict | BaseModel
            The evidence payload.
        directory : str | Path, optional
            Directory for the temp file; defaults to system temp dir.
        filename_hint : str, optional
            Prefix for the temporary filename.

        Returns
        -------
        Path
            Absolute path to the generated PDF file.
        """
        pdf_bytes = self.render(template_type, data, filename_hint=filename_hint)

        prefix = filename_hint or template_type
        suffix = ".pdf"
        dir_path = str(directory) if directory else None

        fd = tempfile.NamedTemporaryFile(
            prefix=f"{prefix}_",
            suffix=suffix,
            dir=dir_path,
            delete=False,
        )
        try:
            fd.write(pdf_bytes.read())
        finally:
            fd.close()

        result = Path(fd.name)
        logger.info("Wrote PDF to %s", result)
        return result

    # ── internals ──────────────────────────────────────────────────

    def _resolve(self, template_type: str, data: Union[dict[str, Any], BaseModel]):
        """Look up the template and validate / coerce the data payload."""
        entry = self._registry.get(template_type)
        if entry is None:
            raise ProofRendererError(
                f"Unknown template_type '{template_type}'. "
                f"Available: {self.available_templates}"
            )

        render_fn, model_cls = entry

        # If the caller already passed a model instance, trust it.
        if isinstance(data, model_cls):
            return render_fn, data

        # Coerce dict → Pydantic model (structural validation only).
        if isinstance(data, dict):
            try:
                validated = model_cls(**data)
            except Exception as exc:
                raise ProofRendererError(
                    f"Data does not match schema for '{template_type}': {exc}"
                ) from exc
            return render_fn, validated

        # If it's a different BaseModel subclass, dump and re-validate.
        if isinstance(data, BaseModel):
            try:
                validated = model_cls(**data.model_dump())
            except Exception as exc:
                raise ProofRendererError(
                    f"Data does not match schema for '{template_type}': {exc}"
                ) from exc
            return render_fn, validated

        raise ProofRendererError(
            f"Expected dict or BaseModel for data, got {type(data).__name__}"
        )

    @staticmethod
    def _make_doc(buffer: BytesIO, title: str) -> SimpleDocTemplate:
        """Create a ReportLab SimpleDocTemplate with sensible defaults."""
        return SimpleDocTemplate(
            buffer,
            pagesize=A4,
            title=title,
            leftMargin=2 * cm,
            rightMargin=2 * cm,
            topMargin=2 * cm,
            bottomMargin=2 * cm,
        )
