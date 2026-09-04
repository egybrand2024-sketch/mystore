# Defensive Lift Pattern — Version 3.0 Candidate

> نسخة بحثية موسعة مبنية فوق `Defensive Lift v2` بهدف رفع **جودة الاستراتيجية ككل** بنسبة لا تقل عن 30%، مع الفصل بوضوح بين تحسين **Win Rate** وتحسين **Expected Return**.

## 1. الحالة

**Status: Candidate / Research validated on historical holdout**

النسخة الثالثة لا تدعي أن معدل النجاح نفسه تحسن 30%. الاختبارات الموسعة أثبتت أن رفع Win Rate من 43.55% إلى 56.61% بصورة ثابتة لم يتحقق على العينة الحالية دون الوقوع في Overfitting.

لكن تم تحقيق تحسن أكبر من 30% في **متوسط العائد المحقق لكل صفقة** عن طريق تحسين إدارة الصفقة مع إبقاء شروط دخول v2 ثابتة.

---

## 2. نقطة الانطلاق — v2

تعتمد v3 على إشارات `Defensive Lift v2` كما هي دون تعديل:

- Base من 5 إلى 15 جلسة.
- Defensive Lift بين 3% و8%.
- Higher Low داخل القاعدة.
- نشاط حجم قبل الاختراق.
- Base Range <= 8%.
- جسم شمعة الاختراق >= 2%.
- CLV >= 0.55.
- ارتفاع يوم الاختراق <= 6%.
- Breakout Volume >= 2.0 × Median Volume للقاعدة.
- Pre-20-session return >= -3%.
- Compression Ratio <= 1.25.

إدارة الصفقة الأصلية في v2:

```text
Target  = +8%
Stop    = -4%
Horizon = 10 جلسات
```

---

## 3. Benchmark النهائي لـ v2

الفترة النهائية التي لم تُستخدم في اختيار شروط v2:

```text
2025-01-01 → 2026-02-28
```

النتيجة:

```text
62 صفقة
27 Target
22 Stop
13 Timeout
Win Rate = 43.55%
Average realized return/trade = +2.213%
Median realized return/trade  = +1.288%
```

هذه هي نقطة المقارنة الأساسية لـ v3.

---

## 4. هدف التطوير

تم تفسير طلب تحسين الاستراتيجية 30% بطريقتين منفصلتين:

### 4.1 تحسين Win Rate بنسبة 30% نسبيًا

بما أن v2 حققت:

```text
43.55%
```

فإن هدف +30% نسبي يعني:

```text
43.55% × 1.30 = 56.61%
```

### 4.2 تحسين Expected / Average Realized Return بنسبة 30% نسبيًا

Baseline:

```text
+2.213% متوسط عائد لكل صفقة
```

هدف +30% نسبي:

```text
≈ +2.877% لكل صفقة
```

---

## 5. مسار البحث الأول — Machine Learning ranking

تم إنشاء نحو 40 Feature لكل إشارة، منها:

- Base range / base length / lift.
- CLV، body، upper/lower wick.
- breakout volume ratio.
- breakout range / ATR.
- compression.
- returns قبل 5 / 10 / 20 / 60 جلسة.
- Relative Strength مقابل proxy للسوق.
- Market breadth و market regime.
- المسافة من High آخر 20 و60 جلسة.
- المسافة التقديرية إلى مقاومة تاريخية أعلى السعر.
- SMA20 / SMA50 context.
- slope / base slope / low slope.
- volume distribution داخل القاعدة.

تم اختبار Logistic Regression وRandom Forest وExtra Trees وGradient Boosting وHist Gradient Boosting.

### بروتوكول الاختيار

```text
Train 2021–2022 → Validate 2023
Train 2021–2023 → Validate 2024
ثم Lock حتى نهاية 2024
ثم Evaluate 2025–Feb 2026
```

2025+ لم يُستخدم لاختيار نوع الموديل أو Threshold.

### أفضل نتيجة ML

```text
2023: 17/43 = 39.53%
2024:  7/16 = 43.75%
Final: 15/33 = 45.45%
```

مقابل v2 Final:

```text
43.55% → 45.45%
Relative improvement ≈ +4.38%
```

**النتيجة:** لم يحقق هدف +30% في Win Rate، وبالتالي لم يتم اعتماد ML كنسخة نهائية.

