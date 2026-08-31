import 'dart:async';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:get/get.dart';
import 'package:syncfusion_flutter_pdfviewer/pdfviewer.dart';

import '../models/dispute.dart';
import '../theme/theme_provider.dart';
import '../utils/display_mappings.dart';
import '../view_models/dashboard_controller.dart';
import 'settings_screen.dart';

enum DashboardSection { overview, disputes, analytics, settings }

class MainDashboardLayout extends StatefulWidget {
  const MainDashboardLayout({
    super.key,
    required this.viewModel,
    required this.themeProvider,
  });

  final DashboardController viewModel;
  final ThemeProvider themeProvider;

  @override
  State<MainDashboardLayout> createState() => _MainDashboardLayoutState();
}

class _MainDashboardLayoutState extends State<MainDashboardLayout> {
  DashboardSection _section = DashboardSection.overview;
  bool _reviewDialogOpen = false;

  @override
  void initState() {
    super.initState();
    widget.viewModel.addListener(_onViewModelChanged);
  }

  @override
  void dispose() {
    widget.viewModel.removeListener(_onViewModelChanged);
    super.dispose();
  }

  void _onViewModelChanged() {
    if (widget.viewModel.pendingReviewPayload != null && !_reviewDialogOpen) {
      _reviewDialogOpen = true;
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (!mounted) return;
        showDialog<void>(
          context: context,
          barrierDismissible: false,
          builder: (_) => _HilReviewDialog(
            viewModel: widget.viewModel,
            payload: widget.viewModel.pendingReviewPayload!,
          ),
        ).then((_) {
          _reviewDialogOpen = false;
          widget.viewModel.clearPendingReview();
        });
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Scaffold(
      body: Row(
        children: [
          _Sidebar(
            selected: _section,
            themeProvider: widget.themeProvider,
            onSelected: (section) => setState(() => _section = section),
          ),
          VerticalDivider(width: 1, color: theme.dividerColor),
          Expanded(
            child: Column(
              children: [
                _TopBar(
                  section: _section,
                  viewModel: widget.viewModel,
                  themeProvider: widget.themeProvider,
                ),
                Divider(height: 1, color: theme.dividerColor),
                Expanded(
                  child: GetBuilder<DashboardController>(
                    init: widget.viewModel,
                    builder: (viewModel) {
                      return IndexedStack(
                        index: _section.index,
                        children: [
                          OverviewScreen(viewModel: viewModel),
                          DisputesScreen(viewModel: viewModel),
                          AnalyticsScreen(viewModel: viewModel),
                          SettingsScreen(
                            themeProvider: widget.themeProvider,
                            dashboardController: viewModel,
                          ),
                        ],
                      );
                    },
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _HilReviewDialog extends StatefulWidget {
  const _HilReviewDialog({
    required this.viewModel,
    required this.payload,
  });

  final DashboardController viewModel;
  final Map<String, dynamic> payload;

  @override
  State<_HilReviewDialog> createState() => _HilReviewDialogState();
}

class _HilReviewDialogState extends State<_HilReviewDialog> {
  final _reasonController = TextEditingController();
  bool _submitting = false;

  Map<String, dynamic> get _data =>
      (widget.payload['data'] as Map<String, dynamic>?) ?? widget.payload;

  String get _disputeId =>
      widget.payload['dispute_id']?.toString() ?? 'Unknown';

  String? get _winnabilityLabel {
    final score = _data['winnability_score'];
    if (score == null) return null;
    final pct = (score is num ? score.toDouble() : double.tryParse('$score'));
    if (pct == null) return null;
    return '${(pct * 100).toStringAsFixed(1)}%';
  }

  String? get _recommendedAction =>
      _data['recommended_action']?.toString() ??
      _data['gate_action']?.toString();

  String? get _reviewReason =>
      _data['human_review_reason']?.toString();

  List<String> get _riskFactors {
    final factors = _data['risk_factors'];
    if (factors is List) {
      return factors.map((e) => e.toString()).toList();
    }
    return const [];
  }

  String? get _draftLetter =>
      _data['draft_response_letter']?.toString() ??
      _data['verified_explanation_letter']?.toString() ??
      _data['draft_explanation_letter']?.toString();

  String? get _customerEmail => _data['customer_email']?.toString();

  String? get _amount {
    final amt = _data['disputed_amount_inr'] ?? _data['amount'];
    if (amt == null) return null;
    if (amt is num) return 'INR ${(amt / 100).toStringAsFixed(2)}';
    return amt.toString();
  }

  Future<void> _submit(String action) async {
    setState(() => _submitting = true);
    await widget.viewModel
        .submitReviewWithReason(action, _reasonController.text.trim());
    if (mounted) Navigator.of(context).pop();
  }

  @override
  void dispose() {
    _reasonController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Dialog(
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(10),
        side: BorderSide(color: theme.dividerColor),
      ),
      elevation: 0,
      backgroundColor: theme.colorScheme.surface,
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 680, maxHeight: 720),
        child: Padding(
          padding: const EdgeInsets.all(28),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              // ── Header ──
              Row(
                children: [
                  Container(
                    width: 38,
                    height: 38,
                    alignment: Alignment.center,
                    decoration: BoxDecoration(
                      color: theme.colorScheme.error.withValues(alpha: 0.12),
                      borderRadius: BorderRadius.circular(8),
                    ),
                    child: Icon(Icons.gavel,
                        color: theme.colorScheme.error, size: 20),
                  ),
                  const SizedBox(width: 14),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          'Human Review Required',
                          style: theme.textTheme.titleMedium?.copyWith(
                            fontWeight: FontWeight.w700,
                          ),
                        ),
                        const SizedBox(height: 2),
                        Text(
                          'Dispute $_disputeId',
                          style: theme.textTheme.bodySmall,
                        ),
                      ],
                    ),
                  ),
                  IconButton(
                    onPressed: _submitting
                        ? null
                        : () => Navigator.of(context).pop(),
                    icon: const Icon(Icons.close, size: 20),
                    tooltip: 'Dismiss',
                  ),
                ],
              ),

              Divider(height: 28, color: theme.dividerColor),

              // ── Scrollable content ──
              Flexible(
                child: SingleChildScrollView(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      // Dispute context
                      if (_customerEmail != null || _amount != null)
                        Container(
                          padding: const EdgeInsets.all(14),
                          decoration: BoxDecoration(
                            border: Border.all(color: theme.dividerColor),
                            borderRadius: BorderRadius.circular(8),
                          ),
                          child: Wrap(
                            spacing: 24,
                            runSpacing: 8,
                            children: [
                              if (_customerEmail != null)
                                _InfoChip(
                                    label: 'Customer',
                                    value: _customerEmail!),
                              if (_amount != null)
                                _InfoChip(label: 'Amount', value: _amount!),
                              if (_data['reason_code'] != null)
                                _InfoChip(
                                  label: 'Reason',
                                  value: _data['reason_code'].toString(),
                                ),
                            ],
                          ),
                        ),

                      const SizedBox(height: 16),

                      // Agent analysis
                      Container(
                        padding: const EdgeInsets.all(14),
                        decoration: BoxDecoration(
                          border: Border.all(color: theme.dividerColor),
                          borderRadius: BorderRadius.circular(8),
                        ),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text('Agent Analysis',
                                style: theme.textTheme.titleSmall),
                            const SizedBox(height: 12),
                            Wrap(
                              spacing: 20,
                              runSpacing: 8,
                              children: [
                                if (_winnabilityLabel != null)
                                  _InfoChip(
                                    label: 'Winnability',
                                    value: _winnabilityLabel!,
                                  ),
                                if (_recommendedAction != null)
                                  _InfoChip(
                                    label: 'Recommended',
                                    value: _recommendedAction!,
                                  ),
                              ],
                            ),
                            if (_reviewReason != null) ...[
                              const SizedBox(height: 10),
                              Text(
                                'Review reason: $_reviewReason',
                                style: theme.textTheme.bodySmall,
                              ),
                            ],
                            if (_riskFactors.isNotEmpty) ...[
                              const SizedBox(height: 10),
                              Text('Risk Factors:',
                                  style: theme.textTheme.labelMedium),
                              const SizedBox(height: 4),
                              Wrap(
                                spacing: 6,
                                runSpacing: 4,
                                children: _riskFactors
                                    .map((f) => Container(
                                          padding: const EdgeInsets.symmetric(
                                              horizontal: 8, vertical: 4),
                                          decoration: BoxDecoration(
                                            border: Border.all(
                                                color: theme.dividerColor),
                                            borderRadius:
                                                BorderRadius.circular(4),
                                          ),
                                          child: Text(f,
                                              style:
                                                  theme.textTheme.bodySmall),
                                        ))
                                    .toList(),
                              ),
                            ],
                          ],
                        ),
                      ),

                      // Draft response letter preview
                      if (_draftLetter != null) ...[
                        const SizedBox(height: 16),
                        Container(
                          padding: const EdgeInsets.all(14),
                          constraints: const BoxConstraints(maxHeight: 180),
                          decoration: BoxDecoration(
                            border: Border.all(color: theme.dividerColor),
                            borderRadius: BorderRadius.circular(8),
                          ),
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text('Draft Response',
                                  style: theme.textTheme.titleSmall),
                              const SizedBox(height: 8),
                              Expanded(
                                child: SingleChildScrollView(
                                  child: Text(
                                    _draftLetter!,
                                    style: theme.textTheme.bodySmall?.copyWith(
                                      fontFamily: 'monospace',
                                      height: 1.5,
                                    ),
                                  ),
                                ),
                              ),
                            ],
                          ),
                        ),
                      ],

                      // Reason field
                      const SizedBox(height: 16),
                      TextField(
                        controller: _reasonController,
                        maxLines: 2,
                        decoration: const InputDecoration(
                          labelText: 'Reason (optional)',
                          hintText: 'Add a note explaining your decision...',
                          border: OutlineInputBorder(),
                        ),
                      ),
                    ],
                  ),
                ),
              ),

              // ── Action buttons ──
              const SizedBox(height: 20),
              Row(
                children: [
                  Expanded(
                    child: OutlinedButton.icon(
                      onPressed: _submitting ? null : () => _submit('reject'),
                      icon: const Icon(Icons.close, size: 18),
                      label: const Text('Accept Loss'),
                      style: OutlinedButton.styleFrom(
                        padding: const EdgeInsets.symmetric(vertical: 14),
                        foregroundColor: theme.colorScheme.error,
                        side: BorderSide(color: theme.colorScheme.error),
                      ),
                    ),
                  ),
                  const SizedBox(width: 14),
                  Expanded(
                    child: FilledButton.icon(
                      onPressed: _submitting ? null : () => _submit('accept'),
                      icon: _submitting
                          ? const SizedBox(
                              width: 16,
                              height: 16,
                              child: CircularProgressIndicator(
                                  strokeWidth: 2, color: Colors.white),
                            )
                          : const Icon(Icons.send, size: 18),
                      label: const Text('Submit Evidence'),
                      style: FilledButton.styleFrom(
                        padding: const EdgeInsets.symmetric(vertical: 14),
                      ),
                    ),
                  ),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _InfoChip extends StatelessWidget {
  const _InfoChip({required this.label, required this.value});

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: [
        Text(label, style: theme.textTheme.bodySmall),
        const SizedBox(height: 2),
        Text(
          value,
          style: theme.textTheme.titleSmall?.copyWith(
            fontWeight: FontWeight.w700,
          ),
        ),
      ],
    );
  }
}

class _DisputeDetailsDialog extends StatefulWidget {
  const _DisputeDetailsDialog({
    required this.viewModel,
    required this.disputeId,
  });

  final DashboardController viewModel;
  final String disputeId;

  @override
  State<_DisputeDetailsDialog> createState() => _DisputeDetailsDialogState();
}

class _DisputeDetailsDialogState extends State<_DisputeDetailsDialog> {
  final _reasonController = TextEditingController();
  bool _submitting = false;
  bool _fetchingPdf = false;

  @override
  void initState() {
    super.initState();
    unawaited(widget.viewModel.refreshDispute(widget.disputeId));
  }

  @override
  void dispose() {
    _reasonController.dispose();
    super.dispose();
  }

  Future<void> _submitReview(String action) async {
    setState(() => _submitting = true);
    await widget.viewModel.submitReviewWithReason(
      action,
      _reasonController.text.trim(),
      disputeId: widget.disputeId,
    );
    await widget.viewModel.refreshDispute(widget.disputeId);
    if (mounted) {
      setState(() => _submitting = false);
      _reasonController.clear();
    }
  }

  Future<void> _viewEvidencePdf(Dispute dispute) async {
    setState(() => _fetchingPdf = true);
    try {
      final url = await widget.viewModel.fetchEvidencePdfUrl(dispute.id);
      if (mounted) {
        setState(() => _fetchingPdf = false);
        if (url != null && url.isNotEmpty) {
          _showPdfViewerDialog(context, url, dispute);
        } else {
          ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(
              content: Text('Evidence PDF is queued, generating, or not yet available.'),
              backgroundColor: Colors.orange,
            ),
          );
        }
      }
    } catch (e) {
      if (mounted) {
        setState(() => _fetchingPdf = false);
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('Failed to get signed PDF URL: $e'),
            backgroundColor: Colors.red,
          ),
        );
      }
    }
  }

