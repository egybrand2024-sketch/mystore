# Defensive Lift — Version 5.3 Loss-Cluster State Machine

## الحالة

**Status: Rejected Research Version**

## الهدف

الحفاظ على بنية `v3.2` عالية العائد بدون تصغير حجم أفضل صفقة:

- Entry: Frozen v2 DLP
- Target: +12%
- Stop: -4.5%
- Max holding: 7 sessions
- Max positions: 2
- Nominal slot: 50% of portfolio equity
- Friction assumption: 0.5% round trip

الفكرة كانت أن المشكلة قد تكون في **تجمع الخسائر** لا في مخاطرة الصفقة الواحدة. لذلك تم بناء State Machine بسيطة ومفسرة تتحكم فقط في فتح **المركز الثاني**.

## الحالات

### GREEN
الوضع الطبيعي. يسمح بالمركز الأول والثاني، كل منهما 50%.

### AMBER
يبدأ بعد تحقق خسارة فعلية في صفقة، ويستمر عددًا محدودًا من الجلسات.

### RED
يبدأ إذا حدثت خسارة ثانية داخل Cluster Window، أو إذا كانت المحفظة في AMBER وظهر ضعف سوق/ضغط قوي على مركز مفتوح.

## قاعدة المخاطرة

النظام لا يصغر المركز القائم ولا يخرج منه مبكرًا. المركز الأول 50% يظل مسموحًا دائمًا. القرار الوحيد هو هل يسمح بإضافة المركز الثاني 50% أم لا أثناء AMBER/RED.

## شبكة الاختبار

تم اختبار 256 تركيبة تشمل:

- AMBER TTL: 3 / 5 جلسات
- Cluster window: 5 / 10 جلسات
- RED TTL: 3 / 5 جلسات
- Market 5-session threshold: -2% / 0%
- Breadth threshold: 45% / 50%
- Weak mode: AND / OR
- Open-position pain threshold: -3% / -2%
- Block second slot in AMBER: نعم / لا

## بروتوكول الاختيار

- Validation 2023
- Validation 2024
- Final research period 2025–Feb 2026 لا يُستخدم في اختيار الإعداد

شروط النجاح في كل سنة Validation:

- Ending wealth >= 97% من v3.2
- Max Drawdown reduction >= 10%
- Active-week >=2% hit-rate >= 90% من v3.2

## النتيجة

**0 من 256 تركيبة اجتازت الشروط الثلاثة معًا.**

أفضل Near Miss خفّض الـDrawdown بوضوح لكنه قص العائد أكثر من المطلوب:

### 2023
- v3.2 return: +38.78%
- near-miss return: +34.86%
- v3.2 DD: -6.50%
- near-miss DD: -5.09%

### 2024
- v3.2 return: +46.22%
- near-miss return: +27.43%
- v3.2 DD: -11.17%
- near-miss DD: -8.84%

أسوأ مشكلة ظهرت في 2024: منع المركز الثاني بعد الخسارة خفّض التراجع، لكنه منع أيضًا صفقات كانت ضرورية لتعافي العائد. أفضل Near Miss احتفظ فقط بحوالي 87.15% من ثروة v3.2 في أضعف سنة، أقل بكثير من شرط 97%.

## الاستنتاج

Loss clustering حقيقي كمشكلة محفظة، لكن **State Machine بعد الخسارة متأخرة زمنيًا**: هي تتصرف فقط بعد وقوع الضرر، ثم تمنع مخاطرة لاحقة قد تكون رابحة. لذلك هي تحسن DD عن طريق حذف جزء من recovery/right-tail، أي نفس المفاضلة التي رفضناها في النسخ السابقة.

هذا يرفض فكرة `post-loss blocking` كحل رئيسي.

## القرار

`v5.3` لا تستبدل `v3.2`.

الاتجاه التالي يجب أن يحاول اكتشاف **الخطر قبل وقوع أول خسارة**، لكن بقواعد قليلة وثابتة، أو يعيد تصميم توزيع المركزين بطريقة لا تخفض إجمالي التعرض المتوقع للفرص القوية.

## الملفات

- `backtest_v53_loss_cluster_state.py`
- `results_v53_loss_cluster_state.json`
- `DEFENSIVE_LIFT_V53.md`

الـBacktest ليس ضمانًا للأداء المستقبلي، والبيانات التاريخية اليومية لا تمثل فجوات التنفيذ والانزلاق بالكامل.
