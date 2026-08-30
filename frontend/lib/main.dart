import 'package:flutter/material.dart';

import 'theme/theme_provider.dart';
import 'view_models/dashboard_view_model.dart';
import 'views/main_dashboard_layout.dart';

const apiBaseUrl = String.fromEnvironment(
  'API_BASE_URL',
  defaultValue: 'http://localhost:8000',
);

const websocketUrl = String.fromEnvironment(
  'WEBSOCKET_URL',
  defaultValue: 'ws://localhost:8000/ws/dashboard',
);

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
  late final DashboardViewModel _viewModel;

  @override
  void initState() {
    super.initState();
    _themeProvider = ThemeProvider();
    _viewModel = DashboardViewModel(
      apiBaseUrl: apiBaseUrl,
      websocketUrl: websocketUrl,
    );
  }

  @override
  void dispose() {
    _themeProvider.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: _themeProvider,
      builder: (context, _) {
        return MaterialApp(
          debugShowCheckedModeBanner: false,
          title: 'SafeMerchant Dashboard',
          theme: ThemeProvider.lightTheme,
          darkTheme: ThemeProvider.darkTheme,
          themeMode: _themeProvider.themeMode,
          home: MainDashboardLayout(
            themeProvider: _themeProvider,
            viewModel: _viewModel,
          ),
        );
      },
    );
  }
}
