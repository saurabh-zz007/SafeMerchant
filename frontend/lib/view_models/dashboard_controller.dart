import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:get/get.dart';

import '../models/dashboard_event.dart';
import '../models/dispute.dart';
import '../models/metrics.dart';
import '../services/dispute_api_service.dart';
import '../services/server_activity_socket_service.dart';

enum DashboardConnectionStatus {
  disconnected,
  loading,
  connecting,
  connected,
  error,
}

class DashboardController extends GetxController {
  DashboardController({
    DisputeApiService? apiService,
    ServerActivitySocketService? socketService,
    bool autoStart = true,
  })  : _apiService = apiService ?? DisputeApiService(),
        _socketService = socketService ?? ServerActivitySocketService() {
    if (autoStart) {
      unawaited(start());
    }
  }

  bool _useLocalServer = true;
  bool get useLocalServer => _useLocalServer;

  String get apiBaseUrl => _useLocalServer
      ? 'http://${const String.fromEnvironment('LOCAL_SERVER_URL', defaultValue: 'localhost:8000')}'
      : 'https://${const String.fromEnvironment('CLOUD_SERVER_URL', defaultValue: 'safemerchant.onrender.com')}';

  String get websocketUrl => _useLocalServer
      ? 'ws://${const String.fromEnvironment('LOCAL_SERVER_URL', defaultValue: 'localhost:8000')}/ws/dashboard'
      : 'wss://${const String.fromEnvironment('CLOUD_SERVER_URL', defaultValue: 'safemerchant.onrender.com')}/ws/dashboard';

  final DisputeApiService _apiService;
  final ServerActivitySocketService _socketService;

  StreamSubscription<BackendSocketMessage>? _messageSubscription;

  DashboardConnectionStatus _connectionStatus =
      DashboardConnectionStatus.disconnected;
  final List<Dispute> _disputes = [];
  final List<DashboardEvent> _events = [];
  final Map<String, BreakdownGroup> _breakdowns = {};
  List<RepeatPattern> _repeatPatterns = [];
  List<AuditEntry> _selectedAuditEntries = [];
  MetricsSummary? _metricsSummary;
  String? _selectedDisputeId;
  String? _errorMessage;
  String? _healthStatus;
  bool _isSubmittingReview = false;
  bool _isLoadingMetrics = false;
  bool _isEditingDispute = false;
  bool _isResettingDatabase = false;
  Map<String, dynamic>? _pendingReviewPayload;

  DashboardConnectionStatus get connectionStatus => _connectionStatus;
  List<Dispute> get disputes => List.unmodifiable(_disputes);
  List<DashboardEvent> get events => List.unmodifiable(_events);
  MetricsSummary? get metricsSummary => _metricsSummary;
  Map<String, BreakdownGroup> get breakdowns => Map.unmodifiable(_breakdowns);
  List<RepeatPattern> get repeatPatterns => List.unmodifiable(_repeatPatterns);
  List<AuditEntry> get selectedAuditEntries =>
      List.unmodifiable(_selectedAuditEntries);
  String? get errorMessage => _errorMessage;
  String? get healthStatus => _healthStatus;
  bool get isSubmittingReview => _isSubmittingReview;
  bool get isLoadingMetrics => _isLoadingMetrics;
  bool get isEditingDispute => _isEditingDispute;
  bool get isResettingDatabase => _isResettingDatabase;
  Map<String, dynamic>? get pendingReviewPayload => _pendingReviewPayload;
  bool get isBusy =>
      _connectionStatus == DashboardConnectionStatus.loading ||
      _connectionStatus == DashboardConnectionStatus.connecting;

  Dispute? get selectedDispute {
    if (_disputes.isEmpty) {
      return null;
    }
    final id = _selectedDisputeId;
    if (id == null) {
      return _disputes.first;
    }
    return _disputes.cast<Dispute?>().firstWhere((dispute) => dispute?.id == id,
        orElse: () => _disputes.first);
  }

