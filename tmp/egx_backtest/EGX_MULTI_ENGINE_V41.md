# EGX Multi-Engine Quality Gate — Version 4.1 (Rejected)

## الحالة

**Status: Rejected Research Version**

## الهدف

إصلاح مشكلة v4.0 عن طريق تشديد جودة BRT وPBC واستبعاد FBR، ثم اختبار DLP وحده أو مع المحركات الثانوية بدل إجبار جميع المحركات على العمل معًا.

## شروط القبول

- Validation: 2023 و2024.
- Final Holdout: 2025–Feb 2026 لم يستخدم في الاختيار.
- Minimum CAGR في كل سنة Validation: 30%.
- Max Drawdown في كل سنة Validation: 8%.
- تم اختبار 1,152 تركيبة Portfolio/Subset.

## نتيجة Quality Gate للمحركات

### DLP
ظل الأقوى والأكثر ثباتًا.

### BRT المشدد
تحسن 2023، لكنه تراجع في 2024 وأصبح متوسط عائده في الـFinal قريبًا من الصفر:

```text
Final Avg Gross ≈ -0.015%
```

### PBC المشدد
بقي موجبًا قليلًا في 2023/2024 لكنه أصبح سلبيًا في الـFinal:

```text
Final Avg Gross ≈ -0.404%
```

## نتيجة المحفظة

```text
Configurations tested = 1,152
Eligible = 0
```

لا توجد تركيبة جمعت CAGR >=30% وDrawdown <=8% في السنتين معًا.

## الاستنتاج

زيادة عدد الـSetup Families لم تحقق المطلوب. المشكلة ليست نقص الصفقات فقط؛ المحركات الثانوية لا تملك Edge ثابتًا بما يكفي في التعريفات الحالية، وإضافتها تقلل جودة المحفظة.

## القرار

العودة إلى DLP باعتباره Core Alpha Engine، وتغيير مكان إدارة الخطر من **Trade Level** إلى **Market-Regime Level**.

`v4.2` سيختبر فكرة مختلفة: الاحتفاظ بحجم v3.2 الكامل عندما تكون بيئة السوق مواتية، وتقليل/إيقاف التعرض فقط في الأنظمة السوقية الضعيفة. الهدف هو تقليل Drawdown بدون قص أرباح الصفقات الجيدة أو إضافة إشارات ضعيفة.

## الملفات

- `backtest_v41_quality_gate.py`
- `results_v41_quality_gate.json`
- `EGX_MULTI_ENGINE_V41.md`