أكثر الـFeatures تأثيرًا في الموديل كانت تقريبًا:

1. CLV.
2. Upper Wick.
3. Base Range.
4. Breakout relative to 60-day high.
5. Defensive Lift.
6. Breakout candle range.
7. Distance from SMA50.
8. v2 quality flag.
9. 60-session prior return.
10. Breakout candle body.

---

## 6. مسار البحث الثاني — High Selectivity Rules

تم بناء فلاتر تفسيرية إضافية مع فصل زمني:

```text
Threshold calibration: 2021–2022
Validation:            2023
Validation:            2024
Final evaluation:      2025–Feb 2026
```

تم اختبار **7,387** تركيبة مؤهلة من الفلاتر.

أفضل تركيبة مستقرة على فترتي Validation كانت:

```text
v2 signal
+
60-session prior return >= 2.663%
+
nearest estimated overhead resistance >= 0.626%
```

نتائجها:

```text
2023: 8 / 11 = 72.73%
2024: 8 / 10 = 80.00%
Final: 10 / 21 = 47.62%
```

رغم أنها تجاوزت هدف +30% بقوة في 2023 و2024، فإنها هبطت في الفترة النهائية إلى **47.62%**.

مقابل v2 Final:

```text
43.55% → 47.62%
Relative improvement ≈ +9.35%
```

**القرار:** رفض اعتبار هذه الفلاتر تحسينًا حقيقيًا بنسبة 30% لأنها لم تثبت النتيجة في الـFinal Holdout.

---

## 7. الاستنتاج من أبحاث الدخول

على نفس تعريف النجاح:

```text
+8% قبل -4% خلال 10 جلسات
```

لم نجد حتى الآن فلترًا إضافيًا يحسن Win Rate النهائي 30% بصورة يمكن الدفاع عنها إحصائيًا.

محاولة إجبار النتيجة على 56%+ من خلال انتقاء شروط أكثر دقة أدت إلى عينات صغيرة ونتائج Validation ممتازة لكنها لم تستمر في الـHoldout.

لذلك لم يتم تغيير شروط دخول v2 الأساسية لمجرد الوصول إلى رقم مستهدف.

---

## 8. مسار البحث الثالث — Trade Management

بدل محاولة تحسين الدخول أكثر، تم تثبيت **كل إشارات v2** ثم اختبار 320 نظام إدارة صفقة.

Grid:

```text
Targets : 4%, 5%, 6%, 7%, 8%, 9%, 10%, 12%
Stops   : 2%, 2.5%, 3%, 3.5%, 4%, 4.5%, 5%, 6%
Horizon : 5, 7, 10, 12, 15 sessions
```

طريقة الاختيار:

- Optimize على 2023 و2024 فقط.
- تعظيم **أضعف متوسط عائد** بين السنتين.
- 2025–Feb 2026 لم يدخل في الاختيار.
- Same-bar target & stop ambiguity = Stop First.

---

## 9. أفضل إدارة صفقة خرج بها الاختبار

```text
Target  = +12%
Stop    = -4.5%
Horizon = 15 جلسة
```

### Validation 2023

```text
29 صفقة
Target Rate  = 44.83%
Stop Rate    = 34.48%
Timeout Rate = 20.69%
Average realized return = +3.979%
```

### Validation 2024

```text
33 صفقة
Target Rate  = 45.45%
Stop Rate    = 42.42%
Timeout Rate = 12.12%
Average realized return = +3.565%
```

### Final 2025–Feb 2026

```text
62 صفقة
26 Target
21 Stop
15 Timeout
Target Rate  = 41.94%
Stop Rate    = 33.87%
Timeout Rate = 24.19%
Average realized return = +3.648%
Median realized return  = +1.459%
```

---

## 10. التحسن المحقق

مقارنة على نفس 62 إشارة v2 في الفترة النهائية:

| Metric | v2 Management | v3 Management |
|---|---:|---:|
| Target | +8% | +12% |
| Stop | -4% | -4.5% |
| Horizon | 10 | 15 |
| Average return/trade | +2.213% | **+3.648%** |
| Median return/trade | +1.288% | **+1.459%** |
| Target hit rate | 43.55% | 41.94% |

التحسن النسبي في متوسط العائد لكل صفقة:

```text
(3.648 / 2.213) - 1
= +64.85%
```

