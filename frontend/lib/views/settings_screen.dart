import 'package:flutter/material.dart';
import 'dart:ui';

import '../theme/theme_provider.dart';
import '../view_models/dashboard_controller.dart';

enum SettingsSection { account, riskEngine, apiConfiguration }

class SettingsScreen extends StatefulWidget {
  const SettingsScreen({
    super.key,
    required this.themeProvider,
    required this.dashboardController,
  });

  final ThemeProvider themeProvider;
  final DashboardController dashboardController;

  @override
  State<SettingsScreen> createState() => _SettingsScreenState();
}

class _SettingsScreenState extends State<SettingsScreen> {
  SettingsSection _section = SettingsSection.account;
  double _autoAcceptThreshold = 72;

  late final TextEditingController _nameController;
  late final TextEditingController _emailController;
  late final TextEditingController _webhookController;
  late final TextEditingController _secretController;

  @override
  void initState() {
    super.initState();
    _nameController = TextEditingController(text: 'Risk Operations');
    _emailController = TextEditingController(text: 'ops@safemerchant.ai');
    _webhookController = TextEditingController(
      text: 'https://api.safemerchant.ai/api/v1/webhook',
    );
    _secretController =
        TextEditingController(text: 'sk_live_mocked_secret_key');
  }

  @override
  void dispose() {
    _nameController.dispose();
    _emailController.dispose();
    _webhookController.dispose();
    _secretController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return CustomScrollView(
      slivers: [
        SliverPadding(
          padding: const EdgeInsets.all(28),
          sliver: SliverToBoxAdapter(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Text('Settings',
                    style: Theme.of(context).textTheme.headlineSmall),
                const SizedBox(height: 6),
                Text(
                  'Workspace controls for operators, automation policy, and API access.',
                  style: Theme.of(context).textTheme.bodySmall,
                ),
                const SizedBox(height: 22),
                LayoutBuilder(
                  builder: (context, constraints) {
                    final stacked = constraints.maxWidth < 820;
                    final nav = _SettingsNavigation(
                      selected: _section,
                      onSelected: (section) =>
                          setState(() => _section = section),
                    );
                    final content = _SettingsContent(
                      section: _section,
                      nameController: _nameController,
                      emailController: _emailController,
                      webhookController: _webhookController,
                      secretController: _secretController,
                      autoAcceptThreshold: _autoAcceptThreshold,
                      themeProvider: widget.themeProvider,
                      onThresholdChanged: (value) {
                        setState(() => _autoAcceptThreshold = value);
                      },
                    );

                    if (stacked) {
                      return Column(
                        crossAxisAlignment: CrossAxisAlignment.stretch,
                        children: [
                          nav,
                          const SizedBox(height: 16),
                          content,
                        ],
                      );
                    }

                    return Row(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        SizedBox(width: 260, child: nav),
                        const SizedBox(width: 18),
                        Expanded(child: content),
                      ],
                    );
                  },
                ),
              ],
            ),
          ),
        ),
      ],
    );
  }
}

class _SettingsNavigation extends StatelessWidget {
  const _SettingsNavigation({
    required this.selected,
    required this.onSelected,
  });

  final SettingsSection selected;
  final ValueChanged<SettingsSection> onSelected;

  @override
  Widget build(BuildContext context) {
    return _FlatBox(
      padding: const EdgeInsets.all(8),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          _SettingsNavItem(
            icon: Icons.person_outline,
            label: 'Account Profile',
            selected: selected == SettingsSection.account,
            onPressed: () => onSelected(SettingsSection.account),
          ),
          _SettingsNavItem(
            icon: Icons.auto_awesome_outlined,
            label: 'Risk Engine',
            selected: selected == SettingsSection.riskEngine,
            onPressed: () => onSelected(SettingsSection.riskEngine),
          ),
          _SettingsNavItem(
            icon: Icons.key_outlined,
            label: 'API Configuration',
            selected: selected == SettingsSection.apiConfiguration,
            onPressed: () => onSelected(SettingsSection.apiConfiguration),
          ),
        ],
      ),
    );
  }
}

class _SettingsContent extends StatelessWidget {
  const _SettingsContent({
    required this.section,
    required this.nameController,
    required this.emailController,
    required this.webhookController,
    required this.secretController,
    required this.autoAcceptThreshold,
    required this.themeProvider,
    required this.onThresholdChanged,
  });

  final SettingsSection section;
  final TextEditingController nameController;
  final TextEditingController emailController;
  final TextEditingController webhookController;
  final TextEditingController secretController;
  final double autoAcceptThreshold;
  final ThemeProvider themeProvider;
  final ValueChanged<double> onThresholdChanged;