  int get actionRequiredCount =>
      _disputes.where((dispute) => dispute.requiresHumanReview).length;

  int get wonCount =>
      _disputes.where((dispute) => dispute.status == DisputeStatus.won).length;

  int get lostCount =>
      _disputes.where((dispute) => dispute.status == DisputeStatus.lost).length;

  Future<void> start() async {
    _errorMessage = null;
    _setConnectionStatus(DashboardConnectionStatus.loading);

    try {
      final results = await Future.wait([
        _apiService.fetchDisputes(apiBaseUrl),
        _apiService.fetchHealth(apiBaseUrl),
      ]);
      final disputes = results[0] as List<Dispute>;
      final health = results[1] as Map<String, dynamic>;
      _healthStatus = health['status']?.toString();
      _disputes
        ..clear()
        ..addAll(disputes);
      _sortDisputes();
      _selectedDisputeId ??= _firstActionableDisputeId() ??
          (_disputes.isEmpty ? null : _disputes.first.id);
      _prependEvent(
        DashboardEvent(
          receivedAt: DateTime.now(),
          type: 'initial_load',
          title: 'Disputes Loaded',
          description: 'Loaded ${_disputes.length} historical disputes.',
          tone: DashboardEventTone.success,
        ),
      );
    } catch (error) {
      _errorMessage = error.toString();
      _prependEvent(
        DashboardEvent(
          receivedAt: DateTime.now(),
          type: 'initial_load_error',
          title: 'Unable To Load Disputes',
          description: error.toString(),
          tone: DashboardEventTone.error,
        ),
      );
    }

    unawaited(refreshMetrics());
    unawaited(refreshSelectedAudit());
    await _connectSocket();
  }

  Future<void> reconnect() async {
    await _messageSubscription?.cancel();
    _messageSubscription = null;
    await _socketService.disconnect();
    await start();
  }

  Future<void> setUseLocalServer(bool value) async {
    if (_useLocalServer == value) return;
    _useLocalServer = value;
    _prependEvent(
      DashboardEvent(
        receivedAt: DateTime.now(),
        type: 'env_switch',
        title: 'Environment Switched',
        description: 'Switched environment to ${value ? 'Local' : 'Cloud'}. Reconnecting...',
        tone: DashboardEventTone.info,
      ),
    );
    update();
    await reconnect();
  }

  Future<void> resetDatabase() async {
    if (_isResettingDatabase) return;
    _isResettingDatabase = true;
    _errorMessage = null;
    update();

    try {
      final response = await _apiService.resetDatabase(apiBaseUrl);
      _prependEvent(
        DashboardEvent(
          receivedAt: DateTime.now(),
          type: 'database_reset',
          title: 'Database Wiped',
          description: response['message']?.toString() ?? 'Database has been reset successfully.',
          tone: DashboardEventTone.success,
        ),
      );
      await _reloadDisputes();
      _selectedDisputeId = null;
      _selectedAuditEntries = [];
      unawaited(refreshMetrics());
    } catch (error) {
      _errorMessage = error.toString();
      _prependEvent(
        DashboardEvent(
          receivedAt: DateTime.now(),
          type: 'reset_error',
          title: 'Database Reset Failed',
          description: error.toString(),
          tone: DashboardEventTone.error,
        ),
      );
    } finally {
      _isResettingDatabase = false;
      update();
    }
  }

  void selectDispute(String disputeId) {
    _selectedDisputeId = disputeId;
    _selectedAuditEntries = [];
    unawaited(refreshSelectedAudit());
    update();
  }