  void _showPdfViewerDialog(BuildContext context, String signedUrl, Dispute dispute) {
    showDialog(
      context: context,
      builder: (ctx) => _EvidencePdfViewerDialog(
        signedUrl: signedUrl,
        dispute: dispute,
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return AnimatedBuilder(
      animation: widget.viewModel,
      builder: (context, _) {
        final disputeIndex = widget.viewModel.disputes.indexWhere((d) => d.id == widget.disputeId);
        final dispute = disputeIndex != -1 ? widget.viewModel.disputes[disputeIndex] : null;

        if (dispute == null) {
          return Dialog(
            shape: RoundedRectangleBorder(
              borderRadius: BorderRadius.circular(10),
              side: BorderSide(color: theme.dividerColor),
            ),
            child: Padding(
              padding: const EdgeInsets.all(20),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  const CircularProgressIndicator(),
                  const SizedBox(height: 12),
                  Text('Loading details...', style: theme.textTheme.bodyMedium),
                ],
              ),
            ),
          );
        }

        // Extract raw data fields
        final history = dispute.details['history'] as List<dynamic>? ?? const [];
        final webhookEvent = history.firstWhere(
          (item) => item is Map && item['event'] == 'webhook_received',
          orElse: () => <String, dynamic>{},
        ) as Map<String, dynamic>;
        final webhookData = webhookEvent['data'] as Map<String, dynamic>? ?? const {};
        final payload = webhookData['payload'] as Map<String, dynamic>? ?? const {};
        final payment = payload['payment']?['entity'] as Map<String, dynamic>? ?? const {};
        final disputeData = payload['dispute']?['entity'] as Map<String, dynamic>? ?? const {};

        final customerEmail = dispute.customerName ?? payment['email']?.toString();
        final amountStr = _money(dispute.amount, dispute.currency);
        final paymentId = dispute.details['payment_id']?.toString() ?? payment['id']?.toString() ?? 'N/A';
        final orderId = dispute.details['order_id']?.toString() ?? payment['order_id']?.toString() ?? 'N/A';
        final reasonCode = dispute.reason ?? disputeData['reason_code']?.toString() ?? 'N/A';
        final phase = dispute.details['phase']?.toString() ?? disputeData['phase']?.toString() ?? 'N/A';
        final isRunning = dispute.status == DisputeStatus.processing;

        // Draft preview
        final latestState = history.reversed.firstWhere(
          (item) => item is Map && item['event'] == 'node_update' && item['state_update'] != null,
          orElse: () => null,
        ) as Map<String, dynamic>?;
        final stateUpdate = latestState?['state_update'] as Map<String, dynamic>?;
        final draftLetter = stateUpdate?['draft_response_letter']?.toString() ??
            stateUpdate?['verified_explanation_letter']?.toString() ??
            stateUpdate?['draft_explanation_letter']?.toString();

        return Dialog(
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(10),
            side: BorderSide(color: theme.dividerColor),
          ),
          elevation: 0,
          backgroundColor: theme.colorScheme.surface,
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 860, maxHeight: 760),
            child: Padding(
              padding: const EdgeInsets.all(28),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  // ── Header ──
                  Row(
                    children: [
                      Icon(Icons.assignment_outlined, color: theme.colorScheme.primary, size: 24),
                      const SizedBox(width: 12),
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(
                              'Dispute Details',
                              style: theme.textTheme.titleMedium?.copyWith(
                                fontWeight: FontWeight.w700,
                              ),
                            ),
                            const SizedBox(height: 2),
                            Text(
                              'ID: ${dispute.id}',
                              style: theme.textTheme.bodySmall,
                            ),
                          ],
                        ),
                      ),
                      _StatusPill(dispute: dispute),
                      const SizedBox(width: 8),
                      IconButton(
                        onPressed: () => Navigator.of(context).pop(),
                        icon: const Icon(Icons.close, size: 20),
                        tooltip: 'Close',
                      ),
                    ],
                  ),

                  Divider(height: 28, color: theme.dividerColor),

