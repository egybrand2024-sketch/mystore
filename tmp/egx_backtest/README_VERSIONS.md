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
| v5.5 | `DEFENSIVE_LIFT_V55.md` | Rejected | Breadth-Conditional Confirmation؛ 24 تركيبة و0 مؤهل، والـLow Breadth لم تظهر كعامل فشل monotonic ثابت عبر السنوات |
| v5.6 | `DEFENSIVE_LIFT_V56.md` | Rejected | Early Path Behavior؛ 45 تركيبة و0 مؤهل. مسار الفائزين والخاسرين يختلف بوضوح، لكن close-based exits تأتي متأخرة عن كثير من intraday stops |
| v5.7 | `DEFENSIVE_LIFT_V57.md` | Rejected | Staged Probe + Add-on؛ 64 تركيبة و0 مؤهل. خفض الـDD لكنه فقد جزءًا كبيرًا من right-tail بسبب التأخر في الوصول للحجم الكامل |

## النسخة المرجعية الحالية

يظل `v3.2` هو **High-Return Research Reference**. النسخ `v5.1` إلى `v5.7` مهمة لتشخيص مصدر الـDrawdown، لكنها لم تثبت كبديل أفضل.

## نتيجة v5.7 الأساسية

`v5.7` استخدمت probe أصغر عند إشارة DLP ثم أعادت الحجم إلى 50% فقط إذا ظهر continuation في أول جلسة أو جلستين. تم اختبار أحجام probe من 15% إلى 30%، وأربع قواعد continuation، مع خيار إبقاء الـprobe أو الخروج منه إذا فشل التأكيد.

تم اختبار **64 configuration**. النتيجة: **0/64 مؤهل**.

أفضل Near Miss كان Probe 30%، قرار Add-on بعد الجلسة الأولى، والتأكيد MFE >= +2%، مع إبقاء الـprobe إذا لم يتأكد. في 2023 خفض الـDD من -6.50% إلى -4.17% لكنه خفض العائد من +38.78% إلى +31.66%. وفي 2024 خفض الـDD من -11.17% إلى -9.58% لكنه خفض العائد من +46.22% إلى +33.71%.

النتيجة البحثية: staging العام لكل DLP يقلل الخسارة فعلًا، لكنه يقلل المشاركة المبكرة في right-tail winners بما يكفي لكسر شرط الحفاظ على الثروة. لذلك لا نعتمده بديلًا عن v3.2.

## الاستنتاج البحثي

إذا استمر البحث، لا نستخدم Probe لكل الإشارات. الاتجاه الأنسب هو اكتشاف **subset صغير جدًا** من DLP تكون فيه full-size immediate entry خطرة بشكل خاص، مع ترك بقية إشارات v3.2 تدخل 50% فورًا بلا تغيير.

## قاعدة التوثيق

1. لا يتم تعديل ملف نسخة قديمة لتبدو كأن شروطًا جديدة كانت موجودة فيها.
2. أي تغيير جوهري في Entry، Exit، Holding، Position Sizing أو Portfolio Risk يحصل على Version جديد.
3. نتائج الفترة النهائية تُذكر منفصلة عن فترة الاختيار.
4. أي نسخة لا تجتاز الاختبار تبقى موثقة كـRejected/Research Candidate بدل حذفها.
5. لا يتم اعتبار نتيجة Backtest ضمانًا للأداء المستقبلي.
