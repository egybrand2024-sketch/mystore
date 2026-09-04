# Defensive Lift Pattern — Version 3.3 Risk-Based Position Sizing

> نسخة مستقلة مبنية فوق `Defensive Lift v3.2`، هدفها الحفاظ على مدة الصفقة القصيرة مع تقليل تركيز رأس المال عن طريق ربط حجم المركز بالمخاطرة المخططة بدل عدد المراكز فقط.

## 1. الحالة

**Status: Historical Risk-Control Candidate**

هذه النسخة لا تغيّر إشارة الدخول ولا تغير الهدف/الوقف/مدة الاحتفاظ التي ثبتتها v3.2.

الثابت:

```text
Entry       = Defensive Lift v2 signal
Take Profit = +12%
Stop Loss   = -4.5%
Max Holding = 7 جلسات
```

التغيير الوحيد الرئيسي:

```text
Risk-Based Position Sizing
+
Aggregate Open-Risk Cap
```

---

## 2. لماذا ظهرت الحاجة إلى v3.3؟

في `v3.2` كان الحد الأقصى مركزين، وبالتالي كان حجم المركز قد يصل نظريًا إلى نحو 50% من رأس المال.

مع وقف 4.5%:

```text
50% × 4.5% = 2.25% مخاطرة من Equity لكل صفقة
```

هذا حسن سرعة تدوير رأس المال، لكنه رفع تركيز المخاطرة.

الهدف في v3.3 هو أن نقول قبل كل دخول:

```text
أنا أخاطر بنسبة محددة من Equity
```

ثم يُشتق حجم المركز من هذه النسبة.

---

## 3. معادلة تحديد حجم المركز

إذا كانت:

```text
Risk per Trade = R
Stop Distance  = 4.5%
Current Equity = E
```

فإن:

```text
Risk Amount   = E × R
Position Size = Risk Amount / 4.5%
```

مثال عند مخاطرة 1%:

```text
Position Size ≈ 1% / 4.5%
              ≈ 22.22% من Equity
```

إذن المركز لم يعد 50% لمجرد أن عدد المراكز اثنان.

---

## 4. بروتوكول الاختبار

فترات الاختيار:

```text
Validation 1 = 2023
Validation 2 = 2024
```

الفترة النهائية:

```text
Final Holdout = 2025-01-01 → 2026-02-28
```

فترة الـFinal لم تستخدم في اختيار الإعداد.

افتراض الاحتكاك:

```text
0.50% Round Trip
```

حد الـDrawdown المسموح أثناء الاختيار:

```text
10%
```

طريقة الترتيب:

1. تعظيم أضعف CAGR بين 2023 و2024.
2. عند التقارب، تفضيل Worst Drawdown أقل.

---

## 5. مساحة البحث

### Risk per Trade

```text
0.50%
0.75%
1.00%
```

### Max Aggregate Open Risk

```text
1.00%
1.50%
2.00%
2.50%
3.00%
```

### Max Positions

```text
2
3
4
5
```

عدد التركيبات المؤهلة:

```text
60
```

---

## 6. الإعداد المختار

أفضل إعداد حسب بروتوكول الاختيار كان:

```text
Risk per Trade = 1.00% من Equity
Max Open Risk  = 3.00% من Equity
Max Positions  = 3
```

وبما أن Stop = 4.5%، فإن الحجم النظري الكامل للمركز يقارب:

```text
1.00% / 4.5%
≈ 22.22% من Equity
```

إذا كانت 3 صفقات كاملة المخاطرة مفتوحة:

```text
Planned Aggregate Risk ≈ 3% من Equity
```

قبل فروق التنفيذ والحركة الفعلية في Equity.

---

## 7. Validation Results

### 2023

```text
Trades               = 21
Skipped              = 8
Total Return         = +18.11%
CAGR                 = 18.23%
Max Drawdown         = -2.93%
Positive Rate        = 66.67%
Longest Losing Streak= 1
Avg Holding          = 5.38 جلسة
Average Exposure     = 10.46%
Max Exposure         = 68.35%
Max Planned Open Risk≈ 2.97%
```

### 2024

```text
Trades               = 27
Skipped              = 4
Total Return         = +19.05%
CAGR                 = 19.12%
Max Drawdown         = -5.08%
Positive Rate        = 55.56%
Longest Losing Streak= 3
Avg Holding          = 4.44 جلسة
Average Exposure     = 11.24%
Max Exposure         = 46.35%
Max Planned Open Risk≈ 2.02%
```

أضعف CAGR بين فترتي الاختيار:

```text
18.23%
```

