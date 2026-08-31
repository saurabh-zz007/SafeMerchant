import 'package:flutter_test/flutter_test.dart';
import 'package:get/get.dart';
import 'package:safemerchant_frontend/theme/theme_provider.dart';
import 'package:safemerchant_frontend/view_models/dashboard_controller.dart';
import 'package:safemerchant_frontend/views/main_dashboard_layout.dart';

void main() {
  testWidgets('renders main dashboard layout', (tester) async {
    final themeProvider = Get.put(ThemeProvider());
    final viewModel = Get.put(DashboardController(autoStart: false));

    await tester.pumpWidget(
      GetMaterialApp(
        home: MainDashboardLayout(
          viewModel: viewModel,
          themeProvider: themeProvider,
        ),
      ),
    );

    expect(find.text('SafeMerchant'), findsOneWidget);
    expect(find.text('Overview'), findsWidgets);
    expect(find.text('Disputes'), findsWidgets);
    expect(find.text('Analytics'), findsWidgets);
    expect(find.text('Settings'), findsWidgets);
  });
}
