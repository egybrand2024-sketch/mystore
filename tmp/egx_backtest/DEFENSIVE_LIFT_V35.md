# Defensive Lift — Version 3.5 Profit Preservation Risk Engine (Rejected)

## الحالة

**Status: Rejected Research Version**

## الهدف

تقليل الـDrawdown بدون خفض الهدف +12% أو تقليل تركيز رأس المال الخاص بـv3.2. الفكرة كانت رفع الوقف تدريجيًا فقط بعد أن تثبت الصفقة نفسها سعريًا، بدل تصغير حجم المركز من البداية.

## الثوابت

```text
Entry       = Defensive Lift v2
Target      = +12%
Initial Stop= -4.5%
Horizon     = 7 sessions
Portfolio   = 2 slots
Friction    = 0.50% round-trip sensitivity assumption
```

## الآلية المختبرة

تم اختبار 960 تركيبة من:

- Protect Trigger: +2% / +3% / +4% / +5%.
- أول Stop مرفوع: -2% / -1% / 0% / +1%.
- Profit-Lock Trigger: +6% / +8% / +10%.
- Profit-Lock Stop: +2% / +3% / +4% / +5%.
- Weekly Loss Lock: بدون / 1.5% / 2% / 2.5% / 3%.

## شرط القبول قبل فتح الـFinal

في **كل من 2023 و2024** كان المطلوب معًا:

1. الاحتفاظ بما لا يقل عن 98% من Ending Wealth لـv3.2.
2. تخفيض Max Drawdown بما لا يقل عن 10% مقارنة بـv3.2.

## النتيجة

```text
Tested configurations = 960
Eligible configurations = 0
```

لم توجد تركيبة تحقق الشرطين في السنتين معًا، ولذلك لم يتم اختيار إعداد بالاعتماد على فترة 2025–Feb 2026.

## ما تعلمناه

رفع الوقف آليًا بعد مكسب صغير يقلل بعض الخسائر، لكنه أيضًا يطرد عددًا من الصفقات التي كانت ستعود لاحقًا وتحقق +12%. في العينة الحالية لا توجد قاعدة Dynamic Stop بسيطة حافظت على عائد v3.2 تقريبًا كاملًا وفي نفس الوقت خفضت الـDrawdown 10%+ بشكل ثابت في 2023 و2024.

## مقياس الربح الأسبوعي للـBaseline v3.2

قبل بناء النظام متعدد الاستراتيجيات، تم قياس v3.2 نفسها أسبوعيًا:

| Period | Avg Weekly | Positive Weeks | Week-end >= +2% | Hit +2% anytime |
|---|---:|---:|---:|---:|
| 2023 | +0.64% | 32.08% | 18.87% | 22.64% |
| 2024 | +0.77% | 26.92% | 19.23% | 23.08% |
| 2025–Feb 2026 Holdout | +0.98% | 43.10% | 27.59% | 32.76% |

الـMedian الأسبوعي = 0% بسبب وجود أسابيع كثيرة بلا إشارات/تعرض كافٍ. لذلك **استهداف متوسط قريب من 2% أسبوعيًا لا يمكن حله فقط بتعديل Stop أو Position Sizing لـDLP**؛ نحتاج زيادة عدد الفرص المستقلة بدل زيادة الخطر على نفس النوع من الإشارة.

## القرار

تم رفض v3.5 كنسخة تشغيلية. الانتقال إلى `v4.0 Multi-Engine Portfolio`: دمج عدة Setup Families مستقلة نسبيًا لتقليل الأسابيع الخاملة، مع Risk Budget أقل لكل صفقة وعدم زيادة إجمالي الخطر بشكل غير محسوب.

## الملفات

- `backtest_v35_profit_preservation.py`
- `results_v35_profit_preservation.json`
- `DEFENSIVE_LIFT_V35.md`
