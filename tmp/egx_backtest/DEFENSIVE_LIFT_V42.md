# Defensive Lift — Version 4.2 Regime-Adaptive Exposure (Rejected)

## الحالة

**Status: Rejected Research Version**

## الهدف

الاحتفاظ بحجم v3.2 الكامل في بيئة سوق قوية، وتقليل التعرض فقط عندما يكون Market Regime ضعيفًا، على أمل خفض الـDrawdown بدون خفض الربح.

## البحث

تم استخدام Market 20-session return وMarket breadth proxy لتقسيم الدخول إلى Strong / Neutral / Weak، مع أحجام مختلفة للمركز وWeekly Loss Lock.

```text
Configurations tested = 432
```

شروط القبول في 2023 و2024 معًا:

- الاحتفاظ بما لا يقل عن 95% من Ending Wealth لـv3.2.
- خفض Max Drawdown بما لا يقل عن 15% في كل سنة.

## النتيجة

```text
Eligible = 0
```

لم ينجح أي Regime Filter بسيط في تحقيق الشرطين معًا. بعض الخسائر المهمة في DLP تحدث داخل فترات تبدو سوقيًا مقبولة، وبعض الأرباح القوية تظهر قبل أن يصبح مؤشر الـregime إيجابيًا بوضوح؛ لذلك تقليل التعرض بناءً على فلتر سوق عام قص جزءًا من الأرباح أيضًا.

## Baseline الأسبوعي المحدث لـv3.2

في Final 2025–Feb 2026:

```text
Total Return ≈ +75.86%
CAGR ≈ 67.88%
Max Drawdown ≈ -6.91%
Average calendar-week return ≈ +1.03%
Week-end >= +2% ≈ 31.03% of weeks
Hit +2% at any time during week ≈ 32.76%
```

الاختلاف البسيط عن بعض تقارير v3.2 السابقة ناتج عن طريقة حدود الفترة/الصفقات القريبة من نهاية السنة في محرك المقارنة الجديد، ولذلك يجب مقارنة كل Candidate مع الـBaseline الناتج من **نفس المحرك**.

## القرار

رفض v4.2. الخطوة التالية `v4.3` تختبر Weekly Overlay أبسط وأقرب لهدف المشروع:

- لا نصغر الصفقة العادية من البداية.
- لا نخفض Target +12%.
- نوقف **الدخول الجديد فقط** عندما يتحقق هدف أسبوعي أو حد خسارة أسبوعي.
- بعد أول خسارة أسبوعية يمكن تقليل حجم الصفقة التالية فقط، بدل تقليل كل الصفقات دائمًا.

الفكرة: حماية الربح الأسبوعي وتقليل تتابع الخسائر مع الحفاظ على قوة v3.2 في الأسابيع الجيدة.

## الملفات

- `backtest_v42_regime_adaptive.py`
- `results_v42_regime_adaptive.json`
- `DEFENSIVE_LIFT_V42.md`
