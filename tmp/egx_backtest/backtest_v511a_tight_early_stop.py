from backtest_v511_common import run_family
configs=[]
for es in [0.025,0.03,0.035,0.04]:
  for days in [1,2]:
    for rm in [0.01,0.015,0.02,0.025,None]:
      configs.append({'early_stop':es,'stop_days':days,'relax_mfe':rm})
run_family('v5.11A','Tight Early Stop Hazard Protection','A',configs,'tmp/egx_backtest/results_v511a_tight_early_stop.json')
