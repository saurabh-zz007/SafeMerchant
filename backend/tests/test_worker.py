import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.dispute.worker import EvidenceWorkerPool
from app.dispute.models import EvidenceJob

pytestmark = pytest.mark.anyio


@pytest.fixture
def mock_job():
    return EvidenceJob(
        id=101,
        dispute_id="disp_worker_test",
        status="queued",
        attempts=0,
        max_attempts=3,
    )


@patch("app.dispute.worker.async_session_factory")
@patch("app.dispute.worker.DisputeRepository")
@patch("app.dispute.worker.submit_dispute_evidence")
@patch("app.dispute.worker.manager")
async def test_worker_claim_and_process_success(
    mock_ws_manager,
    mock_submit_evidence,
    mock_dispute_repo_class,
    mock_session_factory,
    mock_job,
):
    mock_session = MagicMock()
    mock_session.commit = AsyncMock()
    mock_session_factory.return_value.__aenter__.return_value = mock_session

    mock_repo = MagicMock()
    mock_repo.fetch_next_queued_job = AsyncMock(return_value=mock_job)
    mock_repo.update_job_status = AsyncMock()
    mock_repo.append_history = AsyncMock()
    mock_dispute_repo_class.return_value = mock_repo

    mock_submit_evidence.return_value = {
        "outcome": "success",
        "document_id": "doc_worker_123",
        "dispute_id": "disp_worker_test",
    }

    mock_ws_manager.broadcast_system_event = AsyncMock()

    pool = EvidenceWorkerPool(max_concurrency=2)
    job_info = await pool._claim_next_job()
    assert job_info == (101, "disp_worker_test")
    mock_repo.update_job_status.assert_called_with(101, "processing")
    mock_repo.append_history.assert_called_once()

    await pool._process_job_wrapper(101, "disp_worker_test")
    mock_submit_evidence.assert_called_once_with("disp_worker_test")
    mock_repo.update_job_status.assert_called_with(101, "completed")


@patch("app.dispute.worker.async_session_factory")
@patch("app.dispute.worker.DisputeRepository")
@patch("app.dispute.worker.submit_dispute_evidence")
@patch("app.dispute.worker.manager")
async def test_worker_process_sandbox_limitation(
    mock_ws_manager,
    mock_submit_evidence,
    mock_dispute_repo_class,
    mock_session_factory,
):
    mock_session = MagicMock()
    mock_session.commit = AsyncMock()
    mock_session_factory.return_value.__aenter__.return_value = mock_session

    mock_repo = MagicMock()
    mock_repo.update_job_status = AsyncMock()
    mock_dispute_repo_class.return_value = mock_repo

    mock_submit_evidence.return_value = {
        "outcome": "contest_expected_failure",
        "document_id": "doc_sandbox_123",
        "dispute_id": "disp_sandbox_test",
        "razorpay_response": {"error": {"description": "dispute does not exist"}},
    }
    mock_ws_manager.broadcast_system_event = AsyncMock()

    pool = EvidenceWorkerPool(max_concurrency=2)
    await pool._process_job_wrapper(103, "disp_sandbox_test")

    mock_repo.update_job_status.assert_called_with(
        103,
        "contest_expected_failure",
        error_message='{"error": {"description": "dispute does not exist"}}',
    )
    mock_ws_manager.broadcast_system_event.assert_called_with({
        "event": "contest_sandbox_limitation",
        "dispute_id": "disp_sandbox_test",
        "job_id": 103,
        "document_id": "doc_sandbox_123",
        "razorpay_response": {"error": {"description": "dispute does not exist"}},
        "error_message": '{"error": {"description": "dispute does not exist"}}',
    })


@patch("app.dispute.worker.async_session_factory")
@patch("app.dispute.worker.DisputeRepository")
@patch("app.dispute.worker.submit_dispute_evidence")
@patch("app.dispute.worker.manager")
async def test_worker_process_failure_handling(
    mock_ws_manager,
    mock_submit_evidence,
    mock_dispute_repo_class,
    mock_session_factory,
):
    mock_session = MagicMock()
    mock_session.commit = AsyncMock()
    mock_session_factory.return_value.__aenter__.return_value = mock_session

    mock_repo = MagicMock()
    mock_repo.update_job_status = AsyncMock()
    mock_dispute_repo_class.return_value = mock_repo

    mock_submit_evidence.side_effect = Exception("Storage upload network timeout")
    mock_ws_manager.broadcast_system_event = AsyncMock()

    pool = EvidenceWorkerPool(max_concurrency=2)
    await pool._process_job_wrapper(102, "disp_failed_test")

    mock_repo.update_job_status.assert_called_with(102, "failed", error_message="Storage upload network timeout")
    mock_ws_manager.broadcast_system_event.assert_called()


@patch("app.dispute.routes.async_session_factory")
@patch("app.dispute.routes.DisputeRepository")
@patch("app.dispute.routes.manager")
@patch("app.dispute.routes.metrics_service")
@patch("app.dispute.routes.dispute_service")
@patch("app.dispute.worker.evidence_worker")
async def test_resume_dispute_enqueues_evidence_job_on_contest(
    mock_evidence_worker,
    mock_dispute_service,
    mock_metrics,
    mock_ws_manager,
    mock_dispute_repo_class,
    mock_session_factory,
):
    from app.dispute.routes import resume_dispute_and_broadcast

    mock_session = MagicMock()
    mock_session.commit = AsyncMock()
    mock_session_factory.return_value.__aenter__.return_value = mock_session

    mock_repo = MagicMock()
    mock_job = EvidenceJob(id=205, dispute_id="disp_A1001", status="queued")
    mock_repo.create_evidence_job = AsyncMock(return_value=mock_job)
    mock_repo.append_history = AsyncMock()
    mock_repo.update_status = AsyncMock()
    mock_repo.get_dispute = AsyncMock(return_value=MagicMock(amount_paise=50000))
    mock_dispute_repo_class.return_value = mock_repo

    mock_compiled_graph = MagicMock()
    mock_state = MagicMock()
    mock_state.next = None
    mock_state.values = {
        "gate_action": "human_review",
        "case_resolution": "resolved_contested",
    }
    mock_compiled_graph.aget_state = AsyncMock(return_value=mock_state)

    async def mock_stream_resume(*args, **kwargs):
        if False:
            yield {}

    mock_dispute_service.stream_resume = mock_stream_resume
    mock_ws_manager.broadcast_system_event = AsyncMock()
    mock_metrics.on_dispute_resolved = AsyncMock()

    await resume_dispute_and_broadcast("disp_A1001", mock_compiled_graph)

    mock_repo.create_evidence_job.assert_called_once_with("disp_A1001")
    mock_repo.append_history.assert_any_call("disp_A1001", {
        "event": "job_queued",
        "job_id": 205,
        "queued_at": pytest.approx(MagicMock(), abs=10) if False else mock_repo.append_history.call_args_list[0][0][1]["queued_at"],
    })
    mock_session.commit.assert_called()
    mock_evidence_worker.notify.assert_called_once()

