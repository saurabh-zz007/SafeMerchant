import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:get/get.dart';

import '../theme/theme_provider.dart';
import '../view_models/dashboard_controller.dart';

class DeveloperOptionsScreen extends StatelessWidget {
  const DeveloperOptionsScreen({
    super.key,
    required this.viewModel,
    required this.themeProvider,
    this.onNavigateToDisputes,
  });

  final DashboardController viewModel;
  final ThemeProvider themeProvider;
  final void Function(String disputeId)? onNavigateToDisputes;

  void _confirmReset(BuildContext context, DashboardController controller) {
    if (controller.isProcessingDispute) {
      showDialog<void>(
        context: context,
        barrierDismissible: false,
        builder: (ctx) => ForceResetUrgentDialog(controller: controller),
      );
    } else {
      showDialog<void>(
        context: context,
        barrierDismissible: false,
        builder: (ctx) => StandardResetDialog(controller: controller),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return GetBuilder<DashboardController>(
      init: viewModel,
      builder: (controller) {
        final isProcessing = controller.isProcessingDispute;

        return CustomScrollView(
          slivers: [
            SliverPadding(
              padding: const EdgeInsets.all(28),
              sliver: SliverToBoxAdapter(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    // Header
                    Row(
                      children: [
                        Container(
                          padding: const EdgeInsets.all(10),
                          decoration: BoxDecoration(
                            color: theme.colorScheme.primary.withValues(alpha: 0.12),
                            borderRadius: BorderRadius.circular(10),
                          ),
                          child: Icon(
                            Icons.terminal_rounded,
                            color: theme.colorScheme.primary,
                            size: 24,
                          ),
                        ),
                        const SizedBox(width: 14),
                        Expanded(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(
                                'Developer Options',
                                style: theme.textTheme.headlineSmall?.copyWith(
                                  fontWeight: FontWeight.bold,
                                ),
                              ),
                              const SizedBox(height: 4),
                              Text(
                                'Construct live test dispute scenarios, toggle environments, and administer database storage.',
                                style: theme.textTheme.bodySmall,
                              ),
                            ],
                          ),
                        ),
                        if (isProcessing)
                          Container(
                            padding: const EdgeInsets.symmetric(
                              horizontal: 10,
                              vertical: 6,
                            ),
                            decoration: BoxDecoration(
                              color: Colors.amber.withValues(alpha: 0.15),
                              borderRadius: BorderRadius.circular(6),
                              border: Border.all(
                                color: Colors.amber.withValues(alpha: 0.4),
                              ),
                            ),
                            child: Row(
                              mainAxisSize: MainAxisSize.min,
                              children: [
                                const SizedBox(
                                  width: 12,
                                  height: 12,
                                  child: CircularProgressIndicator(
                                    strokeWidth: 2,
                                    color: Colors.amber,
                                  ),
                                ),
                                const SizedBox(width: 8),
                                Text(
                                  'Dispute Processing Active',
                                  style: TextStyle(
                                    color: (theme.brightness == Brightness.dark)
                                        ? Colors.amberAccent
                                        : Colors.amber.shade900,
                                    fontSize: 12,
                                    fontWeight: FontWeight.w700,
                                  ),
                                ),
                              ],
                            ),
                          ),
                      ],
                    ),
                    const SizedBox(height: 24),

                    // Section 1: Guided Scenario Builder (Create Test Dispute)
                    _CreateTestDisputeCard(
                      controller: controller,
                      onNavigateToDisputes: onNavigateToDisputes,
                    ),

                    const SizedBox(height: 24),

                    // Section 2: Backend Environment
                    _DeveloperCard(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Row(
                            children: [
                              Icon(
                                Icons.dns_outlined,
                                size: 20,
                                color: theme.colorScheme.primary,
                              ),
                              const SizedBox(width: 8),
                              Text(
                                'Backend Environment',
                                style: theme.textTheme.titleMedium?.copyWith(
                                  fontWeight: FontWeight.bold,
                                ),
                              ),
                            ],
                          ),
                          const SizedBox(height: 6),
                          Text(
                            'Select whether the dashboard connects to your local development server or cloud deployment.',
                            style: theme.textTheme.bodySmall,
                          ),
                          const SizedBox(height: 16),

                          if (isProcessing) ...[
                            Container(
                              padding: const EdgeInsets.symmetric(
                                horizontal: 12,
                                vertical: 10,
                              ),
                              decoration: BoxDecoration(
                                color: Colors.amber.withValues(alpha: 0.10),
                                borderRadius: BorderRadius.circular(8),
                                border: Border.all(
                                  color: Colors.amber.withValues(alpha: 0.3),
                                ),
                              ),
                              child: Row(
                                children: [
                                  Icon(
                                    Icons.lock_clock_outlined,
                                    color: (theme.brightness == Brightness.dark)
                                        ? Colors.amberAccent
                                        : Colors.amber.shade800,
                                    size: 18,
                                  ),
                                  const SizedBox(width: 10),
                                  Expanded(
                                    child: Text(
                                      'Environment toggle is locked while disputes are being actively processed. Wait for completion or reset the system.',
                                      style: theme.textTheme.bodySmall?.copyWith(
                                        fontWeight: FontWeight.w600,
                                        color: (theme.brightness == Brightness.dark)
                                            ? Colors.amberAccent
                                            : Colors.amber.shade900,
                                      ),
                                    ),
                                  ),
                                ],
                              ),
                            ),
                            const SizedBox(height: 14),
                          ],

                          SegmentedButton<bool>(
                            segments: const [
                              ButtonSegment<bool>(
                                value: true,
                                icon: Icon(Icons.computer_outlined, size: 16),
                                label: Text('Local Server (Dev)'),
                              ),
                              ButtonSegment<bool>(
                                value: false,
                                icon: Icon(Icons.cloud_outlined, size: 16),
                                label: Text('Cloud Server (Staging)'),
                              ),
                            ],
                            selected: {controller.useLocalServer},
                            onSelectionChanged: isProcessing
                                ? null
                                : (newSelection) {
                                    if (newSelection.isNotEmpty) {
                                      controller.setUseLocalServer(
                                        newSelection.first,
                                      );
                                    }
                                  },
                          ),
                          const SizedBox(height: 18),
                          Container(
                            padding: const EdgeInsets.all(16),
                            decoration: BoxDecoration(
                              color: theme.colorScheme.primary.withValues(
                                alpha: 0.04,
                              ),
                              border: Border.all(color: theme.dividerColor),
                              borderRadius: BorderRadius.circular(8),
                            ),
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                _DeveloperDetailRow(
                                  label: 'API Base URL:',
                                  value: controller.apiBaseUrl,
                                ),
                                const SizedBox(height: 8),
                                _DeveloperDetailRow(
                                  label: 'WebSocket URL:',
                                  value: controller.websocketUrl,
                                ),
                                const SizedBox(height: 8),
                                _DeveloperDetailRow(
                                  label: 'Live Status:',
                                  value: controller.connectionStatus.name
                                      .toUpperCase(),
                                  valueColor: controller.connectionStatus ==
                                          DashboardConnectionStatus.connected
                                      ? Colors.green
                                      : controller.connectionStatus ==
                                              DashboardConnectionStatus.error
                                          ? theme.colorScheme.error
                                          : theme.colorScheme.secondary,
                                ),
                              ],
                            ),
                          ),
                        ],
                      ),
                    ),

                    const SizedBox(height: 24),

                    // Section 3: Database Administration
                    _DeveloperCard(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Row(
                            children: [
                              Icon(
                                Icons.storage_outlined,
                                size: 20,
                                color: theme.colorScheme.error,
                              ),
                              const SizedBox(width: 8),
                              Text(
                                'Database & Storage Administration',
                                style: theme.textTheme.titleMedium?.copyWith(
                                  fontWeight: FontWeight.bold,
                                  color: theme.colorScheme.error,
                                ),
                              ),
                            ],
                          ),
                          const SizedBox(height: 6),
                          Text(
                            'Wipe all PostgreSQL dispute records, purge stored PDF evidence from Supabase Storage, clear LangGraph checkpoint savers, and broadcast refreshes across all connected dashboards.',
                            style: theme.textTheme.bodySmall,
                          ),
                          const SizedBox(height: 20),
                          Align(
                            alignment: Alignment.centerLeft,
                            child: controller.isResettingDatabase
                                ? const Row(
                                    mainAxisSize: MainAxisSize.min,
                                    children: [
                                      SizedBox(
                                        width: 20,
                                        height: 20,
                                        child: CircularProgressIndicator(
                                          strokeWidth: 2,
                                        ),
                                      ),
                                      SizedBox(width: 12),
                                      Text('Resetting system database and storage...'),
                                    ],
                                  )
                                : FilledButton.icon(
                                    onPressed: () =>
                                        _confirmReset(context, controller),
                                    style: FilledButton.styleFrom(
                                      backgroundColor: theme.colorScheme.error,
                                      foregroundColor:
                                          theme.colorScheme.onError,
                                      padding: const EdgeInsets.symmetric(
                                        horizontal: 20,
                                        vertical: 14,
                                      ),
                                    ),
                                    icon: const Icon(
                                      Icons.delete_forever_outlined,
                                      size: 18,
                                    ),
                                    label: const Text('Reset System Database'),
                                  ),
                          ),
                        ],
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ],
        );
      },
    );
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// CREATE TEST DISPUTE CARD (GUIDED FORM)
// ─────────────────────────────────────────────────────────────────────────────

