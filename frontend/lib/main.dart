import 'package:flutter/material.dart';
import 'package:get/get.dart';

import 'theme/theme_provider.dart';
import 'view_models/dashboard_controller.dart';
import 'views/main_dashboard_layout.dart';

void main() {
  runApp(const SafeMerchantApp());
}

class SafeMerchantApp extends StatefulWidget {
  const SafeMerchantApp({super.key});

  @override
  State<SafeMerchantApp> createState() => _SafeMerchantAppState();
}

class _SafeMerchantAppState extends State<SafeMerchantApp> {
  late final ThemeProvider _themeProvider;
  late final DashboardController _viewModel;

  @override
  void initState() {
    super.initState();
    _themeProvider = Get.put(ThemeProvider());
    _viewModel = Get.put(DashboardController());
  }

  @override
  Widget build(BuildContext context) {
    return GetBuilder<ThemeProvider>(
      init: _themeProvider,
      builder: (themeProvider) {
        return GetMaterialApp(
          debugShowCheckedModeBanner: false,
          title: 'SafeMerchant Dashboard',
          theme: ThemeProvider.lightTheme,
          darkTheme: ThemeProvider.darkTheme,
          themeMode: themeProvider.themeMode,
          home: MainDashboardLayout(
            themeProvider: themeProvider,
            viewModel: _viewModel,
          ),
        );
      },
    );
  }
}