أي أن هدف **رفع أداء الاستراتيجية 30%** تحقق على مقياس Average Realized Return، وبفارق كبير:

```text
Target requested: +30%
Historical holdout result: +64.85%
```

---

## 11. تعريف v3 Candidate الحالي

### Entry

لا تغيير عن `Defensive Lift v2`.

### Trade Management

```text
Take Profit = +12%
Stop Loss   = -4.5%
Max Holding = 15 جلسة
```

إذا لم يتحقق Target أو Stop خلال 15 جلسة، يتم الخروج نظريًا عند إغلاق الجلسة الخامسة عشرة في الاختبار.

---

## 12. لماذا تحسن العائد رغم انخفاض Target Hit Rate؟

v2 كانت تستهدف:

```text
+8 : -4
```

أي Reward/Risk اسمي = 2.0R.

v3 Candidate تستهدف:

```text
+12 : -4.5
```

أي Reward/Risk اسمي ≈ 2.67R.

الفكرة التي ظهرت في البيانات هي أن إشارات v2 الناجحة لديها قابلية لاستمرار الحركة بعد +8%، ولذلك أخذ ربح مبكر عند +8% كان يقطع جزءًا مهمًا من Right Tail.

النسخة الثالثة تقبل Target Hit Rate أقل قليلًا مقابل ترك الصفقة الناجحة تمتد لمسافة أكبر.

---

## 13. ما لم يتحقق

يجب عدم صياغة النتيجة على أنها:

```text
"رفعنا Win Rate 30%"
```

هذا غير صحيح.

النتيجة الصحيحة هي:

```text
Win Rate / target hit rate لم يتحسن 30%.
Average realized return per historical trade تحسن 64.85% في الـFinal Holdout.
```

---

## 14. القيود

هذه النسخة ما زالت Candidate للأسباب التالية:

1. الـFinal Holdout يحتوي 62 صفقة فقط.
2. البيانات Daily OHLCV، ولذلك لا نعرف ترتيب High وLow داخل الجلسة.
3. تم التعامل مع Same-Bar Target + Stop بشكل محافظ: Stop First.
4. لا توجد عمولات أو Slippage أو Taxes في العوائد المعروضة.
5. المصدر التاريخي المستخدم ينتهي فعليًا قبل وجود فترة جديدة تمامًا بعد البحث، لذلك لا يوجد Pristine Forward Test مستقل بعد.
6. بيانات Corporate Actions وجودة بعض الأسهم تحتاج مراجعة منفصلة قبل أي استخدام إنتاجي.
7. +64.85% نتيجة تاريخية وليست ضمانًا لنتيجة مستقبلية.

---

## 15. القرار البحثي

**Defensive Lift v3 Candidate = v2 Entry + 12% Target / 4.5% Stop / 15-session Horizon.**

هذه هي أفضل نسخة حالية بحسب الاختبار الزمني المستخدم إذا كان الهدف هو تعظيم **متوسط العائد لكل إشارة** وليس تعظيم نسبة الصفقات التي تصيب هدفًا صغيرًا.

قبل تحويلها إلى `v3 Final` يجب إضافة:

- Walk-forward على بيانات أحدث غير مستخدمة نهائيًا في البحث.
- احتساب تكاليف التنفيذ الواقعية.
- Monte Carlo / bootstrap uncertainty على expectancy.
- مقارنة Against simple breakout benchmark وليس v2 فقط.
- تحليل الأداء حسب Market Regime وقطاع السهم.
- فحص Max Drawdown وتسلسل الخسائر عند بناء Portfolio simulation.

---

## 16. الملفات

```text
DEFENSIVE_LIFT_V1.md
DEFENSIVE_LIFT_V2.md
DEFENSIVE_LIFT_V3.md
backtest_v3_ml.py
backtest_v3_rules.py
backtest_v3_management.py
results_v3_ml.json
results_v3_rules.json
results_v3_management.json
```

---

## 17. Status

```text
v1: Frozen Baseline
v2: Frozen Entry Candidate / robust historical filter
v3: Candidate — improved trade management
```

لا يتم تعديل أرقام v1 أو v2 بعد الآن. أي تطوير إضافي يجب أن يحمل إصدار `v3.x` أو `v4` حتى تظل المقارنة قابلة للتكرار.
