# EGX Multi-Engine Weekly Return Portfolio — Version 4.0 (Rejected)

## الحالة

**Status: Rejected Research Version**

## الهدف

رفع معدل دوران رأس المال وعدد الأسابيع النشطة بدل محاولة استخراج +2% أسبوعيًا من Defensive Lift وحدها عن طريق زيادة حجم المخاطرة.

## المحركات المختبرة

| Engine | الفكرة | Target | Stop | Horizon |
|---|---|---:|---:|---:|
| DLP | Defensive Lift v2 | +12% | -4.5% | 7 |
| BRT | Breakout + Retest confirmation | +10% | -4% | 7 |
| PBC | Pullback Continuation داخل اتجاه صاعد | +8% | -3.5% | 7 |
| FBR | Failed Breakdown Reclaim | +8% | -3.5% | 7 |

تم تثبيت قواعد الإشارات أولًا ثم اختبار Portfolio Risk Grid منفصل على 2023 و2024 فقط.

## حجم البحث

```text
Stocks = 198
Total raw signals = 2,609
Portfolio configurations tested = 216
```

## جودة كل محرك منفردًا

### DLP

- 2023: Positive 59.38%، Avg gross +3.33%.
- 2024: Positive 45.45%، Avg gross +2.19%.
- Final 2025–Feb 2026: Positive 50.72%، Avg gross +2.54%.

### BRT

- 2023: Positive 39.02%، Avg gross +0.87%.
- 2024: Positive 32.27%، Avg gross +0.08%.
- Final: Positive 42.27%، Avg gross +0.82%.

### PBC

- 2023: Positive 38.21%، Avg gross +0.77%.
- 2024: Positive 43.56%، Avg gross +1.10%.
- Final: Positive 36.22%، Avg gross +0.40%.

### FBR

- 2023: Avg gross **-0.84%**.
- 2024: Avg gross +0.59%.
- Final: Avg gross +0.58%.

FBR فشل في الثبات عبر الفترات، وBRT/PBC في تعريفهما الأول كانا أضعف بكثير من DLP.

## Portfolio Grid

تم اختبار:

- Risk per trade: 0.75% و1%.
- Max open risk: 2% / 2.5% / 3%.
- Max positions: 3 / 4 / 5.
- Max position size: 25% / 30% / 35%.
- Weekly loss lock: بدون / 2% / 2.5% / 3%.

شرط أساسي: Max Drawdown <= 10% في كل من 2023 و2024.

## النتيجة

```text
Eligible portfolio configurations = 0
```

إضافة عدد كبير من الإشارات الضعيفة رفعت النشاط لكنها لم تعطِ جودة Risk/Return كافية. زيادة عدد الصفقات **ليست بديلًا عن جودة الإشارة**.

## القرار

تم رفض v4.0. النسخة التالية `v4.1` لا تضيف محركات أكثر؛ بل تقوم بعمل **Quality Gate** للمحركات الثانوية:

1. استبعاد FBR من المحفظة الأساسية.
2. تشديد BRT لتجنب الاختراقات الممتدة/الريتست الضعيف.
3. تشديد PBC ليكون داخل اتجاه صاعد أقوى وبـpullback أنظف.
4. اختبار Subsets بدل إجبار كل المحركات على العمل معًا.
5. إبقاء DLP هو Core Engine وعدم السماح لمحرك ثانوي بإفساد الـRisk/Return.

## الملفات

- `backtest_v40_multiengine.py`
- `results_v40_multiengine.json`
- `EGX_MULTI_ENGINE_V40.md`
