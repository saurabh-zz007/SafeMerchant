extension BackendDisplayLabel on String? {
  String toDisplayLabel() {
    final value = this?.trim();
    if (value == null || value.isEmpty) {
      return 'Unknown';
    }

    final normalized = value.toLowerCase();
    const labels = {
      'auto_refund': 'Refunded (Auto)',
      'refund_review': 'Refunded (Reviewed)',
      'refund_reviewed': 'Refunded (Reviewed)',
      'auto_submit': 'Contested',
      'human_review': 'Contested (Reviewed)',
      'accept_loss': 'Accepted Loss',
      'accepted_loss': 'Accepted Loss',
      'resolved_refunded': 'Refunded',
      'resolved_contested': 'Contested',
      'resolved_accepted_loss': 'Accepted Loss',
      'human_review_required': 'Action Required: Manual Review',
      'manual_review': 'Manual Review (Failsafe)',
      'manual_review_required': 'Action Required: Manual Review',
      'awaiting_review': 'Awaiting Review',
      'dispute_received': 'New Dispute Received',
      'node_update': 'Workflow Updated',
      'metrics_stale': 'Metrics Stale',
      'metrics_refreshed': 'Metrics Refreshed',
      'accept': 'Submit Evidence',
      'evidence_submitted': 'Evidence Submitted',
      'evidence_submission_success': 'Evidence Submitted Successfully',
      'contest_submitted': 'Contest Submitted',
      'contest_expected_failure': 'Contest Ready — Sandbox Limitation',
      'contest_ready_sandbox_limitation': 'Contest Ready — Sandbox Limitation',
      'contest_submitted_sandbox_limitation': 'Contest Submitted (Sandbox Limitation)',
      'contest_submission_failed': 'Contest Submission Failed',
      'resolved': 'Resolved',
      'won': 'Won',
      'lost': 'Lost',
      'processing': 'Processing',
      'paused': 'Paused',
      'error': 'System Error',
      'chargeback_analysis': 'Chargeback Analysis',
      'evidence_builder': 'Evidence Builder',
      'winnability_scoring': 'Winnability Scoring',
      'representment_submission': 'Representment Submission',
    };

    return labels[normalized] ?? _titleCase(normalized.replaceAll('_', ' '));
  }
}

String _titleCase(String value) {
  return value
      .split(' ')
      .where((part) => part.isNotEmpty)
      .map((part) => part[0].toUpperCase() + part.substring(1))
      .join(' ');
}
