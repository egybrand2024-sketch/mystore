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
| v5.8 | `DEFENSIVE_LIFT_V58.md` | Rejected / Diagnostic Reference | Selective Hazard Gate؛ ترك الصفقات العادية 50% وطبّق staging فقط على subset مسبق الخطر. حافظ على العائد أفضل بكثير، لكن hazard attribution لم يكن ثابتًا ولم يحقق خفض DD >=10% في 2023 و2024 معًا |

## النسخة المرجعية الحالية

يظل `v3.2` هو **High-Return Research Reference**. النسخ `v5.1` إلى `v5.8` مهمة لتشخيص مصدر الـDrawdown، لكنها لم تثبت كبديل أفضل.

## نتيجة v5.8 الأساسية

`v5.8` اختبرت الفكرة التالية: لا نقلل حجم كل إشارات DLP. الصفقات العادية تدخل 50% فورًا مثل v3.2، ونطبق Probe + Add-on فقط على subset مصنف مسبقًا كـhazard باستخدام Breadth وMarket20 وRS20 وامتداد الاختراق والمسافة للـOverhead.

تم اختبار **96 configuration**. شروط القبول شملت الحفاظ على >=98% من ثروة v3.2، خفض DD >=10% في 2023 و2024، الحفاظ على >=95% من active-week +2%، وأن يظل hazard subset <=35% من الإشارات. النتيجة: **0/96 مؤهل**.

أهم near miss من ناحية حفظ العائد كان تعريف `context_plus_two_tech` مع Probe 45% وMFE>=2% في اليوم الأول مع إبقاء الـprobe عند عدم التأكيد. حافظ على حوالي **99.8%** من ثروة v3.2 وعلى active-week +2% بالكامل، لكنه خفض الـDD فقط بحوالي **2.1%** في أسوأ سنة، وليس 10%.

تعريف `double_context_plus_one_tech` كان مثيرًا في 2024: بعض التركيبات خفضت DD من -11.17% إلى حوالي -8.2% ورفعت العائد، لكنه لم يكن ثابتًا؛ نفس الاتجاه زاد DD في 2023. لذلك لا نعتمد rule تم ضبطه على شكل Drawdown 2024 وحده.

## الاستنتاج البحثي

`v5.8` حسّنت فهم المشكلة: **Selective staging يمكنه حفظ الـright tail أفضل بكثير من staging العام.** لكن نقطة الضعف أصبحت هي تحديد الـhazard نفسه. الفلاتر البسيطة الحالية لا تعزل subset صغيرًا وثابتًا من الخطر عبر السنين.

الخطوة التالية، إن استمر البحث، يجب أن تكون فرضية جديدة في **hazard attribution** لا مجرد tightening للـthresholds بعد رؤية النتائج.

## قاعدة التوثيق

1. لا يتم تعديل ملف نسخة قديمة لتبدو كأن شروطًا جديدة كانت موجودة فيها.
2. أي تغيير جوهري في Entry، Exit، Holding، Position Sizing أو Portfolio Risk يحصل على Version جديد.
3. نتائج الفترة النهائية تُذكر منفصلة عن فترة الاختيار.
4. أي نسخة لا تجتاز الاختبار تبقى موثقة كـRejected/Research Candidate بدل حذفها.
5. لا يتم اعتبار نتيجة Backtest ضمانًا للأداء المستقبلي.
