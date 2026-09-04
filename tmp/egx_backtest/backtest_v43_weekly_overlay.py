import glob,json,os,sys
from collections import defaultdict
from datetime import datetime,timedelta
sys.path.insert(0,"tmp/egx_backtest")
import backtest_v3_ml as v3
import backtest_v42_regime_adaptive as v42

VAL1=v42.VAL1;VAL2=v42.VAL2;FINAL=v42.FINAL
INITIAL=v42.INITIAL;FRICTION=v42.FRICTION
GAIN_LOCKS=[None,0.02,0.03,0.04]
LOSS_LOCKS=[None,0.015,0.02,0.025,0.03]
AFTER_LOSS_SIZE=[0.25,0.35,0.50]
MIN_WEALTH_RATIO=0.95;MIN_DD_REDUCTION=0.10
WEEKLY_TARGET=0.02


def week_start(s):
 d=datetime.fromisoformat(s).date();return (d-timedelta(days=(d.weekday()+1)%7)).isoformat()
def maxdd(curve):return v42.maxdd(curve)
def weekly(curve):return v42.weekly(curve)
def simulate(trades,closes,dates,p,cfg):
 eb=defaultdict(list);xb=defaultdict(list)
 for t in trades:eb[t["entry_date"]].append(t);xb[t["exit_date"]].append(t)
 for d in eb:eb[d].sort(key=lambda x:(-x["liquidity"],x["symbol"]))
 ds=[d for d in dates if p[0]<=d<=p[1]];half=FRICTION/2;cash=INITIAL;pos={};last={};curve=[];real=[];skip=defaultdict(int)
 wk=None;wk0=INITIAL;gain_locked=False;loss_locked=False;week_losses=0
 def mark(d):
  pv=0
  for s,q in pos.items():
   px=closes.get(s,{}).get(d)
   if px is not None:last[s]=px
   pv+=q["shares"]*last.get(s,q["entry"])
  return cash+pv,pv
 for d in ds:
  w=week_start(d)
  if w!=wk:
   eq0,_=mark(d);wk=w;wk0=eq0;gain_locked=False;loss_locked=False;week_losses=0
  for s in list(pos):
   px=closes.get(s,{}).get(d)
   if px is not None:last[s]=px
  for tr in sorted(xb.get(d,[]),key=lambda x:x["symbol"]):
   s=tr["symbol"]
   if s not in pos:continue
   q=pos.pop(s);proceeds=q["shares"]*tr["exit_price"]*(1-half);cash+=proceeds;net=proceeds/q["budget"]-1;real.append(net)
   if net<0:week_losses+=1
  eq,_=mark(d);wr=eq/wk0-1 if wk0>0 else 0
  if cfg["gain_lock"] is not None and wr>=cfg["gain_lock"]:gain_locked=True
  if cfg["loss_lock"] is not None and wr<=-cfg["loss_lock"]:loss_locked=True
  for tr in eb.get(d,[]):
   if tr["symbol"] in pos:skip["duplicate_symbol"]+=1;continue
   if len(pos)>=2:skip["max_positions"]+=1;continue
   if gain_locked:skip["gain_lock"]+=1;continue
   if loss_locked:skip["loss_lock"]+=1;continue
   eq,_=mark(d);frac=0.50 if week_losses==0 else cfg["after_loss_size"];budget=min(eq*frac,cash)
   if budget<=1:skip["cash"]+=1;continue
   invested=budget*(1-half);shares=invested/tr["entry"];cash-=budget;pos[tr["symbol"]]={"shares":shares,"entry":tr["entry"],"budget":budget};last[tr["symbol"]]=tr["entry"]
  eq,pv=mark(d);curve.append({"date":d,"equity":eq,"exposure":pv/eq if eq else 0,"open":len(pos)})
 m,pd,td=maxdd(curve);final=curve[-1]["equity"];d0=datetime.fromisoformat(curve[0]["date"]).date();d1=datetime.fromisoformat(curve[-1]["date"]).date();yrs=max((d1-d0).days/365.25,1/365.25)
 return {"trades":len(real),"skipped":sum(skip.values()),"skip_reasons":dict(skip),"final_equity":final,"total_return":final/INITIAL-1,"cagr":(final/INITIAL)**(1/yrs)-1,"max_drawdown":m,"dd_peak":pd,"dd_trough":td,"avg_trade_return":sum(real)/len(real) if real else 0,"positive_trade_rate":sum(x>0 for x in real)/len(real) if real else 0,"weekly":weekly(curve),"avg_exposure":sum(x["exposure"] for x in curve)/len(curve)}
