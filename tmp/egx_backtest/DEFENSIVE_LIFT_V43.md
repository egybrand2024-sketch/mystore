# Defensive Lift — Version 4.3 Weekly Profit Protection Overlay (Rejected)

## الحالة

**Status: Rejected after Final Holdout**

## الهدف

الحفاظ على الحجم العادي للمركز والهدف +12%، مع حماية الأسبوع القوي عن طريق إيقاف **الدخول الجديد فقط** بعد بلوغ حد ربح أسبوعي أو حد خسارة أسبوعي. لا يتم إغلاق المراكز الرابحة مبكرًا، ولا يتم خفض Target.

## الثوابت

```text
Entry   = Defensive Lift v2
Target  = +12%
Stop    = -4.5%
Horizon = 7 sessions
Slots   = 2
Friction sensitivity = 0.50% round trip
```

## الشبكة المختبرة

- Gain Lock: بدون / +2% / +3% / +4% أسبوعيًا.
- Loss Lock: بدون / -1.5% / -2% / -2.5% / -3% أسبوعيًا.
- حجم الصفقة التالية بعد أول خسارة أسبوعية: 25% / 35% / 50%.

```text
Configurations tested = 60
Eligible on 2023/2024 = 9
```

## شرط القبول قبل فتح الـFinal

في كل من 2023 و2024:

1. Ending Wealth >= 95% من Baseline v3.2.
2. Max Drawdown أقل من v3.2 بما لا يقل عن 10%.

## التركيبة المختارة من Validation فقط

```text
Gain Lock      = +2%
Loss Lock      = -1.5%
After-loss size= 50%
```

هذا يعني أن الآلية المؤثرة فعليًا كانت: **قفل الدخول الجديد بعد +2% أسبوعيًا أو بعد -1.5% أسبوعيًا**؛ لم يكن هناك تقليل دائم لحجم الصفقة بعد أول خسارة.

## Validation 2023

```text
Total Return = +46.85%
CAGR         = +47.20%
Max DD       = -4.91%
Trades       = 20
Positive     = 70.00%
Avg Trade    = +3.99%
Avg Week     = +0.75%
Week-end >=2%= 22.64%
```

مقابل Baseline v3.2 DD ≈ -6.50%.

## Validation 2024

```text
Total Return = +46.80%
CAGR         = +47.00%
Max DD       = -8.90%
Trades       = 22
Positive     = 59.09%
Avg Trade    = +3.67%
Avg Week     = +0.78%
Week-end >=2%= 17.31%
```

مقابل Baseline v3.2 DD ≈ -11.17%.

التركيبة حسنت Ending Wealth في أسوأ سنة Validation بنحو 2.23% عن Baseline، وخفضت Drawdown في أسوأ المقارنات بحوالي 20.3%.

## Final Holdout 2025–Feb 2026

لم تُستخدم هذه الفترة في اختيار الإعداد.

### v4.3

```text
Trades       = 37
Total Return = +58.76%
CAGR         = +52.83%
Max DD       = -6.59%
Avg Trade    = +2.67%
Positive     = 56.76%
Avg Week     = +0.84%
Week-end >=2%= 25.86%
Worst Week   = -4.43%
```

### Same-engine Baseline v3.2

```text
Total Return = +75.86%
Max DD       = -6.91%
Avg Week     = +1.03%
Week-end >=2%= 31.03%
```

## القرار

رغم نجاح Validation، لم تستمر الميزة في الـFinal Holdout:

- خفض الـDrawdown النهائي كان صغيرًا فقط، حوالي 4.7% نسبيًا.
- Ending Wealth انخفض بحوالي 9.7% مقارنة بالـBaseline نفسه.
- متوسط العائد الأسبوعي ونسبة أسابيع +2% انخفضا أيضًا.

لذلك تم رفض v4.3 وعدم اعتمادها كبديل لـv3.2.

## ما تعلمناه

قفل الأسبوع بعد الوصول إلى +2% يبدو منطقيًا نفسيًا، لكنه في البيانات يقطع بعض الإشارات اللاحقة ذات القيمة العالية. الهدف الصحيح ليس "قفل أي أسبوع أخضر" بل تقليل **Risk Cost** للفرصة دون إلغاء الفرص الجيدة.

## الاتجاه التالي

النسخة التالية تنتقل إلى **DLP Staged Entry / Pre-Breakout Engine**:

- الدخول بجزء أصغر قبل الاختراق فقط عندما يكون DLP قد اكتمل تقريبًا.
- إضافة الجزء الثاني بعد اختراق v2 المؤكد.
- Stop أضيق للجزء المبكر + Time Stop إذا لم يحدث الاختراق.
- الحفاظ على Target +12% وعدم إضافة Setup Family ضعيف.

الهدف: خفض متوسط تكلفة الدخول والخطر الفعلي، وزيادة سرعة العائد في الأسابيع النشطة بدون خفض Right Tail.

## الملفات

- `backtest_v43_weekly_overlay.py`
- `results_v43_weekly_overlay.json`
- `DEFENSIVE_LIFT_V43.md`