class _CreateTestDisputeCard extends StatefulWidget {
  const _CreateTestDisputeCard({
    required this.controller,
    this.onNavigateToDisputes,
  });

  final DashboardController controller;
  final void Function(String disputeId)? onNavigateToDisputes;

  @override
  State<_CreateTestDisputeCard> createState() => _CreateTestDisputeCardState();
}

class _CreateTestDisputeCardState extends State<_CreateTestDisputeCard> {
  final _formKey = GlobalKey<FormState>();
  final _amountController = TextEditingController(text: '2999');
  final _itemDescController = TextEditingController(text: 'Bluetooth Earbuds Pro');
  final _accountAgeController = TextEditingController(text: '180');

  String _deliveryStatus = 'Delivered (Signed)';
  String _customerCommunication = 'Customer confirms receipt';
  bool _is2faVerified = true;
  String _reasonCode = 'product_not_received';

  String? _lastCreatedDisputeId;
  String? _lastCreatedDetails;

  static const _deliveryOptions = [
    'Delivered (Signed)',
    'Delivered (No Signature)',
    'Lost in Transit',
    'In Transit',
  ];

  static const _communicationOptions = [
    'Customer confirms receipt',
    'Customer disputes receipt',
    'No communication on file',
  ];

  static const _reasonCodeOptions = [
    {'value': 'product_not_received', 'label': 'product_not_received (Item / Product Not Received)'},
    {'value': 'processed_invalid_expired_card', 'label': 'processed_invalid_expired_card (Invalid/Expired Card)'},
    {'value': 'chargeback', 'label': 'chargeback (General Chargeback / Unrecognized)'},
    {'value': 'fraud', 'label': 'fraud (Fraudulent Transaction Claim)'},
    {'value': 'product_not_as_described', 'label': 'product_not_as_described (Not as Described / Damaged)'},
    {'value': 'duplicate', 'label': 'duplicate (Duplicate Processing)'},
    {'value': 'subscription_cancelled', 'label': 'subscription_cancelled (Subscription Cancelled)'},
    {'value': 'customer_dispute', 'label': 'customer_dispute (General Customer Dispute)'},
  ];

