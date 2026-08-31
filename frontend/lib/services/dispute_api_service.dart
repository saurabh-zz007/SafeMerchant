import 'dart:convert';
import 'dart:io';

import '../models/dispute.dart';
import '../models/metrics.dart';

class DisputeApiService {
  DisputeApiService({HttpClient? client}) : _client = client ?? HttpClient();

  final HttpClient _client;

  Future<List<Dispute>> fetchDisputes(String baseUrl) async {
    final decoded = await _getJson(Uri.parse('$baseUrl/api/v1/disputes'));
    final items = switch (decoded) {
      List<dynamic> list => list,
      Map<String, dynamic> map when map['disputes'] is List => map['disputes'],
      Map<String, dynamic> map when map['items'] is List => map['items'],
      Map<String, dynamic> map when map['data'] is List => map['data'],
      _ => const <dynamic>[],
    };

    return items
        .whereType<Map<String, dynamic>>()
        .map<Dispute>((json) => Dispute.fromJson(json))
        .toList();
  }

  Future<Dispute> fetchDispute(String baseUrl, String disputeId) async {
    final encodedId = Uri.encodeComponent(disputeId);
    final decoded = await _getJson(Uri.parse('$baseUrl/api/v1/disputes/$encodedId'));
    if (decoded is Map<String, dynamic>) {
      return Dispute.fromJson(decoded);
    }
    throw const HttpException('Failed to parse dispute detail response');
  }

  Future<String?> fetchEvidencePdfUrl({
    required String baseUrl,
    required String disputeId,
  }) async {
    final encodedId = Uri.encodeComponent(disputeId);
    try {
      final decoded = await _getJson(
        Uri.parse('$baseUrl/api/v1/disputes/$encodedId/evidence-url'),
      );
      if (decoded is Map<String, dynamic>) {
        return decoded['signed_url']?.toString();
      }
    } catch (_) {
      return null;
    }
    return null;
  }

  Future<Map<String, dynamic>> retryEvidenceJob({
    required String baseUrl,
    required String disputeId,
  }) async {
    final encodedId = Uri.encodeComponent(disputeId);
    final request = await _client.postUrl(
      Uri.parse('$baseUrl/api/v1/disputes/$encodedId/retry-evidence'),
    );
    final response = await request.close();
    final body = await response.transform(utf8.decoder).join();
    _ensureSuccess(response.statusCode, body);
    if (body.trim().isEmpty) {
      return const {};
    }
    final decoded = jsonDecode(body);
    return decoded is Map<String, dynamic> ? decoded : const {};
  }

  Future<Map<String, dynamic>> fetchHealth(String baseUrl) async {
    final decoded = await _getJson(Uri.parse('$baseUrl/api/v1/health'));
    return decoded is Map<String, dynamic> ? decoded : const {};
  }

  Future<MetricsSummary> fetchMetricsSummary({
    required String baseUrl,
    required DateTime from,
    required DateTime to,
  }) async {
    final uri = Uri.parse('$baseUrl/api/v1/metrics/summary').replace(
      queryParameters: {
        'from': _dateOnly(from),
        'to': _dateOnly(to),
      },
    );
    final decoded = await _getJson(uri);
    return MetricsSummary.fromJson(
      decoded is Map<String, dynamic> ? decoded : const {},
    );
  }

  Future<BreakdownGroup> fetchBreakdown({
    required String baseUrl,
    required String by,
  }) async {
    final uri = Uri.parse('$baseUrl/api/v1/metrics/breakdown').replace(
      queryParameters: {'by': by},
    );
    final decoded = await _getJson(uri);
    return BreakdownGroup.fromJson(
      decoded is Map<String, dynamic> ? decoded : const {},
    );
  }

  Future<List<RepeatPattern>> fetchRepeatPatterns({
    required String baseUrl,
    int minCount = 2,
  }) async {
    final uri = Uri.parse('$baseUrl/api/v1/metrics/repeat-patterns').replace(
      queryParameters: {'min_count': minCount.toString()},
    );
    final decoded = await _getJson(uri);
    final patterns =
        decoded is Map<String, dynamic> && decoded['patterns'] is List
            ? decoded['patterns'] as List<dynamic>
            : const <dynamic>[];
    return patterns
        .whereType<Map<String, dynamic>>()
        .map(RepeatPattern.fromJson)
        .toList();
  }