                  // ── Body Columns ──
                  Expanded(
                    child: Row(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        // Left Column: Metadata + Actions
                        Expanded(
                          flex: 4,
                          child: SingleChildScrollView(
                            child: Padding(
                              padding: const EdgeInsets.only(right: 18),
                              child: Column(
                                crossAxisAlignment: CrossAxisAlignment.stretch,
                                children: [
                                  // Context Details Card
                                  Container(
                                    padding: const EdgeInsets.all(16),
                                    decoration: BoxDecoration(
                                      border: Border.all(color: theme.dividerColor),
                                      borderRadius: BorderRadius.circular(8),
                                      color: theme.colorScheme.surfaceContainerLowest,
                                    ),
                                    child: Column(
                                      crossAxisAlignment: CrossAxisAlignment.stretch,
                                      children: [
                                        _DetailRow(label: 'Customer Email', value: customerEmail ?? 'Unknown'),
                                        const Divider(height: 16),
                                        _DetailRow(label: 'Disputed Amount', value: amountStr),
                                        const Divider(height: 16),
                                        _DetailRow(label: 'Order ID', value: orderId),
                                        const Divider(height: 16),
                                        _DetailRow(label: 'Payment ID', value: paymentId),
                                        const Divider(height: 16),
                                        _DetailRow(label: 'Document ID', value: dispute.documentId ?? 'N/A'),
                                        const Divider(height: 16),
                                        _DetailRow(label: 'Storage Path', value: dispute.storagePath ?? 'N/A'),
                                        const Divider(height: 16),
                                        _DetailRow(label: 'Reason Code', value: reasonCode),
                                        const Divider(height: 16),
                                        _DetailRow(label: 'Workflow Phase', value: phase),
                                        const Divider(height: 16),
                                        _DetailRow(label: 'Last Updated', value: _dateTimeLabel(dispute.updatedAt)),
                                      ],
                                    ),
                                  ),

                                  const SizedBox(height: 16),

                                  // Evidence PDF Card (State-aware)
                                  Builder(
                                    builder: (context) {
                                      final hasStorage = dispute.storagePath != null && dispute.storagePath!.isNotEmpty;
                                      final jobStatus = (dispute.evidenceJobStatus ?? '').toLowerCase();
                                      final isFailed = jobStatus == 'failed';
                                      final isProcessing = jobStatus == 'queued' || jobStatus == 'processing' || (isRunning && !hasStorage);
                                      final isReady = hasStorage || jobStatus == 'completed';

                                      if (isReady && hasStorage) {
                                        // ── State 1: Ready ──
                                        return Container(
                                          padding: const EdgeInsets.all(16),
                                          decoration: BoxDecoration(
                                            border: Border.all(color: Colors.green.withValues(alpha: 0.3)),
                                            borderRadius: BorderRadius.circular(8),
                                            color: Colors.green.withValues(alpha: 0.04),
                                          ),
                                          child: Column(
                                            crossAxisAlignment: CrossAxisAlignment.stretch,
                                            children: [
                                              Row(
                                                children: [
                                                  const Icon(Icons.picture_as_pdf, size: 18, color: Colors.redAccent),
                                                  const SizedBox(width: 8),
                                                  Text(
                                                    'Evidence PDF Document',
                                                    style: theme.textTheme.titleSmall?.copyWith(fontWeight: FontWeight.w600),
                                                  ),
                                                  const Spacer(),
                                                  Container(
                                                    padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                                                    decoration: BoxDecoration(
                                                      color: Colors.green.withValues(alpha: 0.15),
                                                      borderRadius: BorderRadius.circular(4),
                                                    ),
                                                    child: Text(
                                                      'Ready',
                                                      style: theme.textTheme.bodySmall?.copyWith(
                                                        color: Colors.green,
                                                        fontWeight: FontWeight.w600,
                                                        fontSize: 11,
                                                      ),
                                                    ),
                                                  ),
                                                ],
                                              ),
                                              const SizedBox(height: 8),
                                              Text(
                                                'In-memory compiled PDF package stored on Supabase Storage CDN.',
                                                style: theme.textTheme.bodySmall,
                                              ),
                                              const SizedBox(height: 12),
                                              ElevatedButton.icon(
                                                onPressed: _fetchingPdf ? null : () => _viewEvidencePdf(dispute),
                                                icon: _fetchingPdf
                                                    ? const SizedBox(
                                                        width: 14,
                                                        height: 14,
                                                        child: CircularProgressIndicator(strokeWidth: 2),
                                                      )
                                                    : const Icon(Icons.visibility, size: 16),
                                                label: Text(_fetchingPdf ? 'Fetching Signed URL...' : 'View Evidence PDF (Supabase CDN)'),
                                              ),
                                            ],
                                          ),
                                        );
                                      } else if (isFailed) {
                                        // ── State 2: Failed ──
                                        final errorMsg = dispute.evidenceJobError ?? 'Generation or upload failed';
                                        return Container(
                                          padding: const EdgeInsets.all(16),
                                          decoration: BoxDecoration(
                                            border: Border.all(color: theme.colorScheme.error.withValues(alpha: 0.4)),
                                            borderRadius: BorderRadius.circular(8),
                                            color: theme.colorScheme.error.withValues(alpha: 0.05),
                                          ),
                                          child: Column(
                                            crossAxisAlignment: CrossAxisAlignment.stretch,
                                            children: [
                                              Row(
                                                children: [
                                                  Icon(Icons.error_outline, size: 18, color: theme.colorScheme.error),
                                                  const SizedBox(width: 8),
                                                  Text(
                                                    'Evidence Generation Failed',
                                                    style: theme.textTheme.titleSmall?.copyWith(
                                                      fontWeight: FontWeight.w600,
                                                      color: theme.colorScheme.error,
                                                    ),
                                                  ),
                                                  const Spacer(),
                                                  Container(
                                                    padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                                                    decoration: BoxDecoration(
                                                      color: theme.colorScheme.error.withValues(alpha: 0.15),
                                                      borderRadius: BorderRadius.circular(4),
                                                    ),
                                                    child: Text(
                                                      'Failed',
                                                      style: theme.textTheme.bodySmall?.copyWith(
                                                        color: theme.colorScheme.error,
                                                        fontWeight: FontWeight.w600,
                                                        fontSize: 11,
                                                      ),
                                                    ),
                                                  ),
                                                ],
                                              ),
                                              const SizedBox(height: 8),
                                              Text(
                                                errorMsg,
                                                style: theme.textTheme.bodySmall?.copyWith(
                                                  color: theme.colorScheme.error,
                                                ),
                                              ),
                                              const SizedBox(height: 12),
                                              OutlinedButton.icon(
                                                onPressed: () => widget.viewModel.retryEvidenceJob(dispute.id),
                                                icon: const Icon(Icons.refresh, size: 16),
                                                label: const Text('Retry Evidence Generation'),
                                                style: OutlinedButton.styleFrom(
                                                  foregroundColor: theme.colorScheme.error,
                                                  side: BorderSide(color: theme.colorScheme.error.withValues(alpha: 0.5)),
                                                ),
                                              ),
                                            ],
                                          ),
                                        );
                                      } else if (isProcessing) {
                                        // ── State 3: In-Progress / Queued ──
                                        final isPickingUp = jobStatus == 'processing';
                                        return Container(
                                          padding: const EdgeInsets.all(16),
                                          decoration: BoxDecoration(
                                            border: Border.all(color: Colors.amber.withValues(alpha: 0.4)),
                                            borderRadius: BorderRadius.circular(8),
                                            color: Colors.amber.withValues(alpha: 0.05),
                                          ),
                                          child: Column(
                                            crossAxisAlignment: CrossAxisAlignment.stretch,
                                            children: [
                                              Row(
                                                children: [
                                                  const SizedBox(
                                                    width: 14,
                                                    height: 14,
                                                    child: CircularProgressIndicator(strokeWidth: 2, color: Colors.amber),
                                                  ),
                                                  const SizedBox(width: 10),
                                                  Text(
                                                    isPickingUp ? 'Generating Evidence PDF...' : 'Evidence Job Queued',
                                                    style: theme.textTheme.titleSmall?.copyWith(fontWeight: FontWeight.w600),
                                                  ),
                                                  const Spacer(),
                                                  Container(
                                                    padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                                                    decoration: BoxDecoration(
                                                      color: Colors.amber.withValues(alpha: 0.15),
                                                      borderRadius: BorderRadius.circular(4),
                                                    ),
                                                    child: Text(
                                                      isPickingUp ? 'Processing' : 'Queued',
                                                      style: theme.textTheme.bodySmall?.copyWith(
                                                        color: Colors.amber.shade800,
                                                        fontWeight: FontWeight.w600,
                                                        fontSize: 11,
                                                      ),
                                                    ),
                                                  ),
                                                ],
                                              ),
                                              const SizedBox(height: 8),
                                              Text(
                                                isPickingUp
                                                    ? 'Worker is generating in-memory PDF and uploading to Supabase Storage...'
                                                    : 'Dispute is queued in the worker pool. PDF will generate shortly.',
                                                style: theme.textTheme.bodySmall,
                                              ),
                                            ],
                                          ),
                                        );
                                      } else {
                                        // ── State 4: Not Yet Generated ──
                                        return Container(
                                          padding: const EdgeInsets.all(16),
                                          decoration: BoxDecoration(
                                            border: Border.all(color: theme.dividerColor),
                                            borderRadius: BorderRadius.circular(8),
                                            color: theme.colorScheme.surfaceContainerLowest,
                                          ),
                                          child: Column(
                                            crossAxisAlignment: CrossAxisAlignment.stretch,
                                            children: [
                                              Row(
                                                children: [
                                                  Icon(Icons.article_outlined, size: 18, color: theme.textTheme.bodySmall?.color),
                                                  const SizedBox(width: 8),
                                                  Text(
                                                    'Evidence PDF Document',
                                                    style: theme.textTheme.titleSmall?.copyWith(fontWeight: FontWeight.w600),
                                                  ),
                                                  const Spacer(),
                                                  Container(
                                                    padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                                                    decoration: BoxDecoration(
                                                      color: theme.dividerColor.withValues(alpha: 0.1),
                                                      borderRadius: BorderRadius.circular(4),
                                                    ),
                                                    child: Text(
                                                      'Not Generated',
                                                      style: theme.textTheme.bodySmall?.copyWith(
                                                        fontWeight: FontWeight.w500,
                                                        fontSize: 11,
                                                      ),
                                                    ),
                                                  ),
                                                ],
                                              ),
                                              const SizedBox(height: 8),
                                              Text(
                                                'Evidence not yet generated. In-memory PDF package will be compiled automatically when the dispute is contested.',
                                                style: theme.textTheme.bodySmall,
                                              ),
                                            ],
                                          ),
                                        );
                                      }
                                    },
                                  ),

                                  const SizedBox(height: 16),

                                  // Live progress bar if currently running
                                  if (isRunning) ...[
                                    Container(
                                      padding: const EdgeInsets.all(16),
                                      decoration: BoxDecoration(
                                        border: Border.all(color: theme.dividerColor),
                                        borderRadius: BorderRadius.circular(8),
                                      ),
                                      child: _buildLiveWorkflowProgress(dispute, theme),
                                    ),
                                    const SizedBox(height: 16),
                                  ],

                                  // Draft Letter Preview
                                  if (draftLetter != null) ...[
                                    Container(
                                      padding: const EdgeInsets.all(16),
                                      constraints: const BoxConstraints(maxHeight: 180),
                                      decoration: BoxDecoration(
                                        border: Border.all(color: theme.dividerColor),
                                        borderRadius: BorderRadius.circular(8),
                                      ),
                                      child: Column(
                                        crossAxisAlignment: CrossAxisAlignment.stretch,
                                        children: [
                                          Text('Draft Response Letter', style: theme.textTheme.titleSmall),
                                          const SizedBox(height: 8),
                                          Expanded(
                                            child: SingleChildScrollView(
                                              child: Text(
                                                draftLetter,
                                                style: theme.textTheme.bodySmall?.copyWith(
                                                  fontFamily: 'monospace',
                                                  height: 1.4,
                                                ),
                                              ),
                                            ),
                                          ),
                                        ],
                                      ),
                                    ),
                                    const SizedBox(height: 16),
                                  ],

                                  // Review Panel (if awaiting review)
                                  if (dispute.requiresHumanReview) ...[
                                    Container(
                                      padding: const EdgeInsets.all(16),
                                      decoration: BoxDecoration(
                                        border: Border.all(color: theme.colorScheme.error.withValues(alpha: 0.1)),
                                        borderRadius: BorderRadius.circular(8),
                                      ),
                                      child: Column(
                                        crossAxisAlignment: CrossAxisAlignment.stretch,
                                        children: [
                                          Row(
                                            children: [
                                              Icon(Icons.gavel, color: theme.colorScheme.error, size: 18),
                                              const SizedBox(width: 8),
                                              Text(
                                                'Review Actions Required',
                                                style: theme.textTheme.titleSmall?.copyWith(
                                                  color: theme.colorScheme.error,
                                                  fontWeight: FontWeight.w700,
                                                ),
                                              ),
                                            ],
                                          ),
                                          const SizedBox(height: 12),
                                          TextField(
                                            controller: _reasonController,
                                            maxLines: 2,
                                            decoration: const InputDecoration(
                                              labelText: 'Reason (optional)',
                                              hintText: 'Explain your decision...',
                                              border: OutlineInputBorder(),
                                            ),
                                          ),
                                          const SizedBox(height: 14),
                                          Row(
                                            children: [
                                              Expanded(
                                                child: OutlinedButton.icon(
                                                  onPressed: _submitting ? null : () => _submitReview('reject'),
                                                  icon: const Icon(Icons.close, size: 16),
                                                  label: const Text('Accept Loss'),
                                                  style: OutlinedButton.styleFrom(
                                                    foregroundColor: theme.colorScheme.error,
                                                    side: BorderSide(color: theme.colorScheme.error),
                                                  ),
                                                ),
                                              ),
                                              const SizedBox(width: 10),
                                              Expanded(
                                                child: FilledButton.icon(
                                                  onPressed: _submitting ? null : () => _submitReview('accept'),
                                                  icon: _submitting
                                                      ? const SizedBox(
                                                          width: 14,
                                                          height: 14,
                                                          child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white),
                                                        )
                                                      : const Icon(Icons.check, size: 16),
                                                  label: const Text('Submit Evidence'),
                                                ),
                                              ),
                                            ],
                                          ),
                                        ],
                                      ),
                                    ),
                                  ],
                                ],
                              ),
                            ),
                          ),
                        ),

                        VerticalDivider(width: 1, color: theme.dividerColor),

                        // Right Column: Audit Log / History Stream
                        Expanded(
                          flex: 3,
                          child: Padding(
                            padding: const EdgeInsets.only(left: 18),
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.stretch,
                              children: [
                                Row(
                                  children: [
                                    Icon(Icons.history, color: theme.textTheme.bodySmall?.color, size: 18),
                                    const SizedBox(width: 8),
                                    Text('Audit & Operations Log', style: theme.textTheme.titleSmall),
                                  ],
                                ),
                                const SizedBox(height: 14),
                                Expanded(
                                  child: history.isEmpty
                                      ? const Center(child: Text('No log history found.'))
                                      : ListView.builder(
                                          itemCount: history.length,
                                          itemBuilder: (context, idx) {
                                            final item = history[history.length - 1 - idx] as Map<String, dynamic>;
                                            return _HistoryEventItem(event: item);
                                          },
                                        ),
                                ),
                              ],
                            ),
                          ),
                        ),
                      ],
                    ),
                  ),
                ],
              ),
            ),
          ),
        );
      },
    );
  }

  Widget _buildLiveWorkflowProgress(Dispute dispute, ThemeData theme) {
    final steps = ['ingestion', 'retrieve_evidence', 'triage_and_score', 'draft_response'];
    final labels = ['Ingestion', 'Evidence', 'Triage', 'Drafting'];
    
    final current = dispute.currentNode ?? 'ingestion';
    int currentIndex = steps.indexOf(current);
    if (currentIndex == -1) currentIndex = 0;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            const SizedBox(
              width: 14,
              height: 14,
              child: CircularProgressIndicator(strokeWidth: 2),
            ),
            const SizedBox(width: 8),
            Text(
              'Risk Agent Running: ${dispute.workflowLabel}',
              style: theme.textTheme.labelMedium?.copyWith(
                color: theme.colorScheme.primary,
                fontWeight: FontWeight.w700,
              ),
            ),
          ],
        ),
        const SizedBox(height: 14),
        Row(
          children: List.generate(steps.length, (index) {
            final isCompleted = index < currentIndex;
            final isCurrent = index == currentIndex;
            
            Color color = theme.dividerColor;
            if (isCompleted) {
              color = Colors.green;
            } else if (isCurrent) {
              color = theme.colorScheme.primary;
            }

            return Expanded(
              child: Container(
                margin: const EdgeInsets.only(right: 6),
                height: 4,
                decoration: BoxDecoration(
                  color: color,
                  borderRadius: BorderRadius.circular(2),
                ),
              ),
            );
          }),
        ),
        const SizedBox(height: 8),
        Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: List.generate(labels.length, (index) {
            final isCurrent = index == currentIndex;
            return Text(
              labels[index],
              style: theme.textTheme.bodySmall?.copyWith(
                fontSize: 10,
                fontWeight: isCurrent ? FontWeight.w700 : null,
                color: isCurrent ? theme.colorScheme.primary : null,
              ),
            );
          }),
        ),
      ],
    );
  }
}

