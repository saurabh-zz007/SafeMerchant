# Dispute Pipeline — Evaluation Report

Generated: {{ timestamp }}

## Summary

- **Total disputes**: {{ total }}
- **Correct predictions**: {{ correct }}
- **Accuracy**: {{ accuracy }}%

## Confusion Matrix

| Actual \ Predicted | {% for label in labels %}{{ label }} | {% endfor %}
|{% for _ in range(labels|length + 1) %}---|{% endfor %}
{% for gt in labels %}| {{ gt }} | {% for pred in labels %}{{ cm[gt][pred] }} | {% endfor %}
{% endfor %}

## Per-Class Metrics

| Class | Precision | Recall | F1 |
|---|---|---|---|
{% for m in class_metrics %}| {{ m.label }} | {{ "%.2f"|format(m.precision) }} | {{ "%.2f"|format(m.recall) }} | {{ "%.2f"|format(m.f1) }} |
{% endfor %}

## False-Positive Cost Analysis

- **Contested incorrectly**: {{ fpc.contested_incorrectly_count }} cases, ₹{{ fpc.contested_incorrectly_amount }} total
- **Refunded incorrectly**: {{ fpc.refunded_incorrectly_count }} cases, ₹{{ fpc.refunded_incorrectly_amount }} total

## Human Review Queue

| Dispute | Predicted | Ground Truth | Score | Amount | Correct |
|---|---|---|---|---|---|
{% for exc in exceptions %}| {{ exc.dispute_id }} | {{ exc.predicted_action }} | {{ exc.ground_truth }} | {{ exc.winnability_score }}% | ₹{{ exc.amount }} | {{ "✅" if exc.correct else "❌" }} |
{% endfor %}