def baseline(trades,closes,dates,p):return simulate(trades,closes,dates,p,{"gain_lock":None,"loss_lock":None,"after_loss_size":0.50})
def main():
 root=os.environ.get("EGX_DATA_ROOT","egxdata/Dataset/raw");files=sorted(glob.glob(os.path.join(root,"*","*.csv")));data={}
 for fp in files:
  s=os.path.basename(fp).split(".")[0].upper();r=v3.load_csv_all(fp)
  if len(r)>=100:data[s]=r
 market=v3.build_market_maps(data);raw=[]
 for s,r in data.items():raw+=v42.collect(s,r,market)
 tr=[v42.finalize(x) for x in raw];closes,dates=v42.maps(data)
 def tp(p):return [x for x in tr if v42.in_period(x["entry_date"],p) and x["exit_date"]<=p[1]]
 b23=baseline(tp(VAL1),closes,dates,VAL1);b24=baseline(tp(VAL2),closes,dates,VAL2);bf=baseline(tp(FINAL),closes,dates,FINAL)
 allcfg=[];eligible=[]
 for gl in GAIN_LOCKS:
  for ll in LOSS_LOCKS:
   for als in AFTER_LOSS_SIZE:
    cfg={"gain_lock":gl,"loss_lock":ll,"after_loss_size":als};a=simulate(tp(VAL1),closes,dates,VAL1,cfg);b=simulate(tp(VAL2),closes,dates,VAL2,cfg)
    wr1=(1+a["total_return"])/(1+b23["total_return"]);wr2=(1+b["total_return"])/(1+b24["total_return"])
    dr1=1-abs(a["max_drawdown"])/abs(b23["max_drawdown"]);dr2=1-abs(b["max_drawdown"])/abs(b24["max_drawdown"])
    row={"config":cfg,"2023":a,"2024":b,"min_wealth_ratio":min(wr1,wr2),"min_dd_reduction":min(dr1,dr2),"min_cagr":min(a["cagr"],b["cagr"]),"min_week_avg":min(a["weekly"]["avg"],b["weekly"]["avg"])};allcfg.append(row)
    if row["min_wealth_ratio"]>=MIN_WEALTH_RATIO and row["min_dd_reduction"]>=MIN_DD_REDUCTION:eligible.append(row)
 eligible.sort(key=lambda x:(x["min_cagr"],x["min_week_avg"],x["min_dd_reduction"]),reverse=True)
 allcfg.sort(key=lambda x:(x["min_wealth_ratio"]+x["min_dd_reduction"],x["min_cagr"]),reverse=True)
 best=eligible[0] if eligible else None;fin=simulate(tp(FINAL),closes,dates,FINAL,best["config"]) if best else None
 result={"pattern":"Defensive Lift v4.3 Weekly Profit Protection Overlay","goal":"keep normal 50% slot size and +12% target; protect strong weeks by blocking only NEW entries after weekly gain/loss thresholds and optionally cut size only after first weekly loss","protocol":{"validation_2023":VAL1,"validation_2024":VAL2,"final_holdout":FINAL,"final_not_used_for_selection":True,"min_wealth_ratio_vs_v32":MIN_WEALTH_RATIO,"min_drawdown_reduction_vs_v32":MIN_DD_REDUCTION},"baseline_v32":{"2023":b23,"2024":b24,"final":bf},"grid":{"tested":len(allcfg),"eligible":len(eligible)},"selected":best,"final_result":fin,"best_near_misses":allcfg[:10],"top_eligible":eligible[:20]}
 if fin:result["comparison_final"]={"wealth_ratio":(1+fin["total_return"])/(1+bf["total_return"]),"drawdown_reduction":1-abs(fin["max_drawdown"])/abs(bf["max_drawdown"]),"weekly_avg":fin["weekly"]["avg"],"weekend_ge_2_rate":fin["weekly"]["weekend_ge_2_rate"]}
 with open("tmp/egx_backtest/results_v43_weekly_overlay.json","w",encoding="utf-8") as f:json.dump(result,f,ensure_ascii=False,indent=2)
 print(json.dumps({k:result.get(k) for k in ["pattern","baseline_v32","grid","selected","final_result","comparison_final","best_near_misses"]},ensure_ascii=False,indent=2))
if __name__=="__main__":main()