  @override
  void dispose() {
    _amountController.dispose();
    _itemDescController.dispose();
    _accountAgeController.dispose();
    super.dispose();
  }

  void _applyPreset({
    required int amount,
    required String itemDesc,
    required String delivery,
    required String comm,
    required bool is2fa,
    required int age,
    required String reason,
  }) {
    setState(() {
      _amountController.text = amount.toString();
      _itemDescController.text = itemDesc;
      _deliveryStatus = delivery;
      _customerCommunication = comm;
      _is2faVerified = is2fa;
      _accountAgeController.text = age.toString();
      _reasonCode = reason;
      _lastCreatedDisputeId = null;
    });
  }

  Future<void> _submitDisputeScenario() async {
    if (!_formKey.currentState!.validate()) {
      return;
    }

    final amountInr = int.tryParse(_amountController.text.trim()) ?? 2999;
    final accountAge = int.tryParse(_accountAgeController.text.trim()) ?? 180;
    final itemDesc = _itemDescController.text.trim().isNotEmpty
        ? _itemDescController.text.trim()
        : 'Wireless Audio Earbuds';

    final createdId = await widget.controller.createTestDispute(
      amountInr: amountInr,
      itemDescription: itemDesc,
      deliveryStatus: _deliveryStatus,
      customerCommunication: _customerCommunication,
      is2faVerified: _is2faVerified,
      accountAgeDays: accountAge,
      reasonCode: _reasonCode,
    );

    if (mounted && createdId != null) {
      setState(() {
        _lastCreatedDisputeId = createdId;
        _lastCreatedDetails =
            '₹${amountInr.toString()} • $_deliveryStatus • $_reasonCode';
      });

      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Row(
            children: [
              const Icon(Icons.check_circle_outline, color: Colors.white),
              const SizedBox(width: 10),
              Expanded(
                child: Text(
                  'Test dispute ($createdId) created & webhook dispatched live!',
                ),
              ),
            ],
          ),
          backgroundColor: Colors.green.shade700,
          behavior: SnackBarBehavior.floating,
          action: widget.onNavigateToDisputes != null
              ? SnackBarAction(
                  label: 'VIEW IN DISPUTES',
                  textColor: Colors.white,
                  onPressed: () => widget.onNavigateToDisputes!(createdId),
                )
              : null,
        ),
      );
    }
  }

  String _getScenarioPreview() {
    final amount = int.tryParse(_amountController.text) ?? 2999;
    if (_deliveryStatus == 'Lost in Transit' && amount <= 10000) {
      return '🟢 Legitimate Lost Claim (Expected: Auto Refund under threshold)';
    } else if (_deliveryStatus == 'Lost in Transit' && amount > 10000) {
      return '🟡 High-Value Lost Item (Expected: Human Review for Refund Approval)';
    } else if (_deliveryStatus == 'Delivered (Signed)' &&
        _customerCommunication == 'Customer confirms receipt') {
      return '🛡️ Friendly Fraud Defense (Expected: Winnable Evidence → Auto Submit)';
    } else if (_deliveryStatus == 'Delivered (No Signature)' && amount > 10000) {
      return '⚖️ Ambiguous High-Value Delivery (Expected: Route to Human Review)';
    } else if (!_is2faVerified && _reasonCode == 'fraud') {
      return '⚠️ Unverified Fraud Risk (Expected: Evidence triage assessment)';
    }
    return '⚡ Custom Scenario: Simulated evidence will be fed to agent triage pipeline';
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final isCreating = widget.controller.isCreatingTestDispute;

    return _DeveloperCard(
      child: Form(
        key: _formKey,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // Title Header
            Row(
              children: [
                Container(
                  padding: const EdgeInsets.all(8),
                  decoration: BoxDecoration(
                    color: Colors.indigo.withValues(alpha: 0.12),
                    borderRadius: BorderRadius.circular(8),
                  ),
                  child: const Icon(
                    Icons.science_outlined,
                    size: 20,
                    color: Colors.indigoAccent,
                  ),
                ),
                const SizedBox(width: 10),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        'Create Test Dispute (Guided Scenario Builder)',
                        style: theme.textTheme.titleMedium?.copyWith(
                          fontWeight: FontWeight.bold,
                        ),
                      ),
                      const SizedBox(height: 2),
                      Text(
                        'Construct synthetic dispute scenarios with pre-configured evidence and dispatch real signed webhooks directly to the pipeline.',
                        style: theme.textTheme.bodySmall,
                      ),
                    ],
                  ),
                ),
              ],
            ),
            const SizedBox(height: 18),

            // Presets row
            Wrap(
              spacing: 8,
              runSpacing: 8,
              crossAxisAlignment: WrapCrossAlignment.center,
              children: [
                Text(
                  'Quick Scenarios:',
                  style: theme.textTheme.bodySmall?.copyWith(
                    fontWeight: FontWeight.bold,
                  ),
                ),
                ActionChip(
                  avatar: const Icon(Icons.verified_user_outlined, size: 14),
                  label: const Text('Friendly Fraud Win (₹3,499)'),
                  onPressed: isCreating
                      ? null
                      : () => _applyPreset(
                            amount: 3499,
                            itemDesc: 'Nike Running Shoes - Size 9',
                            delivery: 'Delivered (Signed)',
                            comm: 'Customer confirms receipt',
                            is2fa: true,
                            age: 180,
                            reason: 'product_not_received',
                          ),
                ),
                ActionChip(
                  avatar: const Icon(Icons.local_shipping_outlined, size: 14),
                  label: const Text('Lost in Transit Refund (₹2,999)'),
                  onPressed: isCreating
                      ? null
                      : () => _applyPreset(
                            amount: 2999,
                            itemDesc: 'Bluetooth Earbuds Pro',
                            delivery: 'Lost in Transit',
                            comm: 'Customer disputes receipt',
                            is2fa: true,
                            age: 310,
                            reason: 'product_not_received',
                          ),
                ),
                ActionChip(
                  avatar: const Icon(Icons.rate_review_outlined, size: 14),
                  label: const Text('High-Value Ambiguous (₹24,999)'),
                  onPressed: isCreating
                      ? null
                      : () => _applyPreset(
                            amount: 24999,
                            itemDesc: 'Apple iPad 9th Gen 64GB',
                            delivery: 'Delivered (No Signature)',
                            comm: 'No communication on file',
                            is2fa: true,
                            age: 890,
                            reason: 'product_not_received',
                          ),
                ),
                ActionChip(
                  avatar: const Icon(Icons.no_accounts_outlined, size: 14),
                  label: const Text('Weak Defense / Loss (₹1,299)'),
                  onPressed: isCreating
                      ? null
                      : () => _applyPreset(
                            amount: 1299,
                            itemDesc: 'Clear Phone Case',
                            delivery: 'Lost in Transit',
                            comm: 'No communication on file',
                            is2fa: false,
                            age: 2,
                            reason: 'chargeback',
                          ),
                ),
              ],
            ),
            const SizedBox(height: 20),

            // Form Fields Grid
            LayoutBuilder(
              builder: (context, constraints) {
                final isWide = constraints.maxWidth > 650;
                return Column(
                  children: [
                    // Row 1: Amount + Item Description
                    if (isWide)
                      Row(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Expanded(flex: 2, child: _buildAmountField()),
                          const SizedBox(width: 16),
                          Expanded(flex: 3, child: _buildItemDescField()),
                        ],
                      )
                    else ...[
                      _buildAmountField(),
                      const SizedBox(height: 14),
                      _buildItemDescField(),
                    ],
                    const SizedBox(height: 14),

                    // Row 2: Delivery Status + Customer Communication
                    if (isWide)
                      Row(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Expanded(child: _buildDeliveryStatusDropdown(theme)),
                          const SizedBox(width: 16),
                          Expanded(child: _buildCustomerCommDropdown(theme)),
                        ],
                      )
                    else ...[
                      _buildDeliveryStatusDropdown(theme),
                      const SizedBox(height: 14),
                      _buildCustomerCommDropdown(theme),
                    ],
                    const SizedBox(height: 14),

                    // Row 3: 2FA Toggle + Account Age + Reason Code
                    if (isWide)
                      Row(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Expanded(child: _build2faToggle(theme)),
                          const SizedBox(width: 16),
                          Expanded(child: _buildAccountAgeField()),
                          const SizedBox(width: 16),
                          Expanded(flex: 2, child: _buildReasonCodeDropdown(theme)),
                        ],
                      )
                    else ...[
                      _build2faToggle(theme),
                      const SizedBox(height: 14),
                      _buildAccountAgeField(),
                      const SizedBox(height: 14),
                      _buildReasonCodeDropdown(theme),
                    ],
                  ],
                );
              },
            ),

            const SizedBox(height: 18),

            // Dynamic Scenario Preview Box
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
              decoration: BoxDecoration(
                color: theme.colorScheme.primary.withValues(alpha: 0.05),
                borderRadius: BorderRadius.circular(8),
                border: Border.all(
                  color: theme.colorScheme.primary.withValues(alpha: 0.15),
                ),
              ),
              child: Row(
                children: [
                  Icon(
                    Icons.auto_awesome,
                    size: 16,
                    color: theme.colorScheme.primary,
                  ),
                  const SizedBox(width: 10),
                  Expanded(
                    child: Text(
                      _getScenarioPreview(),
                      style: theme.textTheme.bodySmall?.copyWith(
                        fontWeight: FontWeight.w600,
                        color: theme.colorScheme.primary,
                      ),
                    ),
                  ),
                ],
              ),
            ),

            const SizedBox(height: 20),

            // Action Buttons & Live Feedback
            Row(
              children: [
                FilledButton.icon(
                  onPressed: isCreating ? null : _submitDisputeScenario,
                  style: FilledButton.styleFrom(
                    padding: const EdgeInsets.symmetric(
                      horizontal: 22,
                      vertical: 14,
                    ),
                  ),
                  icon: isCreating
                      ? const SizedBox(
                          width: 16,
                          height: 16,
                          child: CircularProgressIndicator(
                            strokeWidth: 2,
                            color: Colors.white,
                          ),
                        )
                      : const Icon(Icons.bolt, size: 18),
                  label: Text(
                    isCreating
                        ? 'Dispatching Webhook Pipeline...'
                        : 'Create & Dispatch Test Dispute',
                  ),
                ),
                const SizedBox(width: 14),
                if (_lastCreatedDisputeId != null) ...[
                  Expanded(
                    child: Container(
                      padding: const EdgeInsets.symmetric(
                        horizontal: 14,
                        vertical: 8,
                      ),
                      decoration: BoxDecoration(
                        color: Colors.green.withValues(alpha: 0.12),
                        borderRadius: BorderRadius.circular(8),
                        border: Border.all(
                          color: Colors.green.withValues(alpha: 0.3),
                        ),
                      ),
                      child: Row(
                        children: [
                          const Icon(
                            Icons.check_circle_rounded,
                            color: Colors.green,
                            size: 18,
                          ),
                          const SizedBox(width: 8),
                          Expanded(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                SelectableText(
                                  'Active: $_lastCreatedDisputeId',
                                  style: const TextStyle(
                                    fontWeight: FontWeight.bold,
                                    fontSize: 12,
                                    fontFamily: 'Courier New',
                                  ),
                                ),
                                if (_lastCreatedDetails != null)
                                  Text(
                                    _lastCreatedDetails!,
                                    style: TextStyle(
                                      fontSize: 11,
                                      color: theme.textTheme.bodySmall?.color,
                                    ),
                                  ),
                              ],
                            ),
                          ),
                          if (widget.onNavigateToDisputes != null)
                            FilledButton.tonalIcon(
                              onPressed: () => widget.onNavigateToDisputes!(
                                _lastCreatedDisputeId!,
                              ),
                              style: FilledButton.styleFrom(
                                padding: const EdgeInsets.symmetric(
                                  horizontal: 12,
                                  vertical: 8,
                                ),
                                visualDensity: VisualDensity.compact,
                              ),
                              icon: const Icon(Icons.arrow_forward, size: 14),
                              label: const Text('View in Disputes'),
                            ),
                        ],
                      ),
                    ),
                  ),
                ],
              ],
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildAmountField() {
    return TextFormField(
      controller: _amountController,
      keyboardType: TextInputType.number,
      inputFormatters: [FilteringTextInputFormatter.digitsOnly],
      decoration: const InputDecoration(
        labelText: 'Disputed Amount (INR)',
        hintText: '2999',
        prefixText: '₹ ',
        border: OutlineInputBorder(),
        contentPadding: EdgeInsets.symmetric(horizontal: 12, vertical: 12),
      ),
      validator: (val) {
        if (val == null || val.trim().isEmpty) {
          return 'Enter disputed amount';
        }
        final numVal = int.tryParse(val.trim());
        if (numVal == null || numVal <= 0) {
          return 'Amount must be > 0';
        }
        return null;
      },
    );
  }

  Widget _buildItemDescField() {
    return TextFormField(
      controller: _itemDescController,
      decoration: const InputDecoration(
        labelText: 'Item Description',
        hintText: 'e.g., Bluetooth Earbuds Pro',
        border: OutlineInputBorder(),
        contentPadding: EdgeInsets.symmetric(horizontal: 12, vertical: 12),
      ),
    );
  }

  bool _isCommOptionEnabled(String comm) {
    switch (_deliveryStatus) {
      case 'Delivered (Signed)':
        return comm != 'Customer disputes receipt';
      case 'Delivered (No Signature)':
        return true;
      case 'Lost in Transit':
        return comm != 'Customer confirms receipt';
      case 'In Transit':
        return comm == 'No communication on file';
      default:
        return true;
    }
  }

  String? _getCommOptionDisabledReason(String comm) {
    switch (_deliveryStatus) {
      case 'Delivered (Signed)':
        if (comm == 'Customer disputes receipt') {
          return 'Not applicable — package was signed for upon delivery.';
        }
        break;
      case 'Lost in Transit':
        if (comm == 'Customer confirms receipt') {
          return 'Not applicable — package reported lost in transit.';
        }
        break;
      case 'In Transit':
        if (comm != 'No communication on file') {
          return 'Not applicable — package is still in transit.';
        }
        break;
    }
    return null;
  }

  void _onDeliveryStatusChanged(String newStatus) {
    setState(() {
      _deliveryStatus = newStatus;
      if (!_isCommOptionEnabled(_customerCommunication)) {
        if (newStatus == 'Lost in Transit') {
          _customerCommunication = 'Customer disputes receipt';
        } else if (newStatus == 'In Transit') {
          _customerCommunication = 'No communication on file';
        } else if (newStatus == 'Delivered (Signed)') {
          _customerCommunication = 'Customer confirms receipt';
        } else {
          _customerCommunication = 'No communication on file';
        }
      }
    });
  }

  Widget _buildDeliveryStatusDropdown(ThemeData theme) {
    return DropdownButtonFormField<String>(
      key: ValueKey('delivery_$_deliveryStatus'),
      initialValue: _deliveryStatus,
      decoration: const InputDecoration(
        labelText: 'Delivery Status',
        border: OutlineInputBorder(),
        contentPadding: EdgeInsets.symmetric(horizontal: 12, vertical: 12),
      ),
      items: _deliveryOptions.map((status) {
        IconData icon;
        Color? color;
        if (status.contains('Signed')) {
          icon = Icons.verified_outlined;
          color = Colors.green;
        } else if (status.contains('No Signature')) {
          icon = Icons.door_front_door_outlined;
          color = Colors.amber.shade700;
        } else if (status.contains('Lost')) {
          icon = Icons.error_outline;
          color = Colors.redAccent;
        } else {
          icon = Icons.local_shipping_outlined;
          color = Colors.blue;
        }

        return DropdownMenuItem(
          value: status,
          child: Row(
            children: [
              Icon(icon, size: 16, color: color),
              const SizedBox(width: 8),
              Text(status, style: const TextStyle(fontSize: 13)),
            ],
          ),
        );
      }).toList(),
      onChanged: (val) {
        if (val != null) _onDeliveryStatusChanged(val);
      },
    );
  }

  Widget _buildCustomerCommDropdown(ThemeData theme) {
    return DropdownButtonFormField<String>(
      key: ValueKey('comm_$_customerCommunication'),
      initialValue: _customerCommunication,
      decoration: const InputDecoration(
        labelText: 'Customer Communication',
        border: OutlineInputBorder(),
        contentPadding: EdgeInsets.symmetric(horizontal: 12, vertical: 12),
      ),
      items: _communicationOptions.map((comm) {
        final isEnabled = _isCommOptionEnabled(comm);
        final disabledReason = _getCommOptionDisabledReason(comm);

        IconData icon;
        Color? color;
        if (comm.contains('confirms')) {
          icon = Icons.mark_email_read_outlined;
          color = Colors.green;
        } else if (comm.contains('disputes')) {
          icon = Icons.mark_email_unread_outlined;
          color = Colors.orange;
        } else {
          icon = Icons.speaker_notes_off_outlined;
          color = Colors.grey;
        }

        return DropdownMenuItem<String>(
          value: comm,
          enabled: isEnabled,
          child: Tooltip(
            message: isEnabled ? '' : (disabledReason ?? 'Option disabled'),
            preferBelow: false,
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Icon(
                  icon,
                  size: 16,
                  color: isEnabled ? color : theme.disabledColor,
                ),
                const SizedBox(width: 8),
                Text(
                  comm,
                  style: TextStyle(
                    fontSize: 13,
                    color: isEnabled ? null : theme.disabledColor,
                  ),
                ),
                if (!isEnabled) ...[
                  const SizedBox(width: 6),
                  Icon(
                    Icons.info_outline,
                    size: 14,
                    color: theme.disabledColor,
                  ),
                ],
              ],
            ),
          ),
        );
      }).toList(),
      onChanged: (val) {
        if (val != null && _isCommOptionEnabled(val)) {
          setState(() => _customerCommunication = val);
        }
      },
    );
  }

  Widget _build2faToggle(ThemeData theme) {
    return InputDecorator(
      decoration: const InputDecoration(
        labelText: '2FA / OTP Verified',
        border: OutlineInputBorder(),
        contentPadding: EdgeInsets.symmetric(horizontal: 10, vertical: 4),
      ),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Row(
            children: [
              Icon(
                _is2faVerified ? Icons.lock_outline : Icons.lock_open_outlined,
                size: 16,
                color: _is2faVerified ? Colors.green : Colors.redAccent,
              ),
              const SizedBox(width: 6),
              Text(
                _is2faVerified ? 'Yes' : 'No',
                style: TextStyle(
                  fontWeight: FontWeight.bold,
                  fontSize: 13,
                  color: _is2faVerified ? Colors.green : Colors.redAccent,
                ),
              ),
            ],
          ),
          Switch(
            value: _is2faVerified,
            onChanged: (val) => setState(() => _is2faVerified = val),
          ),
        ],
      ),
    );
  }

  Widget _buildAccountAgeField() {
    return TextFormField(
      controller: _accountAgeController,
      keyboardType: TextInputType.number,
      inputFormatters: [FilteringTextInputFormatter.digitsOnly],
      decoration: const InputDecoration(
        labelText: 'Account Age (Days)',
        hintText: '180',
        border: OutlineInputBorder(),
        contentPadding: EdgeInsets.symmetric(horizontal: 12, vertical: 12),
      ),
      validator: (val) {
        if (val == null || val.trim().isEmpty) {
          return 'Enter account age';
        }
        return null;
      },
    );
  }

  Widget _buildReasonCodeDropdown(ThemeData theme) {
    return DropdownButtonFormField<String>(
      key: ValueKey('reason_$_reasonCode'),
      initialValue: _reasonCode,
      decoration: const InputDecoration(
        labelText: 'Razorpay Reason Code',
        border: OutlineInputBorder(),
        contentPadding: EdgeInsets.symmetric(horizontal: 12, vertical: 12),
      ),
      isExpanded: true,
      items: _reasonCodeOptions.map((opt) {
        return DropdownMenuItem(
          value: opt['value'],
          child: Text(
            opt['label']!,
            style: const TextStyle(fontSize: 12),
            overflow: TextOverflow.ellipsis,
          ),
        );
      }).toList(),
      onChanged: (val) {
        if (val != null) setState(() => _reasonCode = val);
      },
    );
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// DIALOGS & HELPER COMPONENTS
// ─────────────────────────────────────────────────────────────────────────────

class StandardResetDialog extends StatelessWidget {
  const StandardResetDialog({super.key, required this.controller});

  final DashboardController controller;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return AlertDialog(
      title: Row(
        children: [
          Icon(Icons.warning_amber_rounded, color: theme.colorScheme.error),
          const SizedBox(width: 10),
          const Text('Confirm System Reset'),
        ],
      ),
      content: const Text(
        'Are you sure you want to reset all database states? This will wipe all disputes, purge storage PDF evidence files, reset metrics and checkpointers, and trigger a fresh client reload. This action is irreversible.',
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.of(context).pop(),
          child: const Text('Cancel'),
        ),
        FilledButton(
          onPressed: () {
            Navigator.of(context).pop();
            _executeReset(context, controller);
          },
          style: FilledButton.styleFrom(
            backgroundColor: theme.colorScheme.error,
          ),
          child: const Text('Reset Everything'),
        ),
      ],
    );
  }
}

