import '../utils/display_mappings.dart';

enum DisputeStatus {
  processing,
  awaitingReview,
  resolved,
  won,
  lost,
  acceptedLoss,
  paused,
  humanReviewRequired,
  evidenceSubmitted,
  contestReadySandboxLimitation,
  error,
  unknown,
}

class Dispute {
  const Dispute({
    required this.id,
    required this.status,
    required this.updatedAt,
    this.amount,
    this.currency,
    this.customerName,
    this.reason,
    this.currentNode,
    this.requiresHumanReview = false,
    this.details = const {},
    this.createdAt,
    this.respondBy,
    this.amountDeducted,
    this.documentId,
    this.storagePath,
    this.evidenceJobId,
    this.evidenceJobStatus,
    this.evidenceJobError,
  });

  final String id;
  final DisputeStatus status;
  final DateTime updatedAt;
  final double? amount;
  final String? currency;
  final String? customerName;
  final String? reason;
  final String? currentNode;
  final bool requiresHumanReview;
  final Map<String, dynamic> details;
  final DateTime? createdAt;
  final DateTime? respondBy;
  final double? amountDeducted;
  final String? documentId;
  final String? storagePath;
  final int? evidenceJobId;
  final String? evidenceJobStatus;
  final String? evidenceJobError;

  String get displayStatus {
    if (requiresHumanReview) {
      return 'Action Required: Manual Review';
    }
    return switch (status) {
      DisputeStatus.processing => 'Processing',
      DisputeStatus.awaitingReview => 'Awaiting Review',
      DisputeStatus.resolved => 'Resolved',
      DisputeStatus.won => 'Won',
      DisputeStatus.lost => 'Lost',
      DisputeStatus.acceptedLoss => 'Accepted Loss',
      DisputeStatus.paused => 'Paused',
      DisputeStatus.humanReviewRequired => 'Action Required: Manual Review',
      DisputeStatus.evidenceSubmitted => 'Evidence Submitted',
      DisputeStatus.contestReadySandboxLimitation => 'Contest Ready — Sandbox Limitation',
      DisputeStatus.error => 'System Error',
      DisputeStatus.unknown => 'Unknown',
    };
  }

  String get workflowLabel => currentNode.toDisplayLabel();

