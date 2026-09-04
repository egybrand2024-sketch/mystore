# Defensive Lift — Version 5.4 Pre-Loss Cluster Gate

## الحالة

**Status: Rejected**

هذه النسخة تختبر فرضية جديدة مختلفة عن v5.3: بدل انتظار أول خسارة ثم الدخول في حالة AMBER/RED، نحاول اكتشاف **خطر تكدس المخاطرة قبل الخسارة الأولى**.

القاعدة الأساسية بقيت ثابتة:

```text
Entry = Frozen Defensive Lift v2
Target = +12%
Stop = -4.5%
Max holding = 7 sessions
Max positions = 2
Nominal slot = 50% of portfolio equity
Round-trip friction = 0.50%
```

## الفكرة

لا يتم تصغير الصفقة الأولى ولا إجبار أي مركز مفتوح على الخروج. البوابة تعمل فقط عند محاولة فتح **المركز الثاني**.

يتم حساب Score قبل الدخول باستخدام معلومات متاحة في نفس اللحظة فقط:

1. Recent DLP signal crowding.
2. Market 5-session impulse.
3. 20-session market breadth.
4. Mark-to-market return للمركز الأول المفتوح.

إذا تجاوز الـScore الحد المحدد، يتم حجب المركز الثاني فقط.

## شبكة الاختبار

تم اختبار:

```text
Crowding lookback = 3 / 5 sessions
Crowding threshold = 2 / 3 signals
Market 5-session threshold = -1% / 0%
Breadth20 threshold = 45% / 50%
Open-position pain threshold = -1% / 0%
Score threshold = 2 / 3
```

إجمالي التركيبات:

```text
64
```

## شروط النجاح

تم الاختيار على 2023 و2024 فقط.

لكي تصبح التركيبة مرشحًا كان يجب أن تحقق في **كل سنة Validation**:

```text
Ending wealth >= 98% من v3.2
AND
Max Drawdown reduction >= 10%
AND
Active-week >=2% rate >= 95% من v3.2
```

الفترة 2025–Feb 2026 لم تستخدم لاختيار الإعداد.

## النتيجة

```text
Eligible configs = 0 / 64
```

إذًا النسخة **Rejected** ولم يتم فتح Final لاختيار إعداد بعد رؤية المستقبل.

## أفضل Near Miss

أفضل إعداد قريب كان تقريبًا:

```text
Crowd lookback = 3
Crowd threshold = 3
Market5 threshold = -1%
Breadth20 threshold = 45%
Open pain threshold = -1%
Score threshold = 3
```

### 2023

```text
v3.2 return        = +38.78%
v5.4 return        = +38.08%
Wealth preservation≈ 99.49%

v3.2 Max DD        = -6.50%
v5.4 Max DD        = -5.09%
DD reduction       ≈ 21.65%
```

وهذا كان جيدًا نسبيًا: خفض Drawdown مع قص صغير جدًا في الثروة.

البوابة حجبت 5 فرص في 2023. بالنظر اللاحق فقط للتشخيص، 3 منها انتهت بخسارة و2 انتهت بمكسب، بينها صفقة وصلت للهدف الكامل +12%.

### 2024

المشكلة الحاسمة:

```text
Gate events = 0
```

أي أن أفضل Rule التي نجحت جزئيًا في 2023 **لم تتدخل أصلًا** في 2024، وبالتالي:

```text
Return = نفس v3.2 تقريبًا
Max DD = نفس v3.2 = -11.17%
DD reduction = 0%
```

ولهذا فشلت شرط خفض الـDrawdown في كل سنة Validation.

## الاستنتاج

v5.4 أثبتت نقطتين مهمتين:

1. يمكن فعلًا العثور على ظروف قبل الخسارة تقلل بعض التكدس بدون قص كبير من العائد — ظهر ذلك في 2023.
2. لكن نفس القواعد لم تكن مستقرة بين السنوات؛ في 2024 لم تُفعّل في الأماكن التي صنعت Drawdown الكبير.

المشكلة إذًا ليست أن Pre-Loss Gate مستحيلة، بل أن الإشارات الحالية — crowding + market5 + breadth + open-position pain — لا تلتقط سبب التراجع بطريقة مستقرة كفاية.

## القرار

- لا تعتمد v5.4 كبديل لـ v3.2.
- لا يتم تخفيف شروط النجاح بعد رؤية نتيجة 2024.
- v3.2 تظل High-Return Research Reference.
- أي تطوير لاحق يجب أن يكون Version جديدًا مستقلًا.

## الملفات

```text
backtest_v54_pre_loss_cluster_gate.py
results_v54_pre_loss_cluster_gate.json
DEFENSIVE_LIFT_V54.md
```

## ملاحظة منهجية

تشخيص blocked winners / blocked losers الموجود في النتائج يستخدم outcome المستقبلي **للتقييم بعد الاختبار فقط**، وليس في قرار الدخول نفسه.

نتائج الـBacktest تاريخية ولا تمثل ضمانًا للأداء المستقبلي.