class ForceResetUrgentDialog extends StatefulWidget {
  const ForceResetUrgentDialog({super.key, required this.controller});

  final DashboardController controller;

  @override
  State<ForceResetUrgentDialog> createState() => _ForceResetUrgentDialogState();
}

class _ForceResetUrgentDialogState extends State<ForceResetUrgentDialog> {
  final _textController = TextEditingController();
  bool _canSubmit = false;

  @override
  void initState() {
    super.initState();
    _textController.addListener(() {
      final matches = _textController.text.trim() == 'CONFIRM';
      if (matches != _canSubmit) {
        setState(() {
          _canSubmit = matches;
        });
      }
    });
  }

  @override
  void dispose() {
    _textController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return AlertDialog(
      title: Row(
        children: [
          Container(
            padding: const EdgeInsets.all(8),
            decoration: BoxDecoration(
              color: theme.colorScheme.error.withValues(alpha: 0.15),
              borderRadius: BorderRadius.circular(8),
            ),
            child: Icon(
              Icons.dangerous_outlined,
              color: theme.colorScheme.error,
              size: 24,
            ),
          ),
          const SizedBox(width: 12),
          const Expanded(child: Text('Warning: Active Processing')),
        ],
      ),
      content: SizedBox(
        width: 440,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Container(
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                color: theme.colorScheme.error.withValues(alpha: 0.08),
                borderRadius: BorderRadius.circular(8),
                border: Border.all(
                  color: theme.colorScheme.error.withValues(alpha: 0.3),
                ),
              ),
              child: Text(
                'Warning: A dispute is currently processing. Resetting the database will force-terminate this operation.',
                style: theme.textTheme.bodyMedium?.copyWith(
                  color: theme.colorScheme.error,
                  fontWeight: FontWeight.w600,
                ),
              ),
            ),
            const SizedBox(height: 16),
            Text(
              'This will forcibly wipe all in-progress pipeline checkpoints, purge storage files, and terminate background agent tasks.',
              style: theme.textTheme.bodySmall,
            ),
            const SizedBox(height: 18),
            Text(
              'Type "CONFIRM" below to authorize force reset:',
              style: theme.textTheme.bodySmall?.copyWith(
                fontWeight: FontWeight.bold,
              ),
            ),
            const SizedBox(height: 8),
            TextField(
              controller: _textController,
              autofocus: true,
              decoration: const InputDecoration(
                hintText: 'CONFIRM',
                border: OutlineInputBorder(),
                contentPadding: EdgeInsets.symmetric(horizontal: 14, vertical: 12),
              ),
            ),
          ],
        ),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.of(context).pop(),
          child: const Text('Cancel'),
        ),
        FilledButton.icon(
          onPressed: _canSubmit
              ? () {
                  Navigator.of(context).pop();
                  _executeReset(context, widget.controller);
                }
              : null,
          style: FilledButton.styleFrom(
            backgroundColor: theme.colorScheme.error,
            foregroundColor: theme.colorScheme.onError,
          ),
          icon: const Icon(Icons.delete_forever, size: 16),
          label: const Text('Force Reset Everything'),
        ),
      ],
    );
  }
}

