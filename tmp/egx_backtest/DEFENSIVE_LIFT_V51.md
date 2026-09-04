# Defensive Lift — Version 5.1 Correlation-Aware Risk Engine

## الحالة

**Status: Research in progress**

هذه النسخة لا تقلل حجم أفضل فرصة بشكل عشوائي. الهدف هو الحفاظ على بنية `v3.2` عالية العائد:

```text
Entry = Frozen Defensive Lift v2
Target = +12%
Stop = -4.5%
Max holding = 7 sessions
Max positions = 2
Nominal slot = 50% of portfolio equity
```

ثم إضافة بوابة مخاطرة جديدة تمنع فقط **تكديس مخاطرة متشابهة** عندما تكون الصفقة الجديدة مرتبطة تاريخيًا بصفقة مفتوحة بالفعل.

## الفرضية

جزء من الـDrawdown قد يكون ناتجًا عن Loss Clustering وليس عن سوء متوسط الصفقة. إذا كانت صفقتان تتحركان معًا قبل الدخول، فإن تخصيص 50% + 50% لهما قد يكون في الواقع رهانًا واحدًا مضاعفًا.

## ما يتم قياسه قبل الدخول

لكل مرشح جديد مقابل كل مركز مفتوح:

1. Pearson correlation لعوائد الإغلاق اليومية السابقة فقط.
2. Downside overlap: نسبة الجلسات الضاغطة التي هبط فيها السهمان معًا >=1%.
3. لا يتم استخدام أي بيانات مستقبلية في قرار البوابة.
4. عند نقص التاريخ الكافي لا يتم حجب الإشارة تلقائيًا.

## شبكة البحث

- Lookback: 20 / 40 / 60 جلسة.
- Correlation threshold: 0.20 / 0.35 / 0.50 / 0.65 / 0.80.
- Downside-overlap threshold: 25% / 40% / 55% / disabled.
- Gate modes:
  - correlation only
  - correlation OR downside overlap
  - correlation AND downside overlap
- Same-day candidate ranking:
  - historical median base traded value
  - fixed contemporaneous signal-quality score

## شروط النجاح

يتم الاختيار باستخدام 2023 و2024 فقط.

لكي تصبح التركيبة مرشحًا يجب أن تحقق في **كل سنة Validation**:

```text
Ending wealth >= 97% of frozen v3.2 baseline
AND
Max Drawdown reduction >= 10%
```

ثم فقط يتم فتح فترة 2025–Feb 2026 كتقييم نهائي Algorithmic Holdout.

## تشخيص إضافي

النسخة تقيس أيضًا ارتباط الأزواج التي كانت مفتوحة معًا في v3.2، وتقارن:

- متوسط correlation للأزواج التي انتهت بخسارتين.
- متوسط correlation لباقي الأزواج.
- Downside overlap لنفس المجموعتين.

هذا الاختبار مهم لأنه يستطيع **رفض الفرضية نفسها** إذا لم تكن الخسائر المتجمعة مرتبطة أكثر من الصفقات الأخرى.

## قاعدة القرار

- إذا خفّضت البوابة DD بدون قص أكثر من 3% من Ending Wealth في كل سنة Validation، نختبرها على الـFinal.
- إذا فشلت، يتم توثيقها كـRejected ولا يتم تخفيف الشروط بعد رؤية الـFinal.
- لا يتم تعديل أي وثيقة إصدار سابق.

## الملفات

- `backtest_v51_correlation_risk.py`
- `results_v51_correlation_risk.json` بعد اكتمال الاختبار
- `DEFENSIVE_LIFT_V51.md`