class _DetailRow extends StatelessWidget {
  const _DetailRow({required this.label, required this.value});

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Row(
      mainAxisAlignment: MainAxisAlignment.spaceBetween,
      children: [
        Text(label, style: theme.textTheme.bodySmall),
        Text(
          value,
          style: theme.textTheme.labelMedium?.copyWith(
            fontWeight: FontWeight.w600,
          ),
        ),
      ],
    );
  }
}

class _HistoryEventItem extends StatelessWidget {
  const _HistoryEventItem({required this.event});

  final Map<String, dynamic> event;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final timestamp = event['timestamp']?.toString() ?? '';
    final eventName = event['event']?.toString() ?? 'unknown';
    
    // Parse time
    String timeStr = '';
    if (timestamp.isNotEmpty) {
      final dt = DateTime.tryParse(timestamp);
      if (dt != null) {
        timeStr = '${dt.hour.toString().padLeft(2, '0')}:${dt.minute.toString().padLeft(2, '0')}:${dt.second.toString().padLeft(2, '0')}';
      }
    }

    // Determine title & detail
    String title = eventName.toDisplayLabel();
    String detail = '';
    IconData icon = Icons.info_outline;
    Color iconColor = theme.textTheme.bodySmall?.color ?? Colors.grey;

    switch (eventName) {
      case 'webhook_received':
        title = 'Ingestion';
        detail = 'Razorpay webhook received & verified.';
        icon = Icons.cloud_download_outlined;
        iconColor = Colors.blue;
        break;
      case 'job_queued':
        final qId = event['job_id']?.toString() ?? '';
        title = 'Evidence Job Queued';
        detail = 'Queued in worker pool for in-memory PDF generation.${qId.isNotEmpty ? " Job #$qId" : ""}';
        icon = Icons.schedule;
        iconColor = Colors.amber;
        break;
      case 'job_picked_up':
        final pId = event['job_id']?.toString() ?? '';
        title = 'Worker Picked Up Job';
        detail = 'Worker began in-memory PDF compilation.${pId.isNotEmpty ? " Job #$pId" : ""}';
        icon = Icons.bolt;
        iconColor = Colors.cyan;
        break;
      case 'evidence_composed':
        title = 'Evidence Composed';
        detail = 'PDF evidence package generated from database records.';
        icon = Icons.article_outlined;
        iconColor = Colors.orange;
        break;
      case 'evidence_uploaded':
        final docId = event['document_id']?.toString() ?? 'unknown';
        title = 'Evidence Uploaded';
        detail = 'Uploaded to Razorpay. Doc ID: $docId';
        icon = Icons.cloud_upload_outlined;
        iconColor = Colors.blue;
        break;
      case 'evidence_upload_failed':
        final reason = event['reason']?.toString() ?? 'Unknown reason';
        title = 'Evidence Upload Failed';
        detail = 'Error: $reason';
        icon = Icons.error_outline;
        iconColor = Colors.red;
        break;
      case 'evidence_submitted':
        final amt = event['contest_amount'] != null ? ' (Amount: ₹${(event['contest_amount'] as num) / 100})' : '';
        title = 'Evidence Submitted';
        detail = 'Contest submitted to Razorpay$amt.';
        icon = Icons.send_outlined;
        iconColor = Colors.indigo;
        break;
      case 'node_update':
        final node = event['node']?.toString() ?? 'unknown';
        title = 'Node Completed: ${node.toDisplayLabel()}';
        detail = 'Agent finished executing state logic.';
        icon = Icons.dns_outlined;
        iconColor = Colors.teal;
        break;
      case 'human_review_required':
        title = 'HITL Triggered';
        detail = 'Risk score/value flagged for operator decision.';
        icon = Icons.gavel;
        iconColor = Colors.purple;
        break;
      case 'human_review_submitted':
        final action = event['action']?.toString() ?? '';
        final reason = event['reason']?.toString() ?? '';
        title = 'HIL Review Submitted';
        detail = 'Decision: ${action.toUpperCase()}${reason.isNotEmpty ? " (Reason: $reason)" : ""}';
        icon = Icons.assignment_turned_in_outlined;
        iconColor = action == 'accept' ? Colors.green : Colors.red;
        break;
      case 'execution_completed':
        final res = event['data']?['case_resolution']?.toString() ?? '';
        title = 'Graph Completed';
        detail = 'Outcome resolution: ${res.toDisplayLabel()}';
        icon = Icons.check_circle_outline;
        iconColor = Colors.green;
        break;
      case 'execution_completed_after_review':
        final res = event['data']?['case_resolution']?.toString() ?? '';
        title = 'Graph Completed after review';
        detail = 'Outcome resolution: ${res.toDisplayLabel()}';
        icon = Icons.check_circle_outline;
        iconColor = Colors.green;
        break;
      case 'execution_error':
      case 'resume_error':
        title = 'Workflow Error';
        detail = event['error']?.toString() ?? 'Unknown error';
        icon = Icons.error_outline;
        iconColor = Colors.red;
        break;
    }

    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 8),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Container(
            padding: const EdgeInsets.all(6),
            decoration: BoxDecoration(
              color: iconColor.withValues(alpha: 0.10),
              borderRadius: BorderRadius.circular(6),
            ),
            child: Icon(icon, size: 16, color: iconColor),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Expanded(
                      child: Text(
                        title,
                        style: theme.textTheme.labelMedium?.copyWith(
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                    ),
                    if (timeStr.isNotEmpty)
                      Text(
                        timeStr,
                        style: theme.textTheme.bodySmall?.copyWith(fontSize: 10),
                      ),
                  ],
                ),
                const SizedBox(height: 2),
                Text(
                  detail,
                  style: theme.textTheme.bodySmall?.copyWith(fontSize: 11),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _Sidebar extends StatelessWidget {
  const _Sidebar({
    required this.selected,
    required this.themeProvider,
    required this.onSelected,
  });

  final DashboardSection selected;
  final ThemeProvider themeProvider;
  final ValueChanged<DashboardSection> onSelected;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final muted = theme.textTheme.bodySmall?.color;
    return Container(
      width: 248,
      color: theme.colorScheme.surfaceContainerLowest,
      child: SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              const _BrandLockup(),
              const SizedBox(height: 28),
              _NavLink(
                icon: Icons.space_dashboard_outlined,
                label: 'Overview',
                selected: selected == DashboardSection.overview,
                onPressed: () => onSelected(DashboardSection.overview),
              ),
              _NavLink(
                icon: Icons.receipt_long_outlined,
                label: 'Disputes',
                selected: selected == DashboardSection.disputes,
                onPressed: () => onSelected(DashboardSection.disputes),
              ),
              _NavLink(
                icon: Icons.query_stats,
                label: 'Analytics',
                selected: selected == DashboardSection.analytics,
                onPressed: () => onSelected(DashboardSection.analytics),
              ),
              _NavLink(
                icon: Icons.tune,
                label: 'Settings',
                selected: selected == DashboardSection.settings,
                onPressed: () => onSelected(DashboardSection.settings),
              ),
              const Spacer(),
              Container(
                decoration: BoxDecoration(
                  border: Border.all(color: theme.dividerColor),
                  borderRadius: BorderRadius.circular(8),
                  color: theme.colorScheme.surface,
                ),
                padding: const EdgeInsets.all(12),
                child: Row(
                  children: [
                    Container(
                      width: 34,
                      height: 34,
                      alignment: Alignment.center,
                      decoration: BoxDecoration(
                        color:
                            theme.colorScheme.primary.withValues(alpha: 0.12),
                        borderRadius: BorderRadius.circular(8),
                      ),
                      child: Text(
                        'SM',
                        style: TextStyle(
                          color: theme.colorScheme.primary,
                          fontWeight: FontWeight.w800,
                          fontSize: 12,
                        ),
                      ),
                    ),
                    const SizedBox(width: 10),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          Text(
                            'Risk Ops',
                            overflow: TextOverflow.ellipsis,
                            style: theme.textTheme.titleMedium?.copyWith(
                              fontSize: 13,
                            ),
                          ),
                          Text(
                            'ops@safemerchant.ai',
                            overflow: TextOverflow.ellipsis,
                            style: theme.textTheme.bodySmall?.copyWith(
                              color: muted,
                            ),
                          ),
                        ],
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _BrandLockup extends StatelessWidget {
  const _BrandLockup();

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Row(
      children: [
        Container(
          width: 36,
          height: 36,
          decoration: BoxDecoration(
            color: theme.colorScheme.primary,
            borderRadius: BorderRadius.circular(8),
          ),
          child: Icon(
            Icons.verified_user_outlined,
            color: theme.colorScheme.onPrimary,
            size: 20,
          ),
        ),
        const SizedBox(width: 10),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text('SafeMerchant', style: theme.textTheme.titleMedium),
              Text(
                'AI Risk Manager',
                overflow: TextOverflow.ellipsis,
                style: theme.textTheme.bodySmall,
              ),
            ],
          ),
        ),
      ],
    );
  }
}

class _NavLink extends StatelessWidget {
  const _NavLink({
    required this.icon,
    required this.label,
    required this.selected,
    required this.onPressed,
  });

  final IconData icon;
  final String label;
  final bool selected;
  final VoidCallback onPressed;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final foreground = selected
        ? theme.colorScheme.onSurface
        : theme.textTheme.bodySmall?.color;
    return Padding(
      padding: const EdgeInsets.only(bottom: 4),
      child: TextButton.icon(
        onPressed: onPressed,
        icon: Icon(icon, size: 18),
        label: Align(
          alignment: Alignment.centerLeft,
          child: Text(label, overflow: TextOverflow.ellipsis),
        ),
        style: TextButton.styleFrom(
          foregroundColor: foreground,
          backgroundColor: selected
              ? theme.colorScheme.primary.withValues(alpha: 0.10)
              : null,
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 12),
          alignment: Alignment.centerLeft,
        ),
      ),
    );
  }
}

