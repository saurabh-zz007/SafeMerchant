import httpx
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone

from app.dispute.submission import (
    submit_dispute_evidence,
    DisputeSubmissionError,
    RAZORPAY_API_BASE
)
from app.dispute.models import Dispute

# Mark all test functions as async
pytestmark = pytest.mark.anyio

@pytest.fixture
def mock_dispute():
    return Dispute(
        id="disp_test123",
        status="resolved",
        amount_paise=10000,
        payment_id="pay_test123",
        customer_email="customer@example.com",
        history=[]
    )

@pytest.fixture
def mock_session():
    session = MagicMock()
    session.add = MagicMock()
    session.commit = AsyncMock()
    return session

@pytest.fixture
def mock_dispute_repo(mock_dispute):
    repo = MagicMock()
    repo.get_dispute = AsyncMock(return_value=mock_dispute)
    repo.update_status = AsyncMock()
    repo.append_history = AsyncMock()
    repo.update_document_id = AsyncMock()
    repo.update_evidence_pointers = AsyncMock()
    return repo

@pytest.fixture
def mock_evidence_repo():
    repo = MagicMock()
    repo.get_order_by_payment_id = AsyncMock(return_value=None)
    repo.get_order_by_id = AsyncMock(return_value=None)
    return repo

@patch("app.dispute.submission.settings")
@patch("app.dispute.submission.async_session_factory")
@patch("app.dispute.submission.DisputeRepository")
@patch("app.dispute.submission.EvidenceRepository")
@patch("app.dispute.submission.ChargebackPDFRenderer")
@patch("httpx.AsyncClient")
async def test_submit_dispute_evidence_success(
    mock_client_class,
    mock_pdf_renderer_class,
    mock_evidence_repo_class,
    mock_dispute_repo_class,
    mock_session_factory,
    mock_settings,
    mock_dispute,
    mock_session,
    mock_dispute_repo,
    mock_evidence_repo
):
    # Setup settings
    mock_settings.razorpay_key_id = "test_key"
    mock_settings.razorpay_key_secret = "test_secret"

    # Setup session
    mock_session_factory.return_value.__aenter__.return_value = mock_session

    # Setup repos
    mock_dispute_repo_class.return_value = mock_dispute_repo
    mock_evidence_repo_class.return_value = mock_evidence_repo

    # Setup PDF renderer
    mock_pdf = MagicMock()
    mock_pdf.getvalue.return_value = b"%PDF-mock-bytes"
    mock_pdf_renderer_class.return_value.render.return_value = mock_pdf

    # Setup httpx mock client
    mock_client = AsyncMock()
    mock_client_class.return_value.__aenter__.return_value = mock_client

    # Response 1: Document Upload Success
    mock_doc_response = MagicMock()
    mock_doc_response.status_code = 201
    mock_doc_response.json.return_value = {"id": "doc_test123"}
    
    # Response 2: Contest Dispute Success
    mock_contest_response = MagicMock()
    mock_contest_response.status_code = 200
    mock_contest_response.json.return_value = {"status": "contested"}

    # Mock sequence of client calls
    mock_client.post = AsyncMock(side_effect=[mock_doc_response, mock_contest_response])

    # Call the service function
    result = await submit_dispute_evidence("disp_test123")

    # Assert outcomes
    assert result["outcome"] == "success"
    assert result["document_id"] == "doc_test123"
    assert result["dispute_id"] == "disp_test123"
    
    # Verify status transition
    mock_dispute_repo.update_status.assert_called_once_with("disp_test123", "under_review")
    # Verify history logging (evidence_composed, evidence_uploaded, and contest_submitted)
    assert mock_dispute_repo.append_history.call_count == 3
    # Verify database log row added
    mock_session.add.assert_called_once()
    mock_session.commit.assert_called()

@patch("app.dispute.submission.settings")
@patch("app.dispute.submission.async_session_factory")
@patch("app.dispute.submission.DisputeRepository")
@patch("app.dispute.submission.EvidenceRepository")
@patch("app.dispute.submission.ChargebackPDFRenderer")
@patch("httpx.AsyncClient")
async def test_submit_dispute_evidence_api_rejection(
    mock_client_class,
    mock_pdf_renderer_class,
    mock_evidence_repo_class,
    mock_dispute_repo_class,
    mock_session_factory,
    mock_settings,
    mock_dispute,
    mock_session,
    mock_dispute_repo,
    mock_evidence_repo
):
    # Setup settings
    mock_settings.razorpay_key_id = "test_key"
    mock_settings.razorpay_key_secret = "test_secret"

    # Setup session
    mock_session_factory.return_value.__aenter__.return_value = mock_session

    # Setup repos
    mock_dispute_repo_class.return_value = mock_dispute_repo
    mock_evidence_repo_class.return_value = mock_evidence_repo

    # Setup PDF renderer
    mock_pdf = MagicMock()
    mock_pdf.getvalue.return_value = b"%PDF-mock-bytes"
    mock_pdf_renderer_class.return_value.render.return_value = mock_pdf

    # Setup httpx mock client
    mock_client = AsyncMock()
    mock_client_class.return_value.__aenter__.return_value = mock_client

    # Response 1: Document Upload Success
    mock_doc_response = MagicMock()
    mock_doc_response.status_code = 201
    mock_doc_response.json.return_value = {"id": "doc_test123"}
    
    # Response 2: Contest Dispute Rejection (400 Bad Request / 404 Not Found)
    mock_contest_response = MagicMock()
    mock_contest_response.status_code = 400
    mock_contest_response.json.return_value = {
        "error": {
            "code": "BAD_REQUEST_ERROR",
            "description": "dispute does not exist"
        }
    }

    mock_client.post = AsyncMock(side_effect=[mock_doc_response, mock_contest_response])

    # Call the service function
    result = await submit_dispute_evidence("disp_test123")

    # Assert outcomes
    assert result["outcome"] == "contest_expected_failure"
    # Verify status transition NOT called
    mock_dispute_repo.update_status.assert_not_called()
    # Verify DB log row committed
    mock_session.add.assert_called_once()
    mock_session.commit.assert_called()