  Future<void> refreshMetrics() async {
    _isLoadingMetrics = true;
    _errorMessage = null;
    update();

    final now = DateTime.now();
    final from = DateTime(now.year, now.month, now.day)
        .subtract(const Duration(days: 29));
    final to = DateTime(now.year, now.month, now.day);

    try {
      final results = await Future.wait([
        _apiService.fetchMetricsSummary(
            baseUrl: apiBaseUrl, from: from, to: to),
        _apiService.fetchBreakdown(baseUrl: apiBaseUrl, by: 'reason_code'),
        _apiService.fetchBreakdown(baseUrl: apiBaseUrl, by: 'outcome'),
        _apiService.fetchBreakdown(baseUrl: apiBaseUrl, by: 'phase'),
        _apiService.fetchRepeatPatterns(baseUrl: apiBaseUrl),
      ]);
      _metricsSummary = results[0] as MetricsSummary;
      _breakdowns
        ..clear()
        ..addAll({
          'reason_code': results[1] as BreakdownGroup,
          'outcome': results[2] as BreakdownGroup,
          'phase': results[3] as BreakdownGroup,
        });
      _repeatPatterns = results[4] as List<RepeatPattern>;
      _prependEvent(
        DashboardEvent(
          receivedAt: DateTime.now(),
          type: 'metrics_refreshed',
          title: 'Metrics Refreshed',
          description: 'Dashboard metrics were refreshed from the backend.',
          tone: DashboardEventTone.success,
        ),
      );
    } catch (error) {
      _errorMessage = error.toString();
      _prependEvent(
        DashboardEvent(
          receivedAt: DateTime.now(),
          type: 'metrics_error',
          title: 'Metrics Refresh Failed',
          description: error.toString(),
          tone: DashboardEventTone.error,
        ),
      );
    } finally {
      _isLoadingMetrics = false;
      update();
    }
  }

  Future<void> refreshSelectedAudit() async {
    final dispute = selectedDispute;
    if (dispute == null) {
      return;
    }

    try {
      _selectedAuditEntries = await _apiService.fetchAudit(
        baseUrl: apiBaseUrl,
        disputeId: dispute.id,
      );
      update();
    } catch (_) {
      _selectedAuditEntries = [];
      update();
    }
  }

  Future<void> refreshDispute(String disputeId) async {
    try {
      final dispute = await _apiService.fetchDispute(apiBaseUrl, disputeId);
      final index = _disputes.indexWhere((d) => d.id == disputeId);
      if (index == -1) {
        _disputes.add(dispute);
      } else {
        _disputes[index] = dispute;
      }
      _sortDisputes();
      update();
    } catch (e) {
      debugPrint('Error refreshing dispute: $e');
    }
  }

  void clearPendingReview() {
    _pendingReviewPayload = null;
    update();
  }

  Future<void> submitReview(String action, {String? disputeId}) =>
      submitReviewWithReason(action, '', disputeId: disputeId);

  Future<void> submitReviewWithReason(String action, String reason, {String? disputeId}) async {
    final id = disputeId ??
        _pendingReviewPayload?['dispute_id']?.toString() ??
        selectedDispute?.id;
    if (id == null || _isSubmittingReview) {
      return;
    }

    _isSubmittingReview = true;
    _errorMessage = null;
    update();

    try {
      final response = await _apiService.submitReview(
        baseUrl: apiBaseUrl,
        disputeId: id,
        action: action,
        reason: reason,
      );
      final updatePayload = _extractDisputePayload(response) ??
          {
            'dispute_id': id,
            'status': action == 'accept' ? 'evidence_submitted' : 'lost',
            'current_node': action,
            'requires_human_review': false,
          };
      _upsertDispute(updatePayload);
      if (id == _pendingReviewPayload?['dispute_id']?.toString()) {
        _pendingReviewPayload = null;
      }
      _prependEvent(
        DashboardEvent(
          receivedAt: DateTime.now(),
          type: action,
          title: action == 'accept'
              ? 'Evidence Submitted Successfully'
              : 'Loss Accepted',
          description: 'Review decision submitted for dispute $id.',
          tone: action == 'accept'
              ? DashboardEventTone.success
              : DashboardEventTone.error,
          disputeId: id,
          node: action,
        ),
      );
    } catch (error) {
      _errorMessage = error.toString();
      _prependEvent(
        DashboardEvent(
          receivedAt: DateTime.now(),
          type: 'review_error',
          title: 'Review Submission Failed',
          description: error.toString(),
          tone: DashboardEventTone.error,
          disputeId: id,
        ),
      );
    } finally {
      _isSubmittingReview = false;
      update();
    }
  }