void _executeReset(BuildContext context, DashboardController controller) {
  controller.resetDatabase().then((_) {
    if (context.mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            controller.errorMessage ??
                'Database & storage reset successful. Refresh triggered.',
          ),
          backgroundColor: controller.errorMessage != null
              ? Theme.of(context).colorScheme.error
              : Theme.of(context).colorScheme.primary,
        ),
      );
    }
  });
}

class _DeveloperCard extends StatelessWidget {
  const _DeveloperCard({required this.child});

  final Widget child;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Container(
      decoration: BoxDecoration(
        color: theme.colorScheme.surface,
        border: Border.all(color: theme.dividerColor),
        borderRadius: BorderRadius.circular(10),
      ),
      padding: const EdgeInsets.all(22),
      child: child,
    );
  }
}

class _DeveloperDetailRow extends StatelessWidget {
  const _DeveloperDetailRow({
    required this.label,
    required this.value,
    this.valueColor,
  });

  final String label;
  final String value;
  final Color? valueColor;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        SizedBox(
          width: 140,
          child: Text(
            label,
            style: theme.textTheme.bodyMedium?.copyWith(
              fontWeight: FontWeight.w600,
            ),
          ),
        ),
        Expanded(
          child: SelectableText(
            value,
            style: theme.textTheme.bodyMedium?.copyWith(
              fontFamily: 'Courier New',
              color: valueColor ?? theme.textTheme.bodyMedium?.color,
            ),
          ),
        ),
      ],
    );
  }
}