@patch("app.dispute.submission.settings")
@patch("app.dispute.submission.async_session_factory")
@patch("app.dispute.submission.DisputeRepository")
@patch("app.dispute.submission.EvidenceRepository")
@patch("app.dispute.submission.ChargebackPDFRenderer")
@patch("httpx.AsyncClient")
async def test_submit_dispute_evidence_genuine_failure(
    mock_client_class,
    mock_pdf_renderer_class,
    mock_evidence_repo_class,
    mock_dispute_repo_class,
    mock_session_factory,
    mock_settings,
    mock_dispute,
    mock_session,
    mock_dispute_repo,
    mock_evidence_repo
):
    # Setup settings
    mock_settings.razorpay_key_id = "test_key"
    mock_settings.razorpay_key_secret = "test_secret"

    # Setup session
    mock_session_factory.return_value.__aenter__.return_value = mock_session

    # Setup repos
    mock_dispute_repo_class.return_value = mock_dispute_repo
    mock_evidence_repo_class.return_value = mock_evidence_repo

    # Setup PDF renderer
    mock_pdf = MagicMock()
    mock_pdf.getvalue.return_value = b"%PDF-mock-bytes"
    mock_pdf_renderer_class.return_value.render.return_value = mock_pdf

    # Setup httpx mock client
    mock_client = AsyncMock()
    mock_client_class.return_value.__aenter__.return_value = mock_client

    # Response 1: Document Upload Success
    mock_doc_response = MagicMock()
    mock_doc_response.status_code = 201
    mock_doc_response.json.return_value = {"id": "doc_test123"}
    
    # Response 2: Contest Dispute failure (500 Internal Server Error)
    mock_contest_response = MagicMock()
    mock_contest_response.status_code = 500
    mock_contest_response.json.return_value = {"error": "internal_error"}

    mock_client.post = AsyncMock(side_effect=[mock_doc_response, mock_contest_response])

    # Expect DisputeSubmissionError to be raised
    with pytest.raises(DisputeSubmissionError):
        await submit_dispute_evidence("disp_test123")

    # Verify status transition NOT called
    mock_dispute_repo.update_status.assert_not_called()
    # Verify DB log row committed with failed outcome
    mock_session.add.assert_called_once()
    mock_session.commit.assert_called()

@patch("app.dispute.submission.settings")
@patch("app.dispute.submission.async_session_factory")
@patch("app.dispute.submission.DisputeRepository")
@patch("app.dispute.submission.EvidenceRepository")
@patch("app.dispute.submission.ChargebackPDFRenderer")
@patch("httpx.AsyncClient")
async def test_submit_dispute_evidence_timeout_retry(
    mock_client_class,
    mock_pdf_renderer_class,
    mock_evidence_repo_class,
    mock_dispute_repo_class,
    mock_session_factory,
    mock_settings,
    mock_dispute,
    mock_session,
    mock_dispute_repo,
    mock_evidence_repo
):
    # Setup settings
    mock_settings.razorpay_key_id = "test_key"
    mock_settings.razorpay_key_secret = "test_secret"

    # Setup session
    mock_session_factory.return_value.__aenter__.return_value = mock_session

    # Setup repos
    mock_dispute_repo_class.return_value = mock_dispute_repo
    mock_evidence_repo_class.return_value = mock_evidence_repo

    # Setup PDF renderer
    mock_pdf = MagicMock()
    mock_pdf.getvalue.return_value = b"%PDF-mock-bytes"
    mock_pdf_renderer_class.return_value.render.return_value = mock_pdf

    # Setup httpx mock client
    mock_client = AsyncMock()
    mock_client_class.return_value.__aenter__.return_value = mock_client

    # Setup mock sequence: first document upload call raises timeout, second succeeds
    mock_doc_response = MagicMock()
    mock_doc_response.status_code = 201
    mock_doc_response.json.return_value = {"id": "doc_test123"}
    
    mock_contest_response = MagicMock()
    mock_contest_response.status_code = 200
    mock_contest_response.json.return_value = {"status": "contested"}

    mock_client.post = AsyncMock(side_effect=[
        httpx.TimeoutException("Connection timed out"),
        mock_doc_response,
        mock_contest_response
    ])

    # Call the service function
    result = await submit_dispute_evidence("disp_test123")

    # Assert outcomes: should succeed because it retried and the second post succeeded
    assert result["outcome"] == "success"
    assert mock_client.post.call_count == 3