  @override
  Widget build(BuildContext context) {
    final child = switch (section) {
      SettingsSection.account => _AccountProfileSection(
          nameController: nameController,
          emailController: emailController,
          themeProvider: themeProvider,
        ),
      SettingsSection.riskEngine => _RiskEngineSection(
          threshold: autoAcceptThreshold,
          onThresholdChanged: onThresholdChanged,
        ),
      SettingsSection.apiConfiguration => _ApiConfigurationSection(
          webhookController: webhookController,
          secretController: secretController,
        ),
    };

    return _FlatBox(child: child);
  }
}


class _AccountProfileSection extends StatelessWidget {
  const _AccountProfileSection({
    required this.nameController,
    required this.emailController,
    required this.themeProvider,
  });

  final TextEditingController nameController;
  final TextEditingController emailController;
  final ThemeProvider themeProvider; 

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    final profileContent = Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            Container(
              width: 58,
              height: 58,
              alignment: Alignment.center,
              decoration: BoxDecoration(
                color: theme.colorScheme.primary.withValues(alpha: 0.12), 
                border: Border.all(color: theme.dividerColor),
                borderRadius: BorderRadius.circular(10),
              ),
              child: Text(
                'RO',
                style: TextStyle(
                  color: theme.colorScheme.primary,
                  fontSize: 18,
                  fontWeight: FontWeight.w800,
                ),
              ),
            ),
            const SizedBox(width: 14),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text('Risk Operations', style: theme.textTheme.titleMedium),
                  const SizedBox(height: 4),
                  Text('Primary workspace administrator',
                      style: theme.textTheme.bodySmall),
                ],
              ),
            ),
          ],
        ),
        const SizedBox(height: 22),
        _ResponsiveFields(
          children: [
            TextField(
              controller: nameController,
              decoration: const InputDecoration(labelText: 'Name'),
            ),
            TextField(
              controller: emailController,
              decoration: const InputDecoration(labelText: 'Email'),
            ),
          ],
        ),
      ],
    );

    return _SectionBody(
      title: 'Account Profile',
      subtitle: 'Operator identity used in audit trails and approvals.',
      children: [
        Stack(
          alignment: Alignment.center,
          children: [
            AbsorbPointer(
              absorbing: true,
              child: ImageFiltered(
                imageFilter: ImageFilter.blur(sigmaX: 3.0, sigmaY: 3.0),
                child: Opacity(
                  opacity: 0.7,
                  child: profileContent,
                ),
              ),
            ),
            // 3. The "Coming Soon" Badge over the blurred content
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 12),
              decoration: BoxDecoration(
                color: theme.colorScheme.surface.withValues(alpha: 0.12),
                borderRadius: BorderRadius.circular(12),
                boxShadow: [
                  BoxShadow(
                    color: Colors.black.withValues(alpha: 0.12),
                    blurRadius: 10,
                    offset: const Offset(0, 4),
                  )
                ],
              ),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Icon(
                    Icons.construction, 
                    size: 32,
                    color: theme.colorScheme.primary,
                  ),
                  const SizedBox(height: 8),
                  Text(
                    'Coming Soon',
                    style: theme.textTheme.titleMedium?.copyWith(
                      fontWeight: FontWeight.bold,
                      color: theme.colorScheme.primary,
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
        
        const SizedBox(height: 18),
        
        SwitchListTile(
          contentPadding: EdgeInsets.zero,
          value: themeProvider.isDarkMode,
          onChanged: (_) => themeProvider.toggleTheme(),
          title: Text('Dark Mode', style: theme.textTheme.titleMedium),
          subtitle: Text(
            'Use the low-glare workspace theme.',
            style: theme.textTheme.bodySmall,
          ),
        ),
      ],
    );
  }
}


class _RiskEngineSection extends StatelessWidget {
  const _RiskEngineSection({
    required this.threshold,
    required this.onThresholdChanged,
  });

  final double threshold;
  final ValueChanged<double> onThresholdChanged;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    final settingsContent = Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            Expanded(
              child: Text(
                'AI Auto-Accept Threshold',
                style: theme.textTheme.titleMedium,
              ),
            ),
            Text(
              '${threshold.round()}%',
              style: theme.textTheme.titleLarge?.copyWith(
                color: theme.colorScheme.primary,
              ),
            ),
          ],
        ),
        const SizedBox(height: 10),
        Slider(
          min: 0,
          max: 100,
          divisions: 100,
          value: threshold,
          label: '${threshold.round()}%',
          onChanged: onThresholdChanged, 
        ),
        const SizedBox(height: 8),
        Text(
          'Recommendations above this confidence level can proceed without manual intervention.',
          style: theme.textTheme.bodySmall,
        ),
        const SizedBox(height: 24),
        _InlineSetting(
          title: 'Human Review Interrupts',
          detail: 'Pause cases with low confidence or incomplete evidence.',
          value: true,
          onChanged: (_) {},
        ),
        _InlineSetting(
          title: 'SLA Breach Alerts',
          detail: 'Notify operators when response windows are at risk.',
          value: true,
          onChanged: (_) {},
        ),
      ],
    );

    return _SectionBody(
      title: 'Risk Engine',
      subtitle: 'Automation policy controls for dispute handling.',
      children: [
        Stack(
          alignment: Alignment.center,
          children: [
            AbsorbPointer(
              absorbing: true,
              child: ImageFiltered(
                imageFilter: ImageFilter.blur(sigmaX: 3.0, sigmaY: 3.0),
                child: Opacity(
                  opacity: 0.7, 
                  child: settingsContent,
                ),
              ),
            ),
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 12),
              decoration: BoxDecoration(
                color: theme.colorScheme.surface.withValues(alpha: 0.12),
                borderRadius: BorderRadius.circular(12),
                boxShadow: [
                  BoxShadow(
                    color: Colors.black.withValues(alpha: 0.12),
                    blurRadius: 10,
                    offset: const Offset(0, 4),
                  )
                ],
              ),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Icon(
                    Icons.construction, // or Icons.handyman / Icons.auto_awesome
                    size: 32,
                    color: theme.colorScheme.primary,
                  ),
                  const SizedBox(height: 8),
                  Text(
                    'Coming Soon',
                    style: theme.textTheme.titleMedium?.copyWith(
                      fontWeight: FontWeight.bold,
                      color: theme.colorScheme.primary,
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ],
    );
  }
}

class _ApiConfigurationSection extends StatelessWidget {
  const _ApiConfigurationSection({
    required this.webhookController,
    required this.secretController,
  });

  final TextEditingController webhookController;
  final TextEditingController secretController;

  @override
  Widget build(BuildContext context) {
    return _SectionBody(
      title: 'API Configuration',
      subtitle: 'Webhook and authentication settings for backend integrations.',
      children: [
        TextField(
          controller: webhookController,
          decoration: const InputDecoration(
            labelText: 'Webhook URL',
            prefixIcon: Icon(Icons.link, size: 18),
          ),
        ),
        const SizedBox(height: 14),
        TextField(
          controller: secretController,
          obscureText: true,
          decoration: const InputDecoration(
            labelText: 'Secret Key',
            prefixIcon: Icon(Icons.lock_outline, size: 18),
          ),
        ),
        const SizedBox(height: 18),
        Align(
          alignment: Alignment.centerLeft,
          child: OutlinedButton.icon(
            onPressed: () {},
            icon: const Icon(Icons.check_circle_outline, size: 18),
            label: const Text('Test Connection'),
          ),
        ),
      ],
    );
  }
}

class _SectionBody extends StatelessWidget {
  const _SectionBody({
    required this.title,
    required this.subtitle,
    required this.children,
  });

  final String title;
  final String subtitle;
  final List<Widget> children;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Text(title, style: theme.textTheme.titleLarge),
        const SizedBox(height: 6),
        Text(subtitle, style: theme.textTheme.bodySmall),
        const SizedBox(height: 24),
        ...children,
      ],
    );
  }
}