class _TopBar extends StatelessWidget {
  const _TopBar({
    required this.section,
    required this.viewModel,
    required this.themeProvider,
  });

  final DashboardSection section;
  final DashboardController viewModel;
  final ThemeProvider themeProvider;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return SafeArea(
      bottom: false,
      child: Container(
        height: 64,
        color: theme.colorScheme.surface,
        padding: const EdgeInsets.symmetric(horizontal: 22),
        child: Row(
          children: [
            Expanded(
              child: Text(
                _sectionTitle(section),
                overflow: TextOverflow.ellipsis,
                style: theme.textTheme.titleLarge,
              ),
            ),
            Flexible(
              flex: 2,
              child: ConstrainedBox(
                constraints: const BoxConstraints(maxWidth: 420),
                child: TextField(
                  decoration: InputDecoration(
                    prefixIcon: const Icon(Icons.search, size: 18),
                    hintText: 'Search disputes, payments, customers',
                    contentPadding: const EdgeInsets.symmetric(vertical: 10),
                    suffixIcon: IconButton(
                      tooltip: 'Reconnect',
                      onPressed: viewModel.isBusy ? null : viewModel.reconnect,
                      icon: const Icon(Icons.sync, size: 18),
                    ),
                  ),
                ),
              ),
            ),
            const SizedBox(width: 12),
            IconButton(
              tooltip: themeProvider.isDarkMode
                  ? 'Use light theme'
                  : 'Use dark theme',
              onPressed: themeProvider.toggleTheme,
              icon: Icon(
                themeProvider.isDarkMode
                    ? Icons.light_mode_outlined
                    : Icons.dark_mode_outlined,
              ),
            ),
            const SizedBox(width: 4),
            Stack(
              clipBehavior: Clip.none,
              children: [
                IconButton(
                  tooltip: 'Notifications',
                  onPressed: () {},
                  icon: const Icon(Icons.notifications_none_outlined),
                ),
                if (viewModel.actionRequiredCount > 0)
                  Positioned(
                    right: 8,
                    top: 8,
                    child: Container(
                      width: 8,
                      height: 8,
                      decoration: BoxDecoration(
                        color: theme.colorScheme.error,
                        shape: BoxShape.circle,
                      ),
                    ),
                  ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

class OverviewScreen extends StatelessWidget {
  const OverviewScreen({super.key, required this.viewModel});

  final DashboardController viewModel;

  @override
  Widget build(BuildContext context) {
    final totals = viewModel.metricsSummary?.totals;
    return _ScreenScrollView(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          _SectionHeader(
            title: 'Command Center',
            subtitle:
                'Live operational view of dispute automation and risk exposure.',
            trailing: _ConnectionLabel(status: viewModel.connectionStatus),
          ),
          const SizedBox(height: 20),
          LayoutBuilder(
            builder: (context, constraints) {
              final narrow = constraints.maxWidth < 760;
              final tiles = [
                _MetricPanel(
                  label: 'Total Disputes',
                  value: (totals?.totalDisputes ?? viewModel.disputes.length)
                      .toString(),
                  icon: Icons.receipt_long_outlined,
                ),
                _MetricPanel(
                  label: 'Action Required',
                  value:
                      (totals?.actionRequired ?? viewModel.actionRequiredCount)
                          .toString(),
                  icon: Icons.priority_high,
                ),
                _MetricPanel(
                  label: 'Win Rate',
                  value: totals?.winRate == null
                      ? 'N/A'
                      : '${(totals!.winRate! * 100).toStringAsFixed(1)}%',
                  icon: Icons.trending_up,
                ),
                _MetricPanel(
                  label: 'Amount At Risk',
                  value: _paise(totals?.amountAtRiskPaise ?? 0),
                  icon: Icons.account_balance_wallet_outlined,
                ),
              ];
              if (narrow) {
                return Column(
                  children: tiles
                      .map((tile) => Padding(
                            padding: const EdgeInsets.only(bottom: 12),
                            child: tile,
                          ))
                      .toList(),
                );
              }
              return Row(
                children: tiles
                    .map((tile) => Expanded(
                          child: Padding(
                            padding: const EdgeInsets.only(right: 12),
                            child: tile,
                          ),
                        ))
                    .toList(),
              );
            },
          ),
          const SizedBox(height: 24),
          _FlatPanel(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Text('Recent Events',
                    style: Theme.of(context).textTheme.titleMedium),
                const SizedBox(height: 12),
                if (viewModel.events.isEmpty)
                  const _EmptyState(label: 'Waiting for backend events.')
                else
                  ...viewModel.events.take(8).map(
                        (event) => _ActivityLine(
                          title: event.title,
                          detail: event.description,
                          timestamp: _timeLabel(event.receivedAt),
                        ),
                      ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class DisputesScreen extends StatelessWidget {
  const DisputesScreen({super.key, required this.viewModel});

  final DashboardController viewModel;

  @override
  Widget build(BuildContext context) {
    return _ScreenScrollView(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          const _SectionHeader(
            title: 'Disputes',
            subtitle:
                'Monitor lifecycle state, payment context, and review actions.',
          ),
          const SizedBox(height: 20),
          _FlatPanel(
            padding: EdgeInsets.zero,
            child: viewModel.disputes.isEmpty
                ? const SizedBox(
                    height: 260,
                    child: _EmptyState(
                        label: 'No disputes have been received yet.'),
                  )
                : SingleChildScrollView(
                    scrollDirection: Axis.horizontal,
                    child: DataTable(
                      headingRowHeight: 42,
                      dataRowMinHeight: 54,
                      dataRowMaxHeight: 62,
                      columnSpacing: 34,
                      horizontalMargin: 18,
                      showCheckboxColumn: false,
                      columns: const [
                        DataColumn(label: Text('Dispute')),
                        DataColumn(label: Text('Customer')),
                        DataColumn(label: Text('Amount')),
                        DataColumn(label: Text('Status')),
                        DataColumn(label: Text('Workflow')),
                        DataColumn(label: Text('Updated')),
                      ],
                      rows: viewModel.disputes.map((dispute) {
                        return DataRow(
                          onSelectChanged: (_) {
                            viewModel.selectDispute(dispute.id);
                            showDialog<void>(
                              context: context,
                              builder: (_) => _DisputeDetailsDialog(
                                viewModel: viewModel,
                                disputeId: dispute.id,
                              ),
                            );
                          },
                          cells: [
                            DataCell(Text(dispute.id)),
                            DataCell(Text(dispute.customerName ?? 'Unknown')),
                            DataCell(
                                Text(_money(dispute.amount, dispute.currency))),
                            DataCell(_StatusPill(dispute: dispute)),
                            DataCell(Text(dispute.workflowLabel)),
                            DataCell(Text(_dateTimeLabel(dispute.updatedAt))),
                          ],
                        );
                      }).toList(),
                    ),
                  ),
          ),
        ],
      ),
    );
  }
}

class AnalyticsScreen extends StatelessWidget {
  const AnalyticsScreen({super.key, required this.viewModel});

  final DashboardController viewModel;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final totals = viewModel.metricsSummary?.totals;
    final groups = viewModel.breakdowns.values.toList();
    return _ScreenScrollView(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          _SectionHeader(
            title: 'Analytics',
            subtitle:
                'Pre-aggregated metrics, current breakdowns, and repeat patterns.',
            trailing: TextButton.icon(
              onPressed: viewModel.refreshMetrics,
              icon: const Icon(Icons.refresh, size: 18),
              label: const Text('Refresh'),
            ),
          ),

          // ── Section A: KPI Summary Row ──
          const SizedBox(height: 20),
          LayoutBuilder(
            builder: (context, constraints) {
              final narrow = constraints.maxWidth < 760;
              final kpis = [
                _MetricPanel(
                  label: 'Total Disputes',
                  value: '${totals?.totalDisputes ?? 0}',
                  icon: Icons.receipt_long_outlined,
                ),
                _MetricPanel(
                  label: 'Won',
                  value: '${totals?.won ?? 0}',
                  icon: Icons.check_circle_outline,
                ),
                _MetricPanel(
                  label: 'Lost',
                  value: '${totals?.lost ?? 0}',
                  icon: Icons.cancel_outlined,
                ),
                _MetricPanel(
                  label: 'Win Rate',
                  value: totals?.winRate == null
                      ? 'N/A'
                      : '${(totals!.winRate! * 100).toStringAsFixed(1)}%',
                  icon: Icons.trending_up,
                ),
                _MetricPanel(
                  label: 'Amount At Risk',
                  value: _paise(totals?.amountAtRiskPaise ?? 0),
                  icon: Icons.account_balance_wallet_outlined,
                ),
                _MetricPanel(
                  label: 'SLA Breached',
                  value: '${totals?.slaBreached ?? 0}',
                  icon: Icons.timer_off_outlined,
                ),
              ];
              if (narrow) {
                return Wrap(
                  spacing: 12,
                  runSpacing: 12,
                  children: kpis
                      .map((k) => SizedBox(width: double.infinity, child: k))
                      .toList(),
                );
              }
              return Wrap(
                spacing: 12,
                runSpacing: 12,
                children: kpis
                    .map((k) => SizedBox(
                          width: (constraints.maxWidth - 12 * 2) / 3,
                          child: k,
                        ))
                    .toList(),
              );
            },
          ),

          // ── Amount Won / Lost Summary ──
          const SizedBox(height: 16),
          LayoutBuilder(
            builder: (context, constraints) {
              final narrow = constraints.maxWidth < 760;
              final amountCards = [
                _MetricPanel(
                  label: 'Amount Won',
                  value: _paise(totals?.amountWonPaise ?? 0),
                  icon: Icons.arrow_upward,
                ),
                _MetricPanel(
                  label: 'Amount Lost',
                  value: _paise(totals?.amountLostPaise ?? 0),
                  icon: Icons.arrow_downward,
                ),
                _MetricPanel(
                  label: 'Action Required',
                  value: '${totals?.actionRequired ?? 0}',
                  icon: Icons.priority_high,
                ),
              ];
              if (narrow) {
                return Column(
                  children: amountCards
                      .map((c) =>
                          Padding(padding: const EdgeInsets.only(bottom: 12), child: c))
                      .toList(),
                );
              }
              return Row(
                children: amountCards
                    .map((c) => Expanded(
                          child: Padding(
                            padding: const EdgeInsets.only(right: 12),
                            child: c,
                          ),
                        ))
                    .toList(),
              );
            },
          ),

          // ── Section B: Daily Trend Table ──
          const SizedBox(height: 24),
          _FlatPanel(
            padding: EdgeInsets.zero,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Padding(
                  padding: const EdgeInsets.fromLTRB(18, 18, 18, 0),
                  child: Text('Daily Trend',
                      style: theme.textTheme.titleMedium),
                ),
                const SizedBox(height: 8),
                if (viewModel.metricsSummary == null ||
                    viewModel.metricsSummary!.daily.isEmpty)
                  const SizedBox(
                    height: 140,
                    child: _EmptyState(label: 'No daily metrics loaded.'),
                  )
                else
                  SingleChildScrollView(
                    scrollDirection: Axis.horizontal,
                    child: DataTable(
                      headingRowHeight: 40,
                      dataRowMinHeight: 44,
                      dataRowMaxHeight: 50,
                      columnSpacing: 28,
                      horizontalMargin: 18,
                      columns: const [
                        DataColumn(label: Text('Date')),
                        DataColumn(label: Text('Total'), numeric: true),
                        DataColumn(label: Text('Won'), numeric: true),
                        DataColumn(label: Text('Lost'), numeric: true),
                        DataColumn(label: Text('Action Req.'), numeric: true),
                        DataColumn(label: Text('At Risk'), numeric: true),
                        DataColumn(label: Text('Won (₹)'), numeric: true),
                        DataColumn(label: Text('Lost (₹)'), numeric: true),
                      ],
                      rows: viewModel.metricsSummary!.daily
                          .reversed
                          .map((row) => DataRow(
                                cells: [
                                  DataCell(Text(_dateLabel(row.date))),
                                  DataCell(Text('${row.totalDisputes}')),
                                  DataCell(Text('${row.won}')),
                                  DataCell(Text('${row.lost}')),
                                  DataCell(Text('${row.actionRequired}')),
                                  DataCell(Text(_paise(row.amountAtRiskPaise))),
                                  DataCell(Text(_paise(row.amountWonPaise))),
                                  DataCell(Text(_paise(row.amountLostPaise))),
                                ],
                              ))
                          .toList(),
                    ),
                  ),
              ],
            ),
          ),

          // ── Section C: Breakdowns + Repeat Patterns ──
          const SizedBox(height: 24),
          LayoutBuilder(
            builder: (context, constraints) {
              final narrow = constraints.maxWidth < 900;

              final breakdownPanels = groups.map((group) {
                final maxCount = group.items.fold<int>(
                  0,
                  (prev, item) => item.count > prev ? item.count : prev,
                );
                return _FlatPanel(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      Text(
                        'By ${group.by.toDisplayLabel()}',
                        style: theme.textTheme.titleMedium,
                      ),
                      const SizedBox(height: 14),
                      if (group.items.isEmpty)
                        const _EmptyState(label: 'No data.')
                      else
                        ...group.items.take(8).map((item) {
                          final ratio =
                              maxCount > 0 ? item.count / maxCount : 0.0;
                          return Padding(
                            padding: const EdgeInsets.only(bottom: 10),
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Row(
                                  children: [
                                    Expanded(
                                      child: Text(
                                        item.value.toDisplayLabel(),
                                        style: theme.textTheme.bodySmall,
                                        overflow: TextOverflow.ellipsis,
                                      ),
                                    ),
                                    const SizedBox(width: 8),
                                    Text(
                                      '${item.count}',
                                      style:
                                          theme.textTheme.labelMedium?.copyWith(
                                        fontWeight: FontWeight.w700,
                                      ),
                                    ),
                                    const SizedBox(width: 8),
                                    Text(
                                      _paise(item.amountPaise),
                                      style: theme.textTheme.bodySmall,
                                    ),
                                  ],
                                ),
                                const SizedBox(height: 5),
                                ClipRRect(
                                  borderRadius: BorderRadius.circular(3),
                                  child: SizedBox(
                                    height: 8,
                                    child: FractionallySizedBox(
                                      alignment: Alignment.centerLeft,
                                      widthFactor: ratio.clamp(0.04, 1.0),
                                      child: Container(
                                        decoration: BoxDecoration(
                                          color: theme.colorScheme.primary
                                              .withValues(alpha: 0.55),
                                          borderRadius:
                                              BorderRadius.circular(3),
                                        ),
                                      ),
                                    ),
                                  ),
                                ),
                              ],
                            ),
                          );
                        }),
                      if (group.refreshedAt != null) ...[
                        const SizedBox(height: 6),
                        Text(
                          'Refreshed ${_dateTimeLabel(group.refreshedAt!)}',
                          style: theme.textTheme.bodySmall?.copyWith(
                            fontSize: 10,
                          ),
                        ),
                      ],
                    ],
                  ),
                );
              }).toList();

              final repeatPanel = _FlatPanel(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    Text('Repeat Patterns',
                        style: theme.textTheme.titleMedium),
                    const SizedBox(height: 14),
                    if (viewModel.repeatPatterns.isEmpty)
                      const _EmptyState(label: 'No repeat customer patterns.')
                    else
                      SingleChildScrollView(
                        scrollDirection: Axis.horizontal,
                        child: DataTable(
                          headingRowHeight: 38,
                          dataRowMinHeight: 42,
                          dataRowMaxHeight: 50,
                          columnSpacing: 24,
                          horizontalMargin: 0,
                          columns: const [
                            DataColumn(label: Text('Customer')),
                            DataColumn(
                                label: Text('Disputes'), numeric: true),
                            DataColumn(
                                label: Text('Total Amount'), numeric: true),
                            DataColumn(label: Text('Dispute IDs')),
                          ],
                          rows: viewModel.repeatPatterns
                              .map((p) => DataRow(cells: [
                                    DataCell(Text(p.customerEmail,
                                        overflow: TextOverflow.ellipsis)),
                                    DataCell(Text('${p.disputeCount}')),
                                    DataCell(
                                        Text(_paise(p.totalAmountPaise))),
                                    DataCell(
                                      ConstrainedBox(
                                        constraints: const BoxConstraints(
                                            maxWidth: 280),
                                        child: Text(
                                          p.disputeIds.join(', '),
                                          overflow: TextOverflow.ellipsis,
                                          maxLines: 2,
                                        ),
                                      ),
                                    ),
                                  ]))
                              .toList(),
                        ),
                      ),
                  ],
                ),
              );

              final allPanels = [...breakdownPanels, repeatPanel];

              if (narrow || groups.isEmpty) {
                return Column(
                  children: allPanels
                      .map((p) => Padding(
                            padding: const EdgeInsets.only(bottom: 14),
                            child: p,
                          ))
                      .toList(),
                );
              }
              return Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: allPanels
                    .map((p) => Expanded(
                          child: Padding(
                            padding: const EdgeInsets.only(right: 14),
                            child: p,
                          ),
                        ))
                    .toList(),
              );
            },
          ),
        ],
      ),
    );
  }
}