---

## 8. Final Holdout Result

الفترة:

```text
2025-01-01 → 2026-02-28
```

النتيجة:

```text
Trades               = 49
Skipped              = 13
Initial Capital      = 100,000 EGP
Final Equity         = 130,205.58 EGP
Total Return         = +30.21%
CAGR                 = 27.41%
Max Drawdown         = -3.19%
Positive Rate        = 51.02%
Longest Losing Streak= 3
Avg Holding          = 5.43 جلسة
Median Holding       = 7 جلسات
Average Exposure     = 22.40%
Max Exposure         = 67.79%
Avg Planned Open Risk= 1.00%
Max Planned Open Risk≈ 3.04%
```

> تجاوز 3.00% بشكل طفيف في القيمة المحسوبة سببه تغير Equity بين لحظة تحديد Risk Amount ولحظة Mark-to-Market، وليس السماح المتعمد بتجاوز سقف الدخول.

---

## 9. مقارنة v3.2 مع v3.3

| Metric | v3.2 | v3.3 |
|---|---:|---:|
| Target | +12% | +12% |
| Stop | -4.5% | -4.5% |
| Max Holding | 7 | 7 |
| Position Sizing | Slot-based | **Risk-based** |
| Planned Risk / Trade | حتى ~2.25% نظريًا | **1.00%** |
| Max Planned Open Risk | غير مفصول بوضوح | **3.00%** |
| Trades | 42 | 49 |
| Total Return | +71.01% | **+30.21%** |
| CAGR | 63.62% | **27.41%** |
| Max Drawdown | -6.91% | **-3.19%** |
| Avg Holding | 5.36 | **5.43 جلسة** |

الخلاصة:

```text
v3.3 لم تُبنَ لتعظيم العائد الخام.
بُنيت لفصل حجم المركز عن عدد المراكز وتقليل المخاطرة المركزة.
```

وقد نجحت تاريخيًا في خفض Max Drawdown في الـFinal من:

```text
-6.91% → -3.19%
```

أي انخفاض يقارب 54% في عمق الـDrawdown، لكن على حساب انخفاض واضح في العائد الكلي.

---

## 10. Conservative Reference

تم أيضًا قياس إعداد أكثر تحفظًا، غير مختار كأفضل CAGR:

```text
Risk per Trade = 0.75%
Max Open Risk  = 1.50%
Max Positions  = 3
```

Final Holdout:

```text
Trades               = 35
Skipped              = 27
Final Equity         = 116,233.42 EGP
Total Return         = +16.23%
CAGR                 = 14.80%
Max Drawdown         = -2.56%
Positive Rate        = 51.43%
Avg Holding          = 5.34 جلسة
Max Exposure         = 34.55%
Max Planned Open Risk≈ 1.50%
```

هذا يوضح بوضوح الـTrade-off بين:

```text
Capital Utilization
Return
Drawdown
Risk Budget
```

---

## 11. القرار البحثي

`v3.3` **ليست بديلًا تلقائيًا لـv3.2**.

لدينا الآن مساران مختلفان بوضوح:

### v3.2 — Growth / Fast Capital Rotation

```text
Historical Return أعلى
Drawdown أعلى
Risk concentration أعلى
```

### v3.3 — Risk-Controlled Capital Rotation

```text
Historical Return أقل
Drawdown أقل بكثير
Risk per trade معروف مسبقًا
Aggregate portfolio risk محدود
```

وهذا الفصل مهم بدل محاولة وصف نسخة واحدة بأنها الأفضل لكل أهداف المستثمر.

---

## 12. حدود الاختبار

- البيانات Daily OHLCV.
- Same-bar target/stop يعامل Stop First.
- الاحتكاك 0.5% افتراض حساسية وليس جدول تكاليف رسمي.
- لا يوجد ضمان أن الـDrawdown المستقبلي سيبقى ضمن التاريخي.
- Position Risk مبني على وقف نظري؛ gap/slippage قد يجعل الخسارة الفعلية أكبر.
- العينة ما زالت محدودة ويجب توسيعها مع بيانات أحدث قبل ترقية النسخة إلى Final.

---

## 13. ملفات النسخة

```text
backtest_v33_risk_sizing.py
results_v33_risk_sizing.json
DEFENSIVE_LIFT_V33.md
```

---

## 14. حالة التجميد

**Status: Frozen Research Reference**

أي تغيير لاحق في Risk per Trade، Dynamic Risk، Portfolio Heat، أو اختيار الإشارات تحت التزاحم يجب أن يحصل على رقم Version جديد مثل `v3.4`.
