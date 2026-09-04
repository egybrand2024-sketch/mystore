from backtest_v511_common import run_family
configs=[]
for f in [0.30,0.35,0.40,0.425]:
  for es in [0.025,0.03,0.035]:
    for d1t in [0.45,0.475,0.50]:
      for d1m in [0.01,0.015,0.02]:
        configs.append({'initial_frac':f,'early_stop':es,'stop_days':1,'relax_mfe':0.015,'d1_target':d1t,'d1_mfe':d1m,'d1_close':0.0,'d2_mfe':0.0,'d2_close':0.0})
run_family('v5.11B','Progressive Entry + Temporary Stop','B',configs,'tmp/egx_backtest/results_v511b_progressive_stop.json')