  factory Dispute.fromJson(Map<String, dynamic> json) {
    final details = Map<String, dynamic>.from(json);
    final history = json['history'] as List<dynamic>? ?? [];

    // 1. Extract Webhook Payload
    final webhookEvent = history.firstWhere(
      (item) => item is Map && item['event'] == 'webhook_received',
      orElse: () => <String, dynamic>{},
    ) as Map<String, dynamic>;

    final payload = webhookEvent['data']?['payload'];
    final disputeEntity = payload?['dispute']?['entity'];
    final paymentEntity = payload?['payment']?['entity'];

    if (disputeEntity?['phase'] != null) {
      details['workflow'] = disputeEntity['phase'];
    }

    final rawAmount = json['amount_paise'] ?? paymentEntity?['amount'];
    final amountFromPaise = rawAmount is num ? rawAmount / 100 : null;
    final rawAmountDeducted = json['amount_deducted'] ?? disputeEntity?['amount_deducted'];
    final amountDeductedFromPaise = rawAmountDeducted is num ? rawAmountDeducted / 100 : null;

    DateTime? respondBy;
    final rawRespondBy = json['respond_by'] ?? disputeEntity?['respond_by'];
    if (rawRespondBy is int) {
      respondBy = DateTime.fromMillisecondsSinceEpoch(rawRespondBy * 1000, isUtc: true).toLocal();
    } else if (rawRespondBy != null) {
      respondBy = DateTime.tryParse(rawRespondBy.toString())?.toLocal();
    }

    final statusText = _readString(json, const ['status', 'outcome', 'state'])?.toLowerCase();
    final node = _readString(json, const ['current_node', 'node']);
    final reason =
        _readString(json, const ['reason', 'dispute_reason', 'reason_code']) ??
            disputeEntity?['reason_code']?.toString();
    final email = _readString(
            json, const ['customer_email', 'customer_name', 'customer']) ??
        paymentEntity?['email']?.toString();
    final id = _readString(json, const ['id', 'dispute_id', 'case_id']) ??
        'unknown-dispute';
    final documentId = json['document_id']?.toString() ?? disputeEntity?['document_id']?.toString();
    final storagePath = json['storage_path']?.toString() ?? disputeEntity?['storage_path']?.toString();

    final evidenceJobId = json['evidence_job_id'] is int ? json['evidence_job_id'] as int : null;
    var evidenceJobStatus = json['evidence_job_status']?.toString().toLowerCase();
    var evidenceJobError = json['evidence_job_error']?.toString();

    if (evidenceJobStatus == null || evidenceJobStatus.isEmpty) {
      for (var item in history.reversed) {
        if (item is! Map) continue;
        final ev = item['event']?.toString();
        if (ev == 'contest_submitted_sandbox_limitation') {
          evidenceJobStatus = 'contest_expected_failure';
          evidenceJobError = item['error_message']?.toString() ?? item['razorpay_response']?.toString();
          break;
        } else if (ev == 'contest_submission_failed' || ev == 'evidence_upload_failed' || ev == 'evidence_job_failed') {
          evidenceJobStatus = 'failed';
          evidenceJobError = item['reason']?.toString() ?? item['error']?.toString();
          break;
        } else if (ev == 'contest_submitted' || ev == 'evidence_submitted') {
          evidenceJobStatus = 'completed';
          break;
        } else if (ev == 'job_picked_up') {
          evidenceJobStatus = 'processing';
          break;
        } else if (ev == 'job_queued') {
          evidenceJobStatus = 'queued';
          break;
        }
      }
    }

    bool requiresReview = _readBool(json, 'requires_human_review') ||
        statusText == 'awaiting_review' ||
        statusText == 'human_review_required';

    if (!requiresReview) {
      for (var item in history.reversed) {
        if (item is! Map) continue;
        final ev = item['event']?.toString();
        if (ev == 'human_review_required') {
          requiresReview = true;
          break;
        } else if (ev == 'human_review_submitted' || ev == 'execution_completed_after_review') {
          requiresReview = false;
          break;
        }
      }
    }

    // Determine DisputeStatus based on true DB state & evidence worker progress
    DisputeStatus computedStatus;
    if (requiresReview) {
      computedStatus = DisputeStatus.humanReviewRequired;
    } else if (evidenceJobStatus == 'contest_expected_failure') {
      computedStatus = DisputeStatus.contestReadySandboxLimitation;
    } else if (evidenceJobStatus == 'failed' || statusText == 'error') {
      computedStatus = DisputeStatus.error;
    } else if (evidenceJobStatus == 'completed') {
      computedStatus = DisputeStatus.evidenceSubmitted;
    } else if (evidenceJobStatus == 'queued' || evidenceJobStatus == 'processing' || statusText == 'processing') {
      computedStatus = DisputeStatus.processing;
    } else if (statusText == 'accepted_loss') {
      computedStatus = DisputeStatus.acceptedLoss;
    } else if (statusText == 'lost') {
      computedStatus = DisputeStatus.lost;
    } else if (statusText == 'won') {
      computedStatus = DisputeStatus.won;
    } else if (statusText == 'under_review') {
      computedStatus = DisputeStatus.evidenceSubmitted;
    } else if (statusText == 'resolved') {
      computedStatus = DisputeStatus.resolved;
    } else {
      computedStatus = _statusFrom(statusText, node, requiresReview);
    }

    return Dispute(
      id: id,
      status: computedStatus,
      updatedAt: _readDate(json, const ['updated_at', 'last_updated']) ??
          DateTime.now(),
      amount: _readDouble(json, const ['amount', 'dispute_amount']) ??
          amountFromPaise?.toDouble(),
      currency: json['currency']?.toString() ??
          paymentEntity?['currency']?.toString() ??
          'INR',
      customerName: email ?? (computedStatus == DisputeStatus.processing ? 'Processing...' : 'Customer'),
      reason: reason ?? (computedStatus == DisputeStatus.processing ? 'Processing...' : 'Dispute'),
      currentNode: node ?? _readString(json, const ['phase', 'workflow']) ?? (computedStatus == DisputeStatus.processing ? 'processing' : null),
      requiresHumanReview: requiresReview,
      details: details,
      createdAt: _readDate(json, const ['created_at', 'received_at']),
      respondBy: respondBy,
      amountDeducted: _readDouble(json, const ['amount_deducted']) ??
          amountDeductedFromPaise?.toDouble(),
      documentId: documentId,
      storagePath: storagePath,
      evidenceJobId: evidenceJobId,
      evidenceJobStatus: evidenceJobStatus,
      evidenceJobError: evidenceJobError,
    );
  }
  Dispute copyWith({
    DisputeStatus? status,
    DateTime? updatedAt,
    double? amount,
    String? currency,
    String? customerName,
    String? reason,
    String? currentNode,
    bool? requiresHumanReview,
    Map<String, dynamic>? details,
    DateTime? createdAt,
    DateTime? respondBy,
    double? amountDeducted,
    String? documentId,
    String? storagePath,
    int? evidenceJobId,
    String? evidenceJobStatus,
    String? evidenceJobError,
  }) {
    return Dispute(
      id: id,
      status: status ?? this.status,
      updatedAt: updatedAt ?? this.updatedAt,
      amount: amount ?? this.amount,
      currency: currency ?? this.currency,
      customerName: customerName ?? this.customerName,
      reason: reason ?? this.reason,
      currentNode: currentNode ?? this.currentNode,
      requiresHumanReview: requiresHumanReview ?? this.requiresHumanReview,
      details: details ?? this.details,
      createdAt: createdAt ?? this.createdAt,
      respondBy: respondBy ?? this.respondBy,
      amountDeducted: amountDeducted ?? this.amountDeducted,
      documentId: documentId ?? this.documentId,
      storagePath: storagePath ?? this.storagePath,
      evidenceJobId: evidenceJobId ?? this.evidenceJobId,
      evidenceJobStatus: evidenceJobStatus ?? this.evidenceJobStatus,
      evidenceJobError: evidenceJobError ?? this.evidenceJobError,
    );
  }