class _ScreenScrollView extends StatelessWidget {
  const _ScreenScrollView({required this.child});

  final Widget child;

  @override
  Widget build(BuildContext context) {
    return CustomScrollView(
      slivers: [
        SliverPadding(
          padding: const EdgeInsets.all(28),
          sliver: SliverToBoxAdapter(child: child),
        ),
      ],
    );
  }
}

class _SectionHeader extends StatelessWidget {
  const _SectionHeader({
    required this.title,
    required this.subtitle,
    this.trailing,
  });

  final String title;
  final String subtitle;
  final Widget? trailing;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(title, style: theme.textTheme.headlineSmall),
              const SizedBox(height: 6),
              Text(subtitle, style: theme.textTheme.bodySmall),
            ],
          ),
        ),
        if (trailing != null) ...[
          const SizedBox(width: 16),
          Flexible(child: trailing!),
        ],
      ],
    );
  }
}

class _FlatPanel extends StatelessWidget {
  const _FlatPanel({
    required this.child,
    this.padding = const EdgeInsets.all(18),
  });

  final Widget child;
  final EdgeInsetsGeometry padding;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Container(
      decoration: BoxDecoration(
        color: theme.colorScheme.surface,
        border: Border.all(color: theme.dividerColor),
        borderRadius: BorderRadius.circular(8),
      ),
      padding: padding,
      child: child,
    );
  }
}