  Future<List<AuditEntry>> fetchAudit({
    required String baseUrl,
    required String disputeId,
  }) async {
    final encodedId = Uri.encodeComponent(disputeId);
    final decoded =
        await _getJson(Uri.parse('$baseUrl/api/v1/disputes/$encodedId/audit'));
    final entries =
        decoded is Map<String, dynamic> && decoded['entries'] is List
            ? decoded['entries'] as List<dynamic>
            : const <dynamic>[];
    return entries
        .whereType<Map<String, dynamic>>()
        .map(AuditEntry.fromJson)
        .toList();
  }

  Future<Map<String, dynamic>> submitReview({
    required String baseUrl,
    required String disputeId,
    required String action,
    String reason = '',
  }) async {
    final encodedId = Uri.encodeComponent(disputeId);
    final request = await _client.postUrl(
      Uri.parse('$baseUrl/api/v1/disputes/$encodedId/review'),
    );
    request.headers.contentType = ContentType.json;
    request.write(jsonEncode({'action': action, 'reason': reason}));

    final response = await request.close();
    final body = await response.transform(utf8.decoder).join();
    _ensureSuccess(response.statusCode, body);

    if (body.trim().isEmpty) {
      return const {};
    }
    final decoded = jsonDecode(body);
    return decoded is Map<String, dynamic> ? decoded : const {};
  }

  Future<Map<String, dynamic>> patchDispute({
    required String baseUrl,
    required String disputeId,
    String? status,
    int? amountPaise,
    String? reasonCode,
    String? outcome,
    String? note,
  }) async {
    final encodedId = Uri.encodeComponent(disputeId);
    final request = await _client.patchUrl(
      Uri.parse('$baseUrl/api/v1/disputes/$encodedId'),
    );
    request.headers.contentType = ContentType.json;
    request.write(jsonEncode({
      if (status != null) 'status': status,
      if (amountPaise != null) 'amount_paise': amountPaise,
      if (reasonCode != null) 'reason_code': reasonCode,
      if (outcome != null) 'outcome': outcome,
      if (note != null) 'note': note,
    }));

    final response = await request.close();
    final body = await response.transform(utf8.decoder).join();
    _ensureSuccess(response.statusCode, body);

    if (body.trim().isEmpty) {
      return const {};
    }
    final decoded = jsonDecode(body);
    return decoded is Map<String, dynamic> ? decoded : const {};
  }

  Future<Map<String, dynamic>> resetDatabase(String baseUrl) async {
    final request = await _client.deleteUrl(
      Uri.parse('$baseUrl/api/v1/admin/reset'),
    );
    final response = await request.close();
    final body = await response.transform(utf8.decoder).join();
    _ensureSuccess(response.statusCode, body);

    if (body.trim().isEmpty) {
      return const {};
    }
    final decoded = jsonDecode(body);
    return decoded is Map<String, dynamic> ? decoded : const {};
  }

  void close() {
    _client.close(force: true);
  }

  void _ensureSuccess(int statusCode, String body) {
    if (statusCode >= 200 && statusCode < 300) {
      return;
    }
    throw HttpException(
      'Backend returned HTTP $statusCode${body.isEmpty ? '' : ': $body'}',
    );
  }

  Future<dynamic> _getJson(Uri uri) async {
    final request = await _client.getUrl(uri);
    final response = await request.close();
    final body = await response.transform(utf8.decoder).join();

    _ensureSuccess(response.statusCode, body);
    if (body.trim().isEmpty) {
      return null;
    }
    return jsonDecode(body);
  }

  String _dateOnly(DateTime value) {
    return '${value.year.toString().padLeft(4, '0')}-'
        '${value.month.toString().padLeft(2, '0')}-'
        '${value.day.toString().padLeft(2, '0')}';
  }
}