  Future<void> editSelectedDispute({
    String? status,
    int? amountPaise,
    String? reasonCode,
    String? outcome,
    String? note,
  }) async {
    final dispute = selectedDispute;
    if (dispute == null || _isEditingDispute) {
      return;
    }

    _isEditingDispute = true;
    _errorMessage = null;
    update();

    try {
      await _apiService.patchDispute(
        baseUrl: apiBaseUrl,
        disputeId: dispute.id,
        status: status,
        amountPaise: amountPaise,
        reasonCode: reasonCode,
        outcome: outcome,
        note: note,
      );
      await _reloadDisputes();
      await refreshSelectedAudit();
      unawaited(refreshMetrics());
      _prependEvent(
        DashboardEvent(
          receivedAt: DateTime.now(),
          type: 'dispute_edited',
          title: 'Dispute Updated',
          description: 'Manual correction saved for dispute ${dispute.id}.',
          tone: DashboardEventTone.success,
          disputeId: dispute.id,
        ),
      );
    } catch (error) {
      _errorMessage = error.toString();
      _prependEvent(
        DashboardEvent(
          receivedAt: DateTime.now(),
          type: 'edit_error',
          title: 'Dispute Update Failed',
          description: error.toString(),
          tone: DashboardEventTone.error,
          disputeId: dispute.id,
        ),
      );
    } finally {
      _isEditingDispute = false;
      update();
    }
  }

  Future<String?> fetchEvidencePdfUrl(String disputeId) async {
    try {
      return await _apiService.fetchEvidencePdfUrl(
        baseUrl: apiBaseUrl,
        disputeId: disputeId,
      );
    } catch (error) {
      _errorMessage = error.toString();
      update();
      return null;
    }
  }

  Future<void> retryEvidenceJob(String disputeId) async {
    try {
      await _apiService.retryEvidenceJob(
        baseUrl: apiBaseUrl,
        disputeId: disputeId,
      );
      await refreshDispute(disputeId);
      _prependEvent(
        DashboardEvent(
          receivedAt: DateTime.now(),
          type: 'job_queued',
          title: 'Evidence Generation Retried',
          description: 'Queued retry job for dispute $disputeId.',
          tone: DashboardEventTone.info,
          disputeId: disputeId,
        ),
      );
    } catch (error) {
      _errorMessage = error.toString();
      _prependEvent(
        DashboardEvent(
          receivedAt: DateTime.now(),
          type: 'evidence_upload_failed',
          title: 'Retry Failed',
          description: error.toString(),
          tone: DashboardEventTone.error,
          disputeId: disputeId,
        ),
      );
      update();
    }
  }

  @override
  void onClose() {
    unawaited(_messageSubscription?.cancel());
    unawaited(_socketService.dispose());
    _apiService.close();
    super.onClose();
  }

  Future<void> _connectSocket() async {
    _setConnectionStatus(DashboardConnectionStatus.connecting);
    await _messageSubscription?.cancel();
    _messageSubscription = _socketService.messages.listen(_handleSocketMessage);

    try {
      await _socketService.connect(websocketUrl);
      _setConnectionStatus(DashboardConnectionStatus.connected);
      _prependEvent(
        DashboardEvent(
          receivedAt: DateTime.now(),
          type: 'socket_connected',
          title: 'Live Dashboard Connected',
          description: 'Listening for new disputes and workflow updates.',
          tone: DashboardEventTone.success,
        ),
      );
    } catch (error) {
      _errorMessage = error.toString();
      _setConnectionStatus(DashboardConnectionStatus.error);
      _prependEvent(
        DashboardEvent(
          receivedAt: DateTime.now(),
          type: 'socket_error',
          title: 'Live Dashboard Connection Failed',
          description: error.toString(),
          tone: DashboardEventTone.error,
        ),
      );
    }
  }

