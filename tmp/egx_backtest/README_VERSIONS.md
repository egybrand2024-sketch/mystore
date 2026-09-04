# Defensive Lift — Version Documentation Index

هذا الملف مجرد فهرس. كل نسخة موثقة في ملف Markdown مستقل حتى لا تختلط شروطها أو نتائجها مع نسخة لاحقة.

| Version | File | Status | Main Change |
|---|---|---|---|
| v1.0 | `DEFENSIVE_LIFT_V1.md` | Frozen | التعريف الرقمي الأول للباترن والـbaseline |
| v2.0 | `DEFENSIVE_LIFT_V2.md` | Frozen Candidate | تحسين جودة إشارة الدخول بفلاتر أكثر صرامة |
| v3.0 | `DEFENSIVE_LIFT_V3.md` | Frozen Candidate | تحسين Trade Management إلى +12% / -4.5% / 15 جلسة |
| v3.1 | `DEFENSIVE_LIFT_V31.md` | Frozen Portfolio Reference | تحويل الاختبار إلى محفظة محدودة رأس المال والمراكز |
| v3.2 | `DEFENSIVE_LIFT_V32.md` | Frozen Time-Efficiency Reference | تقليل Holding إلى 7 جلسات وتحسين Capital Velocity |
| v3.3 | `DEFENSIVE_LIFT_V33.md` | Frozen Risk-Control Research Reference | Risk-Based Position Sizing + Aggregate Open Risk |
| v3.4 | `DEFENSIVE_LIFT_V34.md` | Rejected | Weekly Risk Budget خفّض استخدام رأس المال ولم يحافظ على العائد |
| v3.5 | `DEFENSIVE_LIFT_V35.md` | Rejected | Dynamic Stop / Profit Lock لم يحافظ على 98% من العائد مع خفض DD المطلوب |
| v4.0 | `EGX_MULTI_ENGINE_V40.md` | Rejected | إضافة BRT/PBC/FBR زادت الإشارات لكن أضعفت جودة المحفظة |
| v4.1 | `EGX_MULTI_ENGINE_V41.md` | Rejected | Quality Gate مشدد للمحركات الثانوية؛ لم توجد محفظة تجتاز الشروط |
| v4.2 | `DEFENSIVE_LIFT_V42.md` | Rejected | Market-Regime Exposure لم يخفض DD دون قص أرباح مهمة |
| v4.3 | `DEFENSIVE_LIFT_V43.md` | Rejected after Holdout | Weekly Gain/Loss Entry Lock نجح في Validation ولم يحافظ على ميزة كافية في Final |
| v5.1 | `DEFENSIVE_LIFT_V51.md` | Rejected as replacement / Diagnostic Reference | Correlation-Aware Risk خفّض DD لكنه قص جزءًا من العائد؛ أثبت أن Pearson correlation وحده لا يفسر Loss Clustering |
| v5.2 | `DEFENSIVE_LIFT_V52.md` | Rejected | Pairwise Failure Probability؛ 160 تركيبة و0 اجتازت شروط الحفاظ على الثروة وخفض DD في 2023 و2024 |

## النسخة المرجعية الحالية

يظل `v3.2` هو **High-Return Research Reference**. `v5.1` و`v5.2` مهمتان كمختبرات لتشخيص مصدر الـDrawdown، لكنهما لم تثبتا كبديل أفضل.

## نتيجة v5.2 الأساسية

النموذج تم تدريبه على 2021–2022 فقط، ثم اختباره على 2023 و2024 قبل فتح أي Final. حجم عينة التدريب كان صغيرًا نسبيًا: 68 زوجًا فقط، منها 10 حالات فشل مشترك. رغم AUC مرتفع جدًا داخل التدريب، الأداء لم يكن مستقرًا خارج العينة: عدة نماذج هبطت في 2023 إلى AUC أقل من 0.5 ثم ارتفعت بقوة في 2024. لذلك لم توجد تركيبة تحافظ على >=97% من ثروة v3.2 وتخفض Max Drawdown >=10% في كل سنة Validation.

## الاتجاه البحثي التالي

بعد فشل نموذج Probability المباشر، الاتجاه التالي يجب أن يقلل درجة الحرية بدل زيادتها:

- بناء **Loss-Cluster State Machine** بسيط وقابل للتفسير.
- التركيز على حالة المحفظة والسوق عند تتابع إشارات DLP، بدل محاولة توقع كل زوج بModel منفصل.
- استخدام قواعد قليلة وثابتة يتم اشتقاقها من 2021–2022 ثم اختبارها على 2023 و2024.
- الحفاظ على 50% slot لأفضل إشارة وعدم خفض الحجم إلا عند وجود دليل قوي على Cluster Risk.
- قياس المحافظة على Right Tail كشرط صريح، وليس فقط Max Drawdown.

## قاعدة التوثيق

1. لا يتم تعديل ملف نسخة قديمة لتبدو كأن شروطًا جديدة كانت موجودة فيها.
2. أي تغيير جوهري في Entry، Exit، Holding، Position Sizing أو Portfolio Risk يحصل على Version جديد.
3. نتائج الـHoldout تُذكر منفصلة عن فترة الاختيار.
4. أي نسخة لا تجتاز الاختبار تبقى موثقة كـRejected/Research Candidate بدل حذفها.
5. لا يتم اعتبار نتيجة Backtest ضمانًا للأداء المستقبلي.
