from backtest_v511_common import run_family
configs=[]
for f in [0.30,0.35,0.40]:
  for d1m in [0.01,0.015,0.02]:
    for pyr in [0.55,0.60,0.65]:
      for d2m in [0.02,0.03,0.04]:
        configs.append({'initial_frac':f,'d1_mfe':d1m,'d1_close':0.0,'pyramid_frac':pyr,'d2_mfe':d2m,'d2_close':0.0})
run_family('v5.11D','Asymmetric Winner Pyramid','D',configs,'tmp/egx_backtest/results_v511d_winner_pyramid.json')