  void _handleSocketMessage(BackendSocketMessage message) {
    if (message.payload == null) {
      _prependEvent(DashboardEvent.text(message.text ?? 'Backend update'));
      return;
    }

    final payload = message.payload!;
    final event = DashboardEvent.fromPayload(payload);
    _prependEvent(event);

    final eventType = event.type.toLowerCase();
    
    // Intercept database_reset event from websocket
    if (eventType == 'database_reset') {
      unawaited(_reloadDisputes());
      _selectedDisputeId = null;
      _selectedAuditEntries = [];
      unawaited(refreshMetrics());
      return;
    }

    if (eventType == 'metrics_stale') {
      unawaited(refreshMetrics());
      return;
    }

    if (eventType == 'dispute_received' ||
        eventType == 'node_update' ||
        eventType == 'human_review_required' ||
        eventType == 'execution_completed' ||
        eventType == 'review_submitted' ||
        eventType == 'execution_error') {
      final updatePayload = _extractDisputePayload(payload) ?? payload;
      final decoratedUpdate = {
        ...updatePayload,
        if (eventType == 'human_review_required') 'requires_human_review': true,
        if (eventType == 'human_review_required') 'status': 'awaiting_review',
        if (eventType == 'execution_completed') 'status': 'resolved',
        if (eventType == 'execution_error') 'status': 'error',
        if (event.disputeId != null) 'dispute_id': event.disputeId,
      };
      _upsertDispute(decoratedUpdate);
      if (eventType == 'human_review_required') {
        _selectedDisputeId = event.disputeId ?? _readDisputeId(decoratedUpdate);
        _pendingReviewPayload = payload;
      }
      unawaited(refreshMetrics());
      unawaited(refreshSelectedAudit());
    }
  }

  Future<void> _reloadDisputes() async {
    final disputes = await _apiService.fetchDisputes(apiBaseUrl);
    _disputes
      ..clear()
      ..addAll(disputes);
    _sortDisputes();
    update();
  }

  void _upsertDispute(Map<String, dynamic> updatePayload) {
    final id = _readDisputeId(updatePayload);
    if (id == null) {
      return;
    }

    final index = _disputes.indexWhere((dispute) => dispute.id == id);
    if (index == -1) {
      _disputes.add(Dispute.fromJson(updatePayload));
    } else {
      _disputes[index] = _disputes[index].merge(updatePayload);
    }
    _sortDisputes();
    _selectedDisputeId ??= id;
    update();
  }

  Map<String, dynamic>? _extractDisputePayload(Map<String, dynamic> payload) {
    for (final key in const ['dispute', 'data', 'state_update']) {
      final value = payload[key];
      if (value is Map<String, dynamic>) {
        return value;
      }
    }
    return null;
  }

  String? _readDisputeId(Map<String, dynamic> source) {
    for (final key in const ['dispute_id', 'id', 'case_id']) {
      final value = source[key];
      if (value != null && value.toString().trim().isNotEmpty) {
        return value.toString();
      }
    }
    return null;
  }

  String? _firstActionableDisputeId() {
    for (final dispute in _disputes) {
      if (dispute.requiresHumanReview) {
        return dispute.id;
      }
    }
    return null;
  }

  void _sortDisputes() {
    _disputes.sort((a, b) {
      if (a.requiresHumanReview != b.requiresHumanReview) {
        return a.requiresHumanReview ? -1 : 1;
      }
      return b.updatedAt.compareTo(a.updatedAt);
    });
  }

  void _setConnectionStatus(DashboardConnectionStatus status) {
    _connectionStatus = status;
    update();
  }

  void _prependEvent(DashboardEvent event) {
    _events.insert(0, event);
    if (_events.length > 100) {
      _events.removeLast();
    }
    update();
  }
}
