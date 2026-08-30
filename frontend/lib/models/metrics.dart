class MetricsSummary {
  const MetricsSummary({
    required this.fromDate,
    required this.toDate,
    required this.totals,
    required this.daily,
  });

  final DateTime fromDate;
  final DateTime toDate;
  final MetricsTotals totals;
  final List<DailySummary> daily;

  factory MetricsSummary.fromJson(Map<String, dynamic> json) {
    return MetricsSummary(
      fromDate: DateTime.tryParse(json['from_date']?.toString() ?? '') ??
          DateTime.now(),
      toDate: DateTime.tryParse(json['to_date']?.toString() ?? '') ??
          DateTime.now(),
      totals: MetricsTotals.fromJson(_readMap(json, 'totals') ?? const {}),
      daily: _readList(json, 'daily')
          .whereType<Map<String, dynamic>>()
          .map(DailySummary.fromJson)
          .toList(),
    );
  }
}

class MetricsTotals {
  const MetricsTotals({
    this.totalDisputes = 0,
    this.won = 0,
    this.lost = 0,
    this.actionRequired = 0,
    this.amountWonPaise = 0,
    this.amountLostPaise = 0,
    this.amountAtRiskPaise = 0,
    this.slaBreached = 0,
    this.winRate,
  });

  final int totalDisputes;
  final int won;
  final int lost;
  final int actionRequired;
  final int amountWonPaise;
  final int amountLostPaise;
  final int amountAtRiskPaise;
  final int slaBreached;
  final double? winRate;

  factory MetricsTotals.fromJson(Map<String, dynamic> json) {
    return MetricsTotals(
      totalDisputes: _readInt(json, 'total_disputes'),
      won: _readInt(json, 'won'),
      lost: _readInt(json, 'lost'),
      actionRequired: _readInt(json, 'action_required'),
      amountWonPaise: _readInt(json, 'amount_won_paise'),
      amountLostPaise: _readInt(json, 'amount_lost_paise'),
      amountAtRiskPaise: _readInt(json, 'amount_at_risk_paise'),
      slaBreached: _readInt(json, 'sla_breached'),
      winRate: _readDouble(json, 'win_rate'),
    );
  }
}

class DailySummary {
  const DailySummary({
    required this.date,
    this.totalDisputes = 0,
    this.won = 0,
    this.lost = 0,
    this.actionRequired = 0,
    this.amountWonPaise = 0,
    this.amountLostPaise = 0,
    this.amountAtRiskPaise = 0,
    this.slaBreached = 0,
  });

  final DateTime date;
  final int totalDisputes;
  final int won;
  final int lost;
  final int actionRequired;
  final int amountWonPaise;
  final int amountLostPaise;
  final int amountAtRiskPaise;
  final int slaBreached;

  factory DailySummary.fromJson(Map<String, dynamic> json) {
    return DailySummary(
      date: DateTime.tryParse(json['date']?.toString() ?? '') ?? DateTime.now(),
      totalDisputes: _readInt(json, 'total_disputes'),
      won: _readInt(json, 'won'),
      lost: _readInt(json, 'lost'),
      actionRequired: _readInt(json, 'action_required'),
      amountWonPaise: _readInt(json, 'amount_won_paise'),
      amountLostPaise: _readInt(json, 'amount_lost_paise'),
      amountAtRiskPaise: _readInt(json, 'amount_at_risk_paise'),
      slaBreached: _readInt(json, 'sla_breached'),
    );
  }
}

class BreakdownGroup {
  const BreakdownGroup({
    required this.by,
    required this.items,
    this.refreshedAt,
  });

  final String by;
  final List<BreakdownItem> items;
  final DateTime? refreshedAt;

  factory BreakdownGroup.fromJson(Map<String, dynamic> json) {
    return BreakdownGroup(
      by: json['by']?.toString() ?? 'unknown',
      items: _readList(json, 'items')
          .whereType<Map<String, dynamic>>()
          .map(BreakdownItem.fromJson)
          .toList(),
      refreshedAt: DateTime.tryParse(json['refreshed_at']?.toString() ?? ''),
    );
  }
}

class BreakdownItem {
  const BreakdownItem({
    required this.dimension,
    required this.value,
    this.count = 0,
    this.amountPaise = 0,
  });

  final String dimension;
  final String value;
  final int count;
  final int amountPaise;

  factory BreakdownItem.fromJson(Map<String, dynamic> json) {
    return BreakdownItem(
      dimension: json['dimension']?.toString() ?? '',
      value: json['dimension_value']?.toString() ?? 'unknown',
      count: _readInt(json, 'count'),
      amountPaise: _readInt(json, 'amount_paise'),
    );
  }
}

class RepeatPattern {
  const RepeatPattern({
    required this.customerEmail,
    required this.disputeIds,
    this.disputeCount = 0,
    this.totalAmountPaise = 0,
  });

  final String customerEmail;
  final List<String> disputeIds;
  final int disputeCount;
  final int totalAmountPaise;

  factory RepeatPattern.fromJson(Map<String, dynamic> json) {
    return RepeatPattern(
      customerEmail: json['customer_email']?.toString() ?? 'unknown',
      disputeCount: _readInt(json, 'dispute_count'),
      totalAmountPaise: _readInt(json, 'total_amount_paise'),
      disputeIds:
          _readList(json, 'dispute_ids').map((id) => id.toString()).toList(),
    );
  }
}

class AuditEntry {
  const AuditEntry({
    required this.id,
    required this.disputeId,
    required this.field,
    required this.changedBy,
    required this.changedAt,
    this.oldValue,
    this.newValue,
    this.note,
  });

  final int id;
  final String disputeId;
  final String field;
  final String changedBy;
  final DateTime changedAt;
  final String? oldValue;
  final String? newValue;
  final String? note;

  factory AuditEntry.fromJson(Map<String, dynamic> json) {
    return AuditEntry(
      id: _readInt(json, 'id'),
      disputeId: json['dispute_id']?.toString() ?? '',
      field: json['field']?.toString() ?? '',
      oldValue: json['old_value']?.toString(),
      newValue: json['new_value']?.toString(),
      changedBy: json['changed_by']?.toString() ?? 'user',
      changedAt: DateTime.tryParse(json['changed_at']?.toString() ?? '') ??
          DateTime.now(),
      note: json['note']?.toString(),
    );
  }
}

Map<String, dynamic>? _readMap(Map<String, dynamic> source, String key) {
  final value = source[key];
  return value is Map<String, dynamic> ? value : null;
}

List<dynamic> _readList(Map<String, dynamic> source, String key) {
  final value = source[key];
  return value is List<dynamic> ? value : const [];
}

int _readInt(Map<String, dynamic> source, String key) {
  final value = source[key];
  if (value is int) {
    return value;
  }
  if (value is num) {
    return value.round();
  }
  return int.tryParse(value?.toString() ?? '') ?? 0;
}

double? _readDouble(Map<String, dynamic> source, String key) {
  final value = source[key];
  if (value is num) {
    return value.toDouble();
  }
  return double.tryParse(value?.toString() ?? '');
}
