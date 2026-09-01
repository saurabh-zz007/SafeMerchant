import '../utils/display_mappings.dart';

enum DashboardEventTone { info, success, warning, error }

class DashboardEvent {
  const DashboardEvent({
    required this.receivedAt,
    required this.type,
    required this.title,
    required this.description,
    required this.tone,
    this.disputeId,
    this.node,
  });

  final DateTime receivedAt;
  final String type;
  final String title;
  final String description;
  final DashboardEventTone tone;
  final String? disputeId;
  final String? node;

  factory DashboardEvent.fromPayload(Map<String, dynamic> payload) {
    final type = _readString(payload, const ['type', 'event', 'status']) ??
        'node_update';
    final data = _readMap(payload, 'data') ??
        _readMap(payload, 'dispute') ??
        _readMap(payload, 'state_update') ??
        payload;
    final node = _readString(data, const ['node', 'current_node', 'step']) ??
        _readString(payload, const ['node', 'current_node', 'step']);
    final disputeId = _readString(data, const [
          'dispute_id',
          'id',
          'case_id',
        ]) ??
        _readString(payload, const [
          'dispute_id',
          'id',
          'case_id',
        ]);
    final description = _readString(payload, const [
          'message',
          'detail',
          'description',
          'error',
        ]) ??
        _readString(data, const [
          'message',
          'detail',
          'description',
          'recommended_action',
          'human_review_reason',
          'error',
        ]) ??
        'SafeMerchant received an update for the dispute workflow.';

    return DashboardEvent(
      receivedAt: DateTime.now(),
      type: type,
      title: type.toDisplayLabel(),
      description: description.toDisplayLabel(),
      tone: _toneFor(type, data),
      disputeId: disputeId,
      node: node,
    );
  }

  static DashboardEvent text(String text) {
    final closed = text.toLowerCase() == 'closed';
    return DashboardEvent(
      receivedAt: DateTime.now(),
      type: closed ? 'socket_closed' : 'message',
      title: closed ? 'Dashboard Stream Closed' : 'Dashboard Message',
      description: closed
          ? 'The backend closed the live dashboard stream.'
          : text.toDisplayLabel(),
      tone: closed ? DashboardEventTone.warning : DashboardEventTone.info,
    );
  }

  static DashboardEventTone _toneFor(
    String type,
    Map<String, dynamic> data,
  ) {
    final normalizedType = type.toLowerCase();
    final status =
        _readString(data, const ['status', 'outcome', 'state'])?.toLowerCase();
    final node = _readString(data, const ['node', 'current_node', 'step'])
        ?.toLowerCase();

    // Sandbox limitation is expected and informational (not alarming error)
    if (normalizedType.contains('sandbox_limitation') ||
        normalizedType.contains('contest_expected_failure') ||
        status == 'contest_expected_failure' ||
        status == 'contest_ready_sandbox_limitation') {
      return DashboardEventTone.info;
    }

    if (normalizedType.contains('error') ||
        status == 'lost' ||
        status == 'error' ||
        node == 'accept_loss' ||
        (data.containsKey('error') && !normalizedType.contains('sandbox'))) {
      return DashboardEventTone.error;
    }
    if (status == 'won' ||
        status == 'evidence_submitted' ||
        normalizedType.contains('success')) {
      return DashboardEventTone.success;
    }
    if (normalizedType == 'human_review_required' ||
        status == 'paused' ||
        status == 'human_review_required') {
      return DashboardEventTone.warning;
    }
    return DashboardEventTone.info;
  }
}

Map<String, dynamic>? _readMap(Map<String, dynamic> source, String key) {
  final value = source[key];
  return value is Map<String, dynamic> ? value : null;
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
