# Defensive Lift — Version 5.2 Pairwise Failure Probability

## الحالة

**Status: Rejected Research Version**

هذه النسخة اختبرت فرضية مختلفة عن v5.1: بدل الاعتماد على Pearson correlation وحده، تم بناء نموذج يتوقع **احتمال فشل صفقتين DLP معًا** من خصائص الإشارتين والسوق وقت الدخول، مع الحفاظ على هيكل v3.2 كما هو.

```text
Entry = Frozen v2 DLP
Target = +12%
Stop = -4.5%
Max holding = 7 sessions
Max positions = 2
Nominal slot = 50% of portfolio equity
Round-trip friction assumption = 0.50%
```

## الفرضية

إذا كانت الصفقة الثانية ترفع احتمال خسارة مشتركة مع مركز مفتوح بالفعل، يتم حجب الصفقة الثانية فقط. لا يتم تصغير حجم أفضل صفقة تلقائيًا.

## بروتوكول البيانات

- Model Training: 2021–2022.
- Validation 1: 2023.
- Validation 2: 2024.
- Final Holdout: 2025–Feb 2026.
- الـFinal لم يُستخدم في تدريب النموذج أو اختيار Threshold.

## تعريف فشل الزوج

```text
Pair Failure = الصفقتان تنتهيان بعائد Gross سلبي
```

يتم تكوين أزواج الإشارات عندما تكون تواريخ دخولها متقاربة حتى 12 يومًا تقويميًا.

## الخصائص المختبرة

تم اختبار مجموعتين من الخصائص `lean` و`full` تضمنت:

- فرق توقيت الدخول / نفس اليوم.
- Correlation سابق 20 و40 جلسة.
- Downside overlap سابق.
- Signal quality لكل صفقة.
- Relative Strength 20.
- CLV والجسم وحجم الاختراق.
- المسافة إلى مقاومة تاريخية قريبة.
- Breakout return / overextension.
- Market 5/20-session return.
- Market breadth.
- Flags مشتركة مثل ضعف RS أو قرب المقاومة أو امتداد الاختراق.

النموذج المستخدم Logistic Regression مع Standard Scaling، وتم اختبار عدة قيم Regularization وClass Weight.

## حجم البيانات

```text
Stocks = 198
DLP signals = 170
Training pairs 2021–2022 = 68
Training joint-failure pairs = 10
2023 pairs = 51
2024 pairs = 40
Final-period pairs = 150
```

## شبكة البحث

```text
16 model variants
10 probability thresholds
160 portfolio configurations tested
```

Thresholds المختبرة:

```text
0.25 → 0.70
```

## شروط النجاح

أي مرشح يجب أن يحقق في **كل من 2023 و2024**:

```text
Ending wealth >= 97% of frozen v3.2
AND
Max Drawdown reduction >= 10%
```

## النتيجة

**0 من 160 Portfolio Configurations اجتازت الشرطين معًا.**

لذلك لم يتم اختيار Model/Threshold نهائي، ولم يتم فتح الـFinal لاختيار نتيجة بعد رؤية المستقبل.

## أهم سبب للفشل

النموذج أظهر عدم استقرار واضح بين السنوات. مثال من النماذج البسيطة:

- Train AUC كان مرتفعًا جدًا، قرابة 0.95–0.98 في عدة إعدادات.
- في 2023 هبط AUC في أمثلة عديدة إلى قرابة 0.30–0.42، أي أن ترتيب احتمالات الفشل لم ينتقل جيدًا خارج التدريب.
- نفس النماذج أعطت AUC مرتفعًا مرة أخرى في 2024، قرابة 0.84–0.94.

هذا التذبذب يشير إلى أن **Joint Failure regime غير ثابت** وأن عينة التدريب صغيرة جدًا، خصوصًا مع 10 حالات Joint Failure فقط في Training.

## الاستنتاج

الفكرة نفسها لم تُثبت كفايتها كـProduction Risk Gate. فشل v5.2 لا يعني أن الخسائر المشتركة غير قابلة للتنبؤ، لكنه يعني أن **نموذج Pairwise ML مباشر على هذا الحجم من البيانات غير مستقر بما يكفي**.

الدرس الرئيسي:

1. عدد Joint Failures في التدريب قليل.
2. العلاقة بين الخصائص والفشل تغيّرت بين 2023 و2024.
3. رفع تعقيد النموذج سيزيد خطر Overfitting بدل حل المشكلة.
4. الأفضل في النسخة التالية اختبار **قواعد Loss-Cluster أبسط ومبنية على حالة المحفظة والسوق والتوقيت** بدل Probability Model عالي الحساسية للعينة.

## القرار

**Rejected.**

`v3.2` يظل High-Return Research Reference. `v5.1` يبقى دليلًا أن Risk Gating الانتقائي يمكنه خفض DD جزئيًا، لكن `v5.2` لم ينجح في تعميم احتمال الفشل المشترك.

## الملفات

- `backtest_v52_pairwise_failure.py`
- `results_v52_pairwise_failure.json`
- `DEFENSIVE_LIFT_V52.md`
