# Defensive Lift — Version 5.5 Breadth-Conditional Confirmation

## 1. الحالة

**Status: Rejected Research Version**

`v5.5` نسخة مستقلة لا تعدّل توثيق أو منطق `v3.2` التاريخي. الهدف كان اختبار فرضية خرجت من تحليل Drawdown 2024: هل ضعف `market_breadth20` يجعل اختراقات DLP أكثر عرضة للفشل، وهل يمكن معالجة ذلك بطلب Confirmation بعد الاختراق بدل حذف الإشارة أو تصغير حجمها؟

---

## 2. الثوابت الموروثة من v3.2

```text
Base entry signal = frozen v2 DLP
Target            = +12%
Stop              = -4.5%
Holding           = 7 جلسات بعد الدخول الفعلي
Max positions     = 2
Nominal slot      = 50% equity
Round-trip friction sensitivity = 0.50%
Ranking           = liquidity, كما في v3.2
```

لا يوجد forced exit، ولا resizing، ولا post-loss state machine.

---

## 3. الفرضية

عند Breadth طبيعية، تدخل الإشارة كما هي في v3.2.

عند Breadth منخفضة فقط، لا تُرفض الإشارة فورًا؛ بل يُطلب Confirmation observable بعد الاختراق.

تم اختبار thresholds:

```text
35.0%
37.5%
40.0%
42.5%
45.0%
50.0%
```

و4 أشكال Confirmation:

1. إغلاق الجلسة التالية فوق مقاومة الـbase.
2. إغلاق الجلسة التالية عند/فوق إغلاق شمعة الاختراق.
3. جلستان متتاليتان بإغلاق فوق المقاومة.
4. Retest/Reclaim خلال جلستين: السعر يعود قرب المقاومة ثم يغلق فوقها.

إجمالي شبكة الاختبار:

```text
6 breadth thresholds × 4 confirmations = 24 configurations
```

---

## 4. البروتوكول الزمني

```text
Diagnostic period = 2021-01-01 → 2022-12-31
Validation 1      = 2023-01-01 → 2023-12-31
Validation 2      = 2024-01-01 → 2024-12-31
Final research    = 2025-01-01 → 2026-02-28
```

الفترة النهائية لم تُستخدم في اختيار أي إعداد. وبما أنه لم يوجد إعداد مؤهل في Validation، لم يتم اختيار Candidate لفتح Final عليه.

---

## 5. شروط النجاح

كان يجب أن تتحقق الشروط التالية في **2023 و2024 معًا**:

```text
Ending wealth >= 98% من v3.2
Max Drawdown reduction >= 10%
Active-week >=2% rate >= 95% من v3.2
Minimum trades >= 12
```

---

## 6. أهم تشخيص للـBreadth

الفرضية لم تظهر بشكل monotonic أو ثابت بين الفترات.

### 2021–2022

```text
Breadth <35%:
33 signals
Target rate = 12.12%
Stop rate   = 21.21%
Avg gross   = +3.08%

Breadth 35–40%:
13 signals
Target rate = 7.69%
Stop rate   = 53.85%
Avg gross   = -2.16%
```

هذه الفترة بدت داعمة لفكرة أن نطاق 35–40% خطِر.

### 2023

```text
Breadth <35%:
25 signals
Target rate = 28.00%
Stop rate   = 32.00%
Avg gross   = +2.82%

Breadth 35–40%:
4 signals
Target rate = 50.00%
Stop rate   = 0.00%
Avg gross   = +8.35%
```

هنا انعكست العلاقة في نطاق 35–40% بدل أن تتكرر.

### 2024

```text
Breadth <35%:
16 signals
Target rate = 25.00%
Stop rate   = 31.25%
Avg gross   = +2.80%

Breadth 35–40%:
15 signals
Target rate = 40.00%
Stop rate   = 40.00%
Avg gross   = +2.89%
```

الـBreadth المنخفضة ظهرت في Drawdown 2024 بالفعل، لكنها لم تكن وحدها predictor ثابتًا لفشل DLP على مستوى كل الإشارات.

---

## 7. نتيجة شبكة Confirmation

```text
Tested configurations = 24
Eligible              = 0
Selected              = None
```

أي أن لا threshold ولا شكل Confirmation حقق في 2023 و2024 معًا:

- الحفاظ على 98% من wealth المرجع،
- خفض DD 10%،
- والحفاظ على 95% من active-week +2% rate.

---

## 8. لماذا فشلت الفكرة؟

السبب ليس أن Breadth بلا قيمة. تحليل Drawdown 2024 أظهر بوضوح أن الخسائر الكبيرة حدثت أثناء Breadth منخفضة. لكن عند توسيع الاختبار تاريخيًا ظهر أن **Low Breadth ليست شرطًا كافيًا ولا ثابتًا** لتمييز الـFalse Breakouts.

والـConfirmation بعد الاختراق يغيّر نقطة الدخول نفسها. حتى عندما يتجنب بعض الإشارات الضعيفة، فإنه قد:

- يدخل بسعر أعلى بعد يوم أو يومين،
- يفقد جزءًا من right tail،
- يغيّر ترتيب/تزامن الصفقات داخل المحفظة،
- أو يستبعد Winners حدثت رغم Breadth ضعيفة.

لذلك لم يتحول التشخيص المحلي لـDrawdown 2024 إلى قاعدة Portfolio مستقرة عبر السنوات.

---

## 9. الاستنتاج العلمي

`Breadth` تبدو **عامل سياق** مهم، وليست Gate مستقلة جاهزة للاستخدام.

النتيجة الأدق:

```text
ضعف Breadth قد يرفع هشاشة الاختراق في بعض الفترات،
لكن العلاقة غير مستقرة بما يكفي لاستخدام Threshold + Confirmation كبديل لـv3.2.
```

أي تطوير لاحق يجب أن يتجنب مجرد البحث عن Breadth threshold أدق. الأفضل دمج Breadth مع **خصائص فشل الإشارة نفسها** أو دراسة path-dependent behavior بعد الاختراق دون إعادة توقيت كل الصفقات بشكل أعمى.

---

## 10. الملفات

```text
backtest_v55_breadth_confirmation.py
results_v55_breadth_confirmation.json
DEFENSIVE_LIFT_V55.md
```

Branch:

```text
tmp-egx-defensive-lift-v55-20260904
```

---

## 11. حالة التجميد

**Rejected / Frozen Research Version**

أي تعديل لاحق على منطق الـConfirmation أو إضافة Features جديدة يحصل على Version جديد ولا يُكتب داخل v5.5 بأثر رجعي.
