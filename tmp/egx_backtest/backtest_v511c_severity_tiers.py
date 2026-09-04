from backtest_v511_common import run_family
configs=[]
for level in ['q85','q90']:
  for severe_frac in [0.25,0.30,0.35]:
    for moderate_frac in [0.40,0.425,0.45,0.475]:
      for d1t in [0.45,0.475,0.50]:
        configs.append({'severe_level':level,'severe_frac':severe_frac,'moderate_frac':moderate_frac,'d1_target':d1t,'d1_mfe':0.015,'d1_close':0.0,'d2_close':0.0})
run_family('v5.11C','Severity-Tier Hazard Staging','C',configs,'tmp/egx_backtest/results_v511c_severity_tiers.json')