class _SettingsNavItem extends StatelessWidget {
  const _SettingsNavItem({
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
          foregroundColor: selected
              ? theme.colorScheme.onSurface
              : theme.textTheme.bodySmall?.color,
          backgroundColor: selected
              ? theme.colorScheme.primary.withValues(alpha: 0.10)
              : null,
          alignment: Alignment.centerLeft,
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 12),
        ),
      ),
    );
  }
}

class _ResponsiveFields extends StatelessWidget {
  const _ResponsiveFields({required this.children});

  final List<Widget> children;

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) {
        if (constraints.maxWidth < 640) {
          return Column(
            children: children
                .map(
                  (child) => Padding(
                    padding: const EdgeInsets.only(bottom: 12),
                    child: child,
                  ),
                )
                .toList(),
          );
        }

        return Row(
          children: children
              .map(
                (child) => Expanded(
                  child: Padding(
                    padding: const EdgeInsets.only(right: 12),
                    child: child,
                  ),
                ),
              )
              .toList(),
        );
      },
    );
  }
}

class _InlineSetting extends StatelessWidget {
  const _InlineSetting({
    required this.title,
    required this.detail,
    required this.value,
    required this.onChanged,
  });

  final String title;
  final String detail;
  final bool value;
  final ValueChanged<bool> onChanged;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Container(
      padding: const EdgeInsets.symmetric(vertical: 14),
      decoration: BoxDecoration(
        border: Border(top: BorderSide(color: theme.dividerColor)),
      ),
      child: Row(
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(title, style: theme.textTheme.titleMedium),
                const SizedBox(height: 3),
                Text(detail, style: theme.textTheme.bodySmall),
              ],
            ),
          ),
          const SizedBox(width: 12),
          Switch(value: value, onChanged: onChanged),
        ],
      ),
    );
  }
}

class _FlatBox extends StatelessWidget {
  const _FlatBox({
    required this.child,
    this.padding = const EdgeInsets.all(22),
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