class _MetricPanel extends StatelessWidget {
  const _MetricPanel({
    required this.label,
    required this.value,
    required this.icon,
  });

  final String label;
  final String value;
  final IconData icon;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return _FlatPanel(
      child: Row(
        children: [
          Icon(icon, color: theme.colorScheme.primary, size: 20),
          const SizedBox(width: 14),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(label, style: theme.textTheme.labelMedium),
                const SizedBox(height: 6),
                Text(
                  value,
                  overflow: TextOverflow.ellipsis,
                  style: theme.textTheme.titleLarge,
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

// _AnalyticsPanel and old _SummaryRows / _BreakdownRows removed —
// replaced by the redesigned inline widgets inside AnalyticsScreen above.

class _ActivityLine extends StatelessWidget {
  const _ActivityLine({
    required this.title,
    required this.detail,
    required this.timestamp,
  });

  final String title;
  final String detail;
  final String timestamp;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Container(
      padding: const EdgeInsets.symmetric(vertical: 11),
      decoration: BoxDecoration(
        border: Border(bottom: BorderSide(color: theme.dividerColor)),
      ),
      child: Row(
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  title,
                  overflow: TextOverflow.ellipsis,
                  style: theme.textTheme.titleMedium?.copyWith(fontSize: 13),
                ),
                const SizedBox(height: 3),
                Text(
                  detail,
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                  style: theme.textTheme.bodySmall,
                ),
              ],
            ),
          ),
          const SizedBox(width: 12),
          Text(timestamp, style: theme.textTheme.labelMedium),
        ],
      ),
    );
  }
}

class _ConnectionLabel extends StatelessWidget {
  const _ConnectionLabel({required this.status});

  final DashboardConnectionStatus status;

  @override
  Widget build(BuildContext context) {
    return _OutlineLabel(
      icon: status == DashboardConnectionStatus.connected
          ? Icons.sensors
          : Icons.link_off,
      label: _connectionText(status),
    );
  }
}

class _StatusPill extends StatelessWidget {
  const _StatusPill({required this.dispute});

  final Dispute dispute;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final isDark = theme.brightness == Brightness.dark;

    Color baseColor;
    IconData icon;

    if (dispute.requiresHumanReview) {
      baseColor = isDark ? Colors.purpleAccent : Colors.purple;
      icon = Icons.gavel;
    } else {
      switch (dispute.status) {
        case DisputeStatus.won:
        case DisputeStatus.resolved:
          baseColor = isDark ? Colors.greenAccent : Colors.green.shade700;
          icon = Icons.check_circle_outline;
          break;
        case DisputeStatus.lost:
          baseColor = isDark ? Colors.redAccent : Colors.red.shade700;
          icon = Icons.cancel_outlined;
          break;
        case DisputeStatus.acceptedLoss:
          baseColor = isDark ? Colors.orangeAccent : Colors.orange.shade800;
          icon = Icons.gavel;
          break;
        case DisputeStatus.evidenceSubmitted:
          baseColor = isDark ? Colors.tealAccent : Colors.teal.shade700;
          icon = Icons.send_outlined;
          break;
        case DisputeStatus.processing:
          baseColor = isDark ? Colors.blueAccent : Colors.blue.shade700;
          icon = Icons.sync;
          break;
        case DisputeStatus.awaitingReview:
        case DisputeStatus.humanReviewRequired:
          baseColor = isDark ? Colors.purpleAccent : Colors.purple;
          icon = Icons.gavel;
          break;
        case DisputeStatus.paused:
          baseColor = isDark ? Colors.amberAccent : Colors.amber.shade800;
          icon = Icons.pause_circle_outline;
          break;
        case DisputeStatus.error:
          baseColor = isDark ? Colors.redAccent : Colors.red.shade800;
          icon = Icons.error_outline;
          break;
        default:
          baseColor = theme.textTheme.bodySmall?.color ?? Colors.grey;
          icon = Icons.circle_outlined;
          break;
      }
    }

    return _OutlineLabel(
      icon: icon,
      label: dispute.displayStatus,
      backgroundColor: baseColor.withValues(alpha: 0.08),
      borderColor: baseColor.withValues(alpha: 0.25),
      textColor: baseColor,
    );
  }
}

class _OutlineLabel extends StatelessWidget {
  const _OutlineLabel({
    required this.icon,
    required this.label,
    this.backgroundColor,
    this.borderColor,
    this.textColor,
  });

