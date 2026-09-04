from backtest_v511_common import run_family
configs=[]
for level in ['q85','q90']:
  for context in ['market20','breadth','either','both']:
    for pf in [0.30,0.35,0.40]:
      for es in [0.025,0.03,0.035]:
        for pyr in [0.55,0.60]:
          configs.append({'severe_level':level,'context_mode':context,'protected_frac':pf,'early_stop':es,'stop_days':1,'relax_mfe':0.015,'d1_mfe':0.015,'d1_close':0.0,'pyramid_frac':pyr,'d2_mfe':0.025,'d2_close':0.0})
run_family('v5.11E','Adaptive Hybrid: Selective Protection + Pyramid','E',configs,'tmp/egx_backtest/results_v511e_adaptive_hybrid.json')
