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
| v5.3 | `DEFENSIVE_LIFT_V53.md` | Rejected | Loss-Cluster State Machine؛ 256 تركيبة و0 اجتازت شروط الثروة + خفض DD + الحفاظ على أسابيع +2% النشطة |
| v5.4 | `DEFENSIVE_LIFT_V54.md` | Rejected | Pre-Loss Cluster Gate؛ خفّض DD في 2023 مع حفظ الثروة تقريبًا لكنه لم يلتقط Drawdown 2024، فكان 0/64 مؤهل |

## النسخة المرجعية الحالية

يظل `v3.2` هو **High-Return Research Reference**. النسخ `v5.1` إلى `v5.4` مهمة لتشخيص مصدر الـDrawdown، لكنها لم تثبت كبديل أفضل.

## نتيجة v5.4 الأساسية

`v5.4` حاولت منع تكدس المخاطرة **قبل الخسارة الأولى** بدل نظام post-loss. حافظت دائمًا على المركز الأول بحجم 50%، ولم تستخدم forced exits أو resizing، وكانت البوابة تعمل فقط عند فتح المركز الثاني.

تم اختبار 64 تركيبة على 2023 و2024 بشروط نجاح متزامنة:

- Ending wealth >= 98% من v3.2 في كل سنة.
- Max Drawdown reduction >= 10% في كل سنة.
- Active-week >=2% hit-rate >= 95% من v3.2 في كل سنة.

النتيجة: **0 تركيبة اجتازت الشروط الثلاثة معًا**.

أفضل Near Miss كان مثيرًا للاهتمام في 2023: حافظ على حوالي 99.49% من الثروة النهائية وخفض الـDrawdown من -6.50% إلى -5.09%. لكنه لم يفعّل البوابة إطلاقًا في 2024، فظل Drawdown عند -11.17% بدون تحسن. لذلك تم رفض النسخة بدون اختيار إعداد من الفترة النهائية.

## الاستنتاج البحثي

نجاح 2023 الجزئي يدل أن Pre-Loss Gating قد يكون اتجاهًا مفيدًا، لكن crowding + market5 + breadth + open-position pain وحدها ليست إشارات مستقرة بما يكفي عبر السنوات. أي نسخة لاحقة يجب ألا تعيد نفس الشبكة بت thresholds أدق فقط؛ يجب أن تضيف فرضية سببية جديدة أو تحليل Attribution أدق لمصدر Drawdown 2024.

## قاعدة التوثيق

1. لا يتم تعديل ملف نسخة قديمة لتبدو كأن شروطًا جديدة كانت موجودة فيها.
2. أي تغيير جوهري في Entry، Exit، Holding، Position Sizing أو Portfolio Risk يحصل على Version جديد.
3. نتائج الفترة النهائية تُذكر منفصلة عن فترة الاختيار.
4. أي نسخة لا تجتاز الاختبار تبقى موثقة كـRejected/Research Candidate بدل حذفها.
5. لا يتم اعتبار نتيجة Backtest ضمانًا للأداء المستقبلي.
