extension BackendDisplayLabel on String? {
  String toDisplayLabel() {
    final value = this?.trim();
    if (value == null || value.isEmpty) {
      return 'Unknown';
    }

    final normalized = value.toLowerCase();
    const labels = {
      'accept_loss': 'Loss Automatically Accepted',
      'human_review_required': 'Action Required: Manual Review',
      'awaiting_review': 'Awaiting Review',
      'dispute_received': 'New Dispute Received',
      'node_update': 'Workflow Updated',
      'metrics_stale': 'Metrics Stale',
      'metrics_refreshed': 'Metrics Refreshed',
      'accept': 'Submit Evidence',
      'evidence_submitted': 'Evidence Submitted',
      'evidence_submission_success': 'Evidence Submitted Successfully',
      'resolved': 'Resolved',
      'accepted_loss': 'Accepted Loss',
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
