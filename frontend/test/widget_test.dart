import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:get/get.dart';

import 'package:safemerchant_frontend/theme/theme_provider.dart';
import 'package:safemerchant_frontend/view_models/dashboard_controller.dart';
import 'package:safemerchant_frontend/views/developer_options_screen.dart';
import 'package:safemerchant_frontend/views/main_dashboard_layout.dart';
import 'package:safemerchant_frontend/views/settings_screen.dart';

void main() {
  testWidgets('renders main dashboard layout and developer options entry', (tester) async {
    await tester.binding.setSurfaceSize(const Size(1400, 900));
    final themeProvider = Get.put(ThemeProvider());
    final viewModel = Get.put(DashboardController(autoStart: false));

    await tester.pumpWidget(
      GetMaterialApp(
        home: MainDashboardLayout(
          themeProvider: themeProvider,
          viewModel: viewModel,
        ),
      ),
    );
    await tester.pumpAndSettle();

    // Verify main navigation bar displays Developer Options item
    expect(find.text('Developer Options'), findsOneWidget);
    expect(find.byIcon(Icons.terminal_outlined), findsOneWidget);
  });

  testWidgets('settings screen does not contain Server Settings tab', (tester) async {
    await tester.binding.setSurfaceSize(const Size(1400, 900));
    final themeProvider = Get.put(ThemeProvider());
    final viewModel = Get.put(DashboardController(autoStart: false));

    await tester.pumpWidget(
      GetMaterialApp(
        home: Scaffold(
          body: SettingsScreen(
            themeProvider: themeProvider,
            dashboardController: viewModel,
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    // Verify old Server Settings tab is NOT in SettingsScreen
    expect(find.text('Server Settings'), findsNothing);
    expect(find.text('Backend Server URL'), findsNothing);
  });

  testWidgets('gatekeeper modal prompts for admin and unlocks developer options', (tester) async {
    await tester.binding.setSurfaceSize(const Size(1400, 900));
    final themeProvider = Get.put(ThemeProvider());
    final viewModel = Get.put(DashboardController(autoStart: false));

    await tester.pumpWidget(
      GetMaterialApp(
        home: MainDashboardLayout(
          themeProvider: themeProvider,
          viewModel: viewModel,
        ),
      ),
    );
    await tester.pumpAndSettle();

    // Tap on Developer Options in the sidebar
    await tester.tap(find.text('Developer Options'));
    await tester.pumpAndSettle();

    // Gatekeeper modal should pop up
    expect(find.text('Developer Options Access'), findsOneWidget);
    expect(find.text('Enter Developer Section'), findsOneWidget);

    // Enter incorrect password
    await tester.enterText(find.byType(TextField).last, 'wrong_pass');
    await tester.tap(find.text('Enter Developer Section'));
    await tester.pumpAndSettle();

    // Still in modal with error
    expect(find.text('Incorrect passkey. Please type "admin" to enter.'), findsOneWidget);

    // Enter 'admin'
    await tester.enterText(find.byType(TextField).last, 'admin');
    await tester.tap(find.text('Enter Developer Section'));
    await tester.pumpAndSettle();

    // Modal closed and Developer Options screen active
    expect(find.text('Developer Options Access'), findsNothing);
    expect(find.text('Create Test Dispute (Guided Scenario Builder)'), findsOneWidget);
    expect(find.text('Backend Environment'), findsOneWidget);
    expect(find.text('Database & Storage Administration'), findsOneWidget);
  });

  testWidgets('guided scenario builder renders all constrained form fields and presets', (tester) async {
    await tester.binding.setSurfaceSize(const Size(1400, 1200));
    final themeProvider = Get.put(ThemeProvider());
    final viewModel = Get.put(DashboardController(autoStart: false));

    await tester.pumpWidget(
      GetMaterialApp(
        home: Scaffold(
          body: DeveloperOptionsScreen(
            viewModel: viewModel,
            themeProvider: themeProvider,
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    // Check header and guided scenario form components
    expect(find.text('Create Test Dispute (Guided Scenario Builder)'), findsOneWidget);
    expect(find.text('Quick Scenarios:'), findsOneWidget);
    expect(find.text('Friendly Fraud Win (₹3,499)'), findsOneWidget);
    expect(find.text('Lost in Transit Refund (₹2,999)'), findsOneWidget);
    expect(find.text('High-Value Ambiguous (₹24,999)'), findsOneWidget);
    expect(find.text('Weak Defense / Loss (₹1,299)'), findsOneWidget);

    // Check form field labels
    expect(find.text('Disputed Amount (INR)'), findsOneWidget);
    expect(find.text('Item Description'), findsOneWidget);
    expect(find.text('Delivery Status'), findsOneWidget);
    expect(find.text('Customer Communication'), findsOneWidget);
    expect(find.text('2FA / OTP Verified'), findsOneWidget);
    expect(find.text('Account Age (Days)'), findsOneWidget);
    expect(find.text('Razorpay Reason Code'), findsOneWidget);
    expect(find.text('Create & Dispatch Test Dispute'), findsOneWidget);

    // Tap a preset chip
    await tester.tap(find.text('Friendly Fraud Win (₹3,499)'));
    await tester.pumpAndSettle();

    // Verify fields updated
    expect(find.text('3499'), findsOneWidget);
    expect(find.text('Nike Running Shoes - Size 9'), findsOneWidget);
  });

  testWidgets('idle reset button shows standard confirmation dialog', (tester) async {
    await tester.binding.setSurfaceSize(const Size(1400, 1200));
    final themeProvider = Get.put(ThemeProvider());
    final viewModel = Get.put(DashboardController(autoStart: false));

    await tester.pumpWidget(
      GetMaterialApp(
        home: Scaffold(
          body: DeveloperOptionsScreen(
            viewModel: viewModel,
            themeProvider: themeProvider,
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    // Ensure visible then click Reset System Database
    final resetBtn = find.text('Reset System Database');
    await tester.ensureVisible(resetBtn);
    await tester.tap(resetBtn);
    await tester.pumpAndSettle();

    // Standard confirmation dialog should show
    expect(find.text('Confirm System Reset'), findsOneWidget);
    expect(find.text('Reset Everything'), findsOneWidget);

    // Cancel
    await tester.tap(find.text('Cancel'));
    await tester.pumpAndSettle();
    expect(find.text('Confirm System Reset'), findsNothing);
  });

  testWidgets('force reset urgent dialog requires typing CONFIRM before enabling action', (tester) async {
    await tester.binding.setSurfaceSize(const Size(1400, 900));
    final viewModel = Get.put(DashboardController(autoStart: false));

    await tester.pumpWidget(
      GetMaterialApp(
        home: Scaffold(
          body: Builder(
            builder: (context) => ElevatedButton(
              onPressed: () {
                showDialog<void>(
                  context: context,
                  builder: (_) => ForceResetUrgentDialog(controller: viewModel),
                );
              },
              child: const Text('Open Force Modal'),
            ),
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    await tester.tap(find.text('Open Force Modal'));
    await tester.pumpAndSettle();

    expect(find.text('Warning: Active Processing'), findsOneWidget);
    expect(
      find.text('Warning: A dispute is currently processing. Resetting the database will force-terminate this operation.'),
      findsOneWidget,
    );

    // Find the Reset button inside dialog - it should be disabled initially
    final filledButtonFinder = find.ancestor(
      of: find.text('Force Reset Everything'),
      matching: find.byWidgetPredicate((w) => w is ButtonStyleButton),
    );
    expect(filledButtonFinder, findsOneWidget);
    final filledButton = tester.widget<ButtonStyleButton>(filledButtonFinder);
    expect(filledButton.onPressed, isNull);

    // Type partial string
    await tester.enterText(find.byType(TextField).last, 'CONF');
    await tester.pumpAndSettle();

    final filledButtonAfterPartial = tester.widget<ButtonStyleButton>(filledButtonFinder);
    expect(filledButtonAfterPartial.onPressed, isNull);

    // Type 'CONFIRM'
    await tester.enterText(find.byType(TextField).last, 'CONFIRM');
    await tester.pumpAndSettle();

    final filledButtonAfterConfirm = tester.widget<ButtonStyleButton>(filledButtonFinder);
    expect(filledButtonAfterConfirm.onPressed, isNotNull);
  });

  testWidgets('conditional customer communication logic adjusts selections and respects constraints', (tester) async {
    await tester.binding.setSurfaceSize(const Size(1400, 1200));
    final themeProvider = Get.put(ThemeProvider());
    final viewModel = Get.put(DashboardController(autoStart: false));

    await tester.pumpWidget(
      GetMaterialApp(
        home: Scaffold(
          body: DeveloperOptionsScreen(
            viewModel: viewModel,
            themeProvider: themeProvider,
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    // Default: Delivered (Signed) and Customer confirms receipt
    expect(find.text('Delivered (Signed)'), findsOneWidget);
    expect(find.text('Customer confirms receipt'), findsOneWidget);

    // Switch Delivery Status to "Lost in Transit"
    await tester.tap(find.text('Delivered (Signed)'));
    await tester.pumpAndSettle();

    // In the opened delivery dropdown, select "Lost in Transit"
    await tester.tap(find.text('Lost in Transit').last);
    await tester.pumpAndSettle();

    // Customer communication should have auto-switched away from "Customer confirms receipt" to "Customer disputes receipt"
    expect(find.text('Customer disputes receipt'), findsOneWidget);

    // Switch Delivery Status to "In Transit"
    await tester.tap(find.text('Lost in Transit'));
    await tester.pumpAndSettle();

    await tester.tap(find.text('In Transit').last);
    await tester.pumpAndSettle();

    // Customer communication should auto-switch to "No communication on file"
    expect(find.text('No communication on file'), findsOneWidget);
  });
}