  Dispute merge(Map<String, dynamic> update) {
    final merged = {...details, ...update};
    final next = Dispute.fromJson(merged);
    return copyWith(
      status: (next.status == DisputeStatus.unknown) ? status : next.status,
      updatedAt: next.updatedAt,
      amount: next.amount ?? amount,
      currency: next.currency ?? currency,
      customerName: (next.customerName == null || next.customerName == 'Processing...' || next.customerName == 'Customer')
          ? (customerName ?? next.customerName)
          : next.customerName,
      reason: (next.reason == null || next.reason == 'Processing...' || next.reason == 'Dispute')
          ? (reason ?? next.reason)
          : next.reason,
      currentNode: next.currentNode ?? currentNode,
      requiresHumanReview: next.requiresHumanReview,
      details: merged,
      createdAt: next.createdAt ?? createdAt,
      respondBy: next.respondBy ?? respondBy,
      amountDeducted: next.amountDeducted ?? amountDeducted,
      documentId: next.documentId ?? documentId,
      storagePath: next.storagePath ?? storagePath,
      evidenceJobId: next.evidenceJobId ?? evidenceJobId,
      evidenceJobStatus: next.evidenceJobStatus ?? evidenceJobStatus,
      evidenceJobError: next.evidenceJobError ?? evidenceJobError,
    );
  }

  static DisputeStatus _statusFrom(
    String? status,
    String? node,
    bool reviewRequired,
  ) {
    if (reviewRequired) {
      return DisputeStatus.humanReviewRequired;
    }

    final normalized = (status ?? node ?? '').toLowerCase();
    if (normalized.contains('sandbox_limitation') || normalized.contains('contest_expected_failure') || normalized.contains('contest_ready')) {
      return DisputeStatus.contestReadySandboxLimitation;
    }
    if (normalized.contains('won') || normalized == 'success') {
      return DisputeStatus.won;
    }
    if (normalized.contains('accepted_loss')) {
      return DisputeStatus.acceptedLoss;
    }
    if (normalized.contains('lost') || normalized == 'accept_loss') {
      return DisputeStatus.lost;
    }
    if (normalized == 'awaiting_review') {
      return DisputeStatus.awaitingReview;
    }
    if (normalized == 'resolved') {
      return DisputeStatus.resolved;
    }
    if (normalized.contains('error') || normalized.contains('failed')) {
      return DisputeStatus.error;
    }
    if (normalized.contains('paused')) {
      return DisputeStatus.paused;
    }
    if (normalized.contains('evidence_submitted')) {
      return DisputeStatus.evidenceSubmitted;
    }
    if (normalized.isEmpty || normalized == 'unknown' || normalized == 'received' || normalized == 'processing') {
      return DisputeStatus.processing;
    }
    return DisputeStatus.processing;
  }
}

String? _readString(Map<String, dynamic> source, List<String> keys) {
  for (final key in keys) {
    final value = source[key];
    if (value != null && value.toString().trim().isNotEmpty) {
      return value.toString();
    }
  }
  return null;
}

bool _readBool(Map<String, dynamic> source, String key) {
  final value = source[key];
  if (value is bool) {
    return value;
  }
  return value?.toString().toLowerCase() == 'true';
}

double? _readDouble(Map<String, dynamic> source, List<String> keys) {
  for (final key in keys) {
    final value = source[key];
    if (value is num) {
      return value.toDouble();
    }
    if (value is String) {
      return double.tryParse(value);
    }
  }
  return null;
}

DateTime? _readDate(Map<String, dynamic> source, List<String> keys) {
  for (final key in keys) {
    final value = source[key];
    if (value is DateTime) {
      return value;
    }
    if (value != null) {
      return DateTime.tryParse(value.toString());
    }
  }
  return null;
}