  final IconData icon;
  final String label;
  final Color? backgroundColor;
  final Color? borderColor;
  final Color? textColor;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final effectiveTextColor = textColor ?? theme.textTheme.bodySmall?.color;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 7),
      decoration: BoxDecoration(
        color: backgroundColor,
        border: Border.all(color: borderColor ?? theme.dividerColor),
        borderRadius: BorderRadius.circular(999),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: 14, color: effectiveTextColor),
          const SizedBox(width: 6),
          Flexible(
            child: Text(
              label,
              overflow: TextOverflow.ellipsis,
              style: theme.textTheme.labelMedium?.copyWith(
                color: effectiveTextColor,
                fontWeight: FontWeight.w600,
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _EmptyState extends StatelessWidget {
  const _EmptyState({required this.label});

  final String label;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Text(label, style: Theme.of(context).textTheme.bodySmall),
    );
  }
}

String _sectionTitle(DashboardSection section) {
  return switch (section) {
    DashboardSection.overview => 'Overview',
    DashboardSection.disputes => 'Disputes',
    DashboardSection.analytics => 'Analytics',
    DashboardSection.settings => 'Settings',
  };
}

String _connectionText(DashboardConnectionStatus status) {
  return switch (status) {
    DashboardConnectionStatus.connected => 'Live',
    DashboardConnectionStatus.loading => 'Loading',
    DashboardConnectionStatus.connecting => 'Connecting',
    DashboardConnectionStatus.error => 'Attention',
    DashboardConnectionStatus.disconnected => 'Offline',
  };
}

String _money(double? amount, String? currency) {
  if (amount == null) {
    return 'Unknown';
  }
  return '${currency ?? 'INR'} ${amount.toStringAsFixed(2)}';
}

String _paise(int paise) {
  return _money(paise / 100, 'INR');
}

String _dateTimeLabel(DateTime dateTime) {
  return '${_dateLabel(dateTime)} '
      '${dateTime.hour.toString().padLeft(2, '0')}:'
      '${dateTime.minute.toString().padLeft(2, '0')}';
}

String _dateLabel(DateTime dateTime) {
  return '${dateTime.year}-'
      '${dateTime.month.toString().padLeft(2, '0')}-'
      '${dateTime.day.toString().padLeft(2, '0')}';
}

String _timeLabel(DateTime time) {
  return '${time.hour.toString().padLeft(2, '0')}:'
      '${time.minute.toString().padLeft(2, '0')}:'
      '${time.second.toString().padLeft(2, '0')}';
}

class _EvidencePdfViewerDialog extends StatefulWidget {
  const _EvidencePdfViewerDialog({
    required this.signedUrl,
    required this.dispute,
  });

  final String signedUrl;
  final Dispute dispute;

  @override
  State<_EvidencePdfViewerDialog> createState() => _EvidencePdfViewerDialogState();
}

class _EvidencePdfViewerDialogState extends State<_EvidencePdfViewerDialog> {
  final PdfViewerController _pdfViewerController = PdfViewerController();
  bool _isLoading = true;
  String? _errorMessage;

  @override
  void dispose() {
    _pdfViewerController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final size = MediaQuery.of(context).size;

    return Dialog(
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(12),
        side: BorderSide(color: theme.dividerColor),
      ),
      backgroundColor: theme.colorScheme.surface,
      child: ConstrainedBox(
        constraints: BoxConstraints(
          maxWidth: 900,
          maxHeight: size.height * 0.90,
        ),
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              // ── Modal Header ──
              Row(
                children: [
                  const Icon(Icons.picture_as_pdf, color: Colors.redAccent, size: 26),
                  const SizedBox(width: 12),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          'Evidence PDF Document',
                          style: theme.textTheme.titleMedium?.copyWith(
                            fontWeight: FontWeight.w700,
                          ),
                        ),
                        const SizedBox(height: 2),
                        Text(
                          'Dispute: ${widget.dispute.id}',
                          style: theme.textTheme.bodySmall,
                        ),
                      ],
                    ),
                  ),
                  IconButton(
                    onPressed: () => Navigator.of(context).pop(),
                    icon: const Icon(Icons.close, size: 20),
                    tooltip: 'Close',
                  ),
                ],
              ),
              Divider(height: 24, color: theme.dividerColor),

              // ── Retained Metadata Section ──
              /*Container(
                padding: const EdgeInsets.all(16),
                decoration: BoxDecoration(
                  color: theme.colorScheme.surfaceContainerLowest,
                  borderRadius: BorderRadius.circular(8),
                  border: Border.all(color: theme.dividerColor),
                ),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        const Icon(Icons.cloud_done_outlined, size: 18, color: Colors.blue),
                        const SizedBox(width: 8),
                        Text(
                          'Direct Supabase Storage CDN',
                          style: theme.textTheme.titleSmall?.copyWith(fontWeight: FontWeight.w600),
                        ),
                      ],
                    ),
                    const SizedBox(height: 8),
                    Text(
                      'Direct short-lived signed URL generated from Supabase Storage. PDF bytes are served directly from the CDN without server memory/disk bottlenecks.',
                      style: theme.textTheme.bodySmall,
                    ),
                    const SizedBox(height: 12),
                    _DetailRow(
                      label: 'Storage Path',
                      value: widget.dispute.storagePath ?? 'evidence-pdfs/${widget.dispute.id}/evidence.pdf',
                    ),
                    const SizedBox(height: 6),
                    _DetailRow(label: 'Document ID', value: widget.dispute.documentId ?? 'N/A'),
                    const SizedBox(height: 6),
                    const _DetailRow(label: 'URL Valid For', value: '1 Hour (3600 seconds)'),
                  ],
                ),
              ), */
              //const SizedBox(height: 12),

              // ── Raw Signed URL ──
              /*Container(
                padding: const EdgeInsets.all(10),
                decoration: BoxDecoration(
                  color: theme.colorScheme.surfaceContainerHigh,
                  borderRadius: BorderRadius.circular(6),
                ),
                child: SelectableText(
                  widget.signedUrl,
                  maxLines: 2,
                  style: theme.textTheme.bodySmall?.copyWith(
                    fontFamily: 'monospace',
                    fontSize: 11,
                  ),
                ),
              ),
              const SizedBox(height: 14),*/

              // ── Embedded PDF Viewer with State Handling ──
              Expanded(
                child: Container(
                  clipBehavior: Clip.antiAlias,
                  decoration: BoxDecoration(
                    borderRadius: BorderRadius.circular(8),
                    border: Border.all(color: theme.dividerColor),
                    color: theme.colorScheme.surfaceContainerLowest,
                  ),
                  child: Stack(
                    children: [
                      if (_errorMessage != null)
                        Center(
                          child: Padding(
                            padding: const EdgeInsets.all(24),
                            child: Column(
                              mainAxisSize: MainAxisSize.min,
                              children: [
                                Icon(Icons.error_outline, size: 42, color: theme.colorScheme.error),
                                const SizedBox(height: 12),
                                Text(
                                  'Failed to Load PDF Document',
                                  style: theme.textTheme.titleSmall?.copyWith(
                                    color: theme.colorScheme.error,
                                    fontWeight: FontWeight.w600,
                                  ),
                                ),
                                const SizedBox(height: 6),
                                Text(
                                  _errorMessage!,
                                  textAlign: TextAlign.center,
                                  style: theme.textTheme.bodySmall,
                                ),
                                const SizedBox(height: 16),
                                OutlinedButton.icon(
                                  onPressed: () {
                                    setState(() {
                                      _errorMessage = null;
                                      _isLoading = true;
                                    });
                                  },
                                  icon: const Icon(Icons.refresh, size: 16),
                                  label: const Text('Retry Loading'),
                                ),
                              ],
                            ),
                          ),
                        )
                      else
                        SfPdfViewer.network(
                          widget.signedUrl,
                          controller: _pdfViewerController,
                          enableDoubleTapZooming: true,
                          canShowScrollHead: true,
                          canShowScrollStatus: true,
                          pageLayoutMode: PdfPageLayoutMode.continuous,
                          scrollDirection: PdfScrollDirection.vertical,
                          onDocumentLoaded: (PdfDocumentLoadedDetails details) {
                            if (mounted) {
                              setState(() => _isLoading = false);
                            }
                          },
                          onDocumentLoadFailed: (PdfDocumentLoadFailedDetails details) {
                            if (mounted) {
                              setState(() {
                                _isLoading = false;
                                _errorMessage = details.description.isNotEmpty
                                    ? details.description
                                    : 'The signed URL may have expired or network is unreachable.';
                              });
                            }
                          },
                        ),

                      if (_isLoading && _errorMessage == null)
                        Container(
                          color: theme.colorScheme.surface.withValues(alpha: 0.75),
                          child: Center(
                            child: Column(
                              mainAxisSize: MainAxisSize.min,
                              children: [
                                const CircularProgressIndicator(),
                                const SizedBox(height: 12),
                                Text(
                                  'Fetching evidence PDF bytes from Supabase CDN...',
                                  style: theme.textTheme.bodySmall?.copyWith(fontWeight: FontWeight.w500),
                                ),
                              ],
                            ),
                          ),
                        ),
                    ],
                  ),
                ),
              ),
              const SizedBox(height: 14),

              // ── Action Buttons & Viewer Controls ──
              Row(
                children: [
                  if (_errorMessage == null && !_isLoading) ...[
                    IconButton(
                      icon: const Icon(Icons.zoom_in, size: 18),
                      tooltip: 'Zoom In',
                      onPressed: () {
                        _pdfViewerController.zoomLevel = (_pdfViewerController.zoomLevel + 0.25).clamp(1.0, 3.0);
                      },
                    ),
                    IconButton(
                      icon: const Icon(Icons.zoom_out, size: 18),
                      tooltip: 'Zoom Out',
                      onPressed: () {
                        _pdfViewerController.zoomLevel = (_pdfViewerController.zoomLevel - 0.25).clamp(1.0, 3.0);
                      },
                    ),
                    IconButton(
                      icon: const Icon(Icons.fit_screen, size: 18),
                      tooltip: 'Reset Zoom',
                      onPressed: () {
                        _pdfViewerController.zoomLevel = 1.0;
                      },
                    ),
                  ],
                  const Spacer(),
                  OutlinedButton.icon(
                    onPressed: () {
                      Clipboard.setData(ClipboardData(text: widget.signedUrl));
                      ScaffoldMessenger.of(context).showSnackBar(
                        const SnackBar(
                          content: Text('Signed PDF URL copied to clipboard!'),
                          duration: Duration(seconds: 2),
                        ),
                      );
                    },
                    icon: const Icon(Icons.copy, size: 16),
                    label: const Text('Copy Signed URL'),
                  ),
                  const SizedBox(width: 12),
                  FilledButton.icon(
                    onPressed: () {
                      Clipboard.setData(ClipboardData(text: widget.signedUrl));
                      ScaffoldMessenger.of(context).showSnackBar(
                        const SnackBar(
                          content: Text('Signed URL copied to clipboard for direct download / browser viewing.'),
                          duration: Duration(seconds: 3),
                        ),
                      );
                    },
                    icon: const Icon(Icons.file_download_outlined, size: 16),
                    label: const Text('Download PDF'),
                  ),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }
}
