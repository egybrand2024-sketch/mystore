# Defensive Lift — Version 5.1 Correlation-Aware Risk Engine

## الحالة

**Status: Rejected as replacement / Useful diagnostic research**

هذه النسخة حاولت تقليل الـDrawdown بدون تقليل حجم أفضل فرصة، وذلك بالحفاظ على بنية `v3.2`:

```text
Entry = Frozen Defensive Lift v2
Target = +12%
Stop = -4.5%
Max holding = 7 sessions
Max positions = 2
Nominal slot = 50% of portfolio equity
Round-trip friction assumption = 0.5%
```

ثم إضافة بوابة تمنع فقط **تكديس مخاطرة متشابهة** عندما تكون الصفقة الجديدة مرتبطة تاريخيًا بمركز مفتوح بالفعل.

## الفرضية

الفرضية كانت أن جزءًا مهمًا من الـDrawdown ناتج عن Loss Clustering بين صفقات تتحرك معًا، وبالتالي يمكن تقليل DD بمنع الزوج الثاني المرتبط بدل تصغير كل الصفقات.

## ما تم قياسه قبل الدخول

لكل مرشح جديد مقابل كل مركز مفتوح:

1. Pearson correlation لعوائد الإغلاق اليومية السابقة فقط.
2. Downside overlap: نسبة الجلسات الضاغطة التي هبط فيها السهمان معًا >=1%.
3. لا تستخدم البوابة أي بيانات مستقبلية.
4. عند نقص التاريخ الكافي لا يتم حجب الإشارة تلقائيًا.

## شبكة البحث

تم اختبار **360 تركيبة**:

- Lookback: 20 / 40 / 60 جلسة.
- Correlation threshold: 0.20 / 0.35 / 0.50 / 0.65 / 0.80.
- Downside-overlap threshold: 25% / 40% / 55% / disabled.
- Gate modes: correlation / OR / AND.
- Same-day ranking: liquidity أو fixed signal-quality score.

## شروط النجاح

الاختيار تم باستخدام 2023 و2024 فقط.

```text
Ending wealth >= 97% of frozen v3.2 baseline
AND
Max Drawdown reduction >= 10%
```

في **كل سنة Validation**.

وجدت 3 تركيبات اجتازت هذه الشروط.

## التركيبة المختارة

```text
Lookback = 40 sessions
Correlation threshold = 0.20
Downside overlap threshold = 25%
Gate = correlation OR downside overlap
Same-day ranking = quality
```

## Validation 2023

Baseline v3.2:

```text
Return = +38.78%
Max DD = -6.50%
Trades = 20
```

v5.1:

```text
Return = +35.80%
Max DD = -4.31%
Trades = 18
Correlation-blocked entries = 8
```

الـDD انخفض بحوالي **33.7% نسبيًا**، مع ثروة نهائية ≈97.85% من baseline.

## Validation 2024

Baseline v3.2:

```text
Return = +46.22%
Max DD = -11.17%
Trades = 27
```

v5.1:

```text
Return = +45.97%
Max DD = -8.01%
Trades = 22
Correlation-blocked entries = 6
```

الـDD انخفض بحوالي **28.25% نسبيًا**، مع الحفاظ تقريبًا على كامل Ending Wealth.

## Final Algorithmic Holdout — 2025 to Feb 2026

Baseline v3.2:

```text
Return = +71.01%
Final Equity = 171,006 EGP
Max DD = -6.91%
Trades = 42
Average active-week return = +1.361%
Active weeks >= +2% = 37.21%
```

v5.1:

```text
Return = +66.78%
Final Equity = 166,776.58 EGP
Max DD = -5.95%
Trades = 36
Correlation-blocked entries = 15
Average active-week return = +1.298%
Active weeks >= +2% = 36.59%
```

النتيجة النهائية:

```text
Wealth retained ≈ 97.53% of v3.2
Relative DD reduction ≈ 13.92%
```

إذن النسخة **نجحت فنيًا في خفض DD** مع قص محدود في الثروة النهائية، لكنها لم تتفوق على v3.2 في العائد المطلق، ولذلك لا تستبدلها كـHigh-Return Reference.

## أهم تشخيص خرج من النسخة

الفرضية الأصلية كانت: الأزواج الخاسرة معًا يجب أن تكون أكثر correlation من بقية الأزواج.

البيانات لم تؤكد ذلك بثبات.

### 2023

```text
Overlapping pairs = 8
Both-negative pairs = 1
Avg corr both-negative = -0.040
Avg corr other pairs = +0.182
```

### 2024

```text
Overlapping pairs = 15
Both-negative pairs = 1
Avg corr both-negative = +0.352
Avg corr other pairs = +0.133
```

### Final Holdout

```text
Overlapping pairs = 34
Both-negative pairs = 9
Avg corr both-negative = +0.081
Avg corr other pairs = +0.155
Downside overlap both-negative = 19.36%
Downside overlap other pairs = 17.83%
```

في الـFinal، الأزواج التي خسرت معًا **لم تكن أعلى correlation من بقية الأزواج**. الفرق في downside overlap كان صغيرًا فقط.

هذا يعني أن Loss Clustering حقيقي، لكن **raw price correlation وحده ليس العامل السببي الأقوى**.

## لماذا رفضنا v5.1 كبديل لـv3.2؟

1. حجب 15 إشارة في الـFinal خفض العائد النهائي من +71.01% إلى +66.78%.
2. تحسن DD من -6.91% إلى -5.95% فقط، أي تحسن مهم لكنه ليس كافيًا لتبرير قص الـRight Tail.
3. التشخيص أظهر أن correlation التقليدي لا يميز الأزواج الخاسرة بشكل ثابت.
4. النسخة حسنت Stability أكثر مما حسنت Return/Risk frontier جذريًا.

## الاستنتاج البحثي التالي

الخطوة التالية يجب ألا تستخدم Correlation فقط. المطلوب **Shared Failure Risk Model** يركز على أسباب الفشل المشتركة قبل الدخول، مثل:

- نفس Market impulse / نفس breakout day.
- تشابه Relative Strength deterioration.
- قرب الإشارتين زمنيًا.
- تشابه overextension وbreakout volatility.
- تشابه market breadth / regime at entry.
- تاريخ sector/cluster إذا أمكن اشتقاقه بدون بيانات مستقبلية.
- احتمالية أن تضرب الصفقتان الوقف معًا، وليس مجرد تحرك السعر معًا.

هذا يتحول في الإصدار التالي إلى **Pairwise Failure Probability / Portfolio Risk Clustering** بدل Pearson correlation البسيط.

## الملفات

- `backtest_v51_correlation_risk.py`
- `results_v51_correlation_risk.json`
- `DEFENSIVE_LIFT_V51.md`

## حالة التجميد

**v5.1 = Frozen Rejected Replacement / Diagnostic Reference**

لا يتم تعديل نتائجها لاحقًا. أي تطوير على Shared Failure Risk يحصل على Version جديد.
