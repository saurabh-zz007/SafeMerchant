import 'package:flutter/material.dart';

class ThemeProvider extends ChangeNotifier {
  ThemeMode _themeMode = ThemeMode.light;

  ThemeMode get themeMode => _themeMode;
  bool get isDarkMode => _themeMode == ThemeMode.dark;

  void toggleTheme() {
    _themeMode = isDarkMode ? ThemeMode.light : ThemeMode.dark;
    notifyListeners();
  }

  void setThemeMode(ThemeMode mode) {
    if (_themeMode == mode) {
      return;
    }
    _themeMode = mode;
    notifyListeners();
  }

  static ThemeData get lightTheme {
    const background = Color(0xFFF7F8FA);
    const surface = Color(0xFFFFFFFF);
    const mutedSurface = Color(0xFFF2F4F7);
    const border = Color(0xFFE3E7ED);
    const text = Color(0xFF111827);
    const mutedText = Color(0xFF667085);
    const primary = Color(0xFF2563EB);

    return _buildTheme(
      brightness: Brightness.light,
      background: background,
      surface: surface,
      mutedSurface: mutedSurface,
      border: border,
      text: text,
      mutedText: mutedText,
      primary: primary,
    );
  }

  static ThemeData get darkTheme {
    const background = Color(0xFF111315);
    const surface = Color(0xFF171A1D);
    const mutedSurface = Color(0xFF1F2328);
    const border = Color(0xFF2C3138);
    const text = Color(0xFFF3F5F7);
    const mutedText = Color(0xFFA6ADB7);
    const primary = Color(0xFF7AA2F7);

    return _buildTheme(
      brightness: Brightness.dark,
      background: background,
      surface: surface,
      mutedSurface: mutedSurface,
      border: border,
      text: text,
      mutedText: mutedText,
      primary: primary,
    );
  }

  static ThemeData _buildTheme({
    required Brightness brightness,
    required Color background,
    required Color surface,
    required Color mutedSurface,
    required Color border,
    required Color text,
    required Color mutedText,
    required Color primary,
  }) {
    final base = ThemeData(
      brightness: brightness,
      useMaterial3: true,
      fontFamily: 'Segoe UI',
      scaffoldBackgroundColor: background,
      dividerColor: border,
      colorScheme: ColorScheme(
        brightness: brightness,
        primary: primary,
        onPrimary: brightness == Brightness.dark ? Colors.black : Colors.white,
        secondary: mutedText,
        onSecondary: surface,
        error: const Color(0xFFDC2626),
        onError: Colors.white,
        surface: surface,
        onSurface: text,
      ),
    );

    return base.copyWith(
      appBarTheme: AppBarTheme(
        elevation: 0,
        scrolledUnderElevation: 0,
        backgroundColor: surface,
        foregroundColor: text,
        surfaceTintColor: Colors.transparent,
        titleTextStyle: TextStyle(
          color: text,
          fontSize: 15,
          fontWeight: FontWeight.w700,
        ),
      ),
      chipTheme: base.chipTheme.copyWith(
        backgroundColor: mutedSurface,
        selectedColor: primary.withValues(alpha: 0.12),
        side: BorderSide(color: border),
        labelStyle: TextStyle(color: text, fontSize: 12),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(6)),
      ),
      dividerTheme: DividerThemeData(color: border, thickness: 1, space: 1),
      filledButtonTheme: FilledButtonThemeData(
        style: FilledButton.styleFrom(
          elevation: 0,
          shadowColor: Colors.transparent,
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(6)),
          textStyle: const TextStyle(fontWeight: FontWeight.w600),
        ),
      ),
      iconButtonTheme: IconButtonThemeData(
        style: IconButton.styleFrom(
          elevation: 0,
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(6)),
        ),
      ),
      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: mutedSurface,
        isDense: true,
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(6),
          borderSide: BorderSide(color: border),
        ),
        enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(6),
          borderSide: BorderSide(color: border),
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(6),
          borderSide: BorderSide(color: primary),
        ),
        labelStyle: TextStyle(color: mutedText),
        hintStyle: TextStyle(color: mutedText),
      ),
      outlinedButtonTheme: OutlinedButtonThemeData(
        style: OutlinedButton.styleFrom(
          elevation: 0,
          side: BorderSide(color: border),
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(6)),
          foregroundColor: text,
        ),
      ),
      sliderTheme: SliderThemeData(
        activeTrackColor: primary,
        inactiveTrackColor: border,
        thumbColor: primary,
        overlayColor: primary.withValues(alpha: 0.12),
      ),
      textButtonTheme: TextButtonThemeData(
        style: TextButton.styleFrom(
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(6)),
          foregroundColor: primary,
        ),
      ),
      textTheme: base.textTheme
          .apply(
            bodyColor: text,
            displayColor: text,
          )
          .copyWith(
            headlineSmall: TextStyle(
              color: text,
              fontSize: 22,
              fontWeight: FontWeight.w700,
              height: 1.2,
            ),
            titleLarge: TextStyle(
              color: text,
              fontSize: 18,
              fontWeight: FontWeight.w700,
              height: 1.25,
            ),
            titleMedium: TextStyle(
              color: text,
              fontSize: 15,
              fontWeight: FontWeight.w700,
              height: 1.25,
            ),
            bodyMedium: TextStyle(color: text, fontSize: 13, height: 1.45),
            bodySmall: TextStyle(color: mutedText, fontSize: 12, height: 1.4),
            labelMedium: TextStyle(
              color: mutedText,
              fontSize: 12,
              fontWeight: FontWeight.w600,
            ),
          ),
    );
  }
}
