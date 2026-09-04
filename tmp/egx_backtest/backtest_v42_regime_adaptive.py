import glob,json,os,sys
from collections import defaultdict
from datetime import datetime,timedelta
sys.path.insert(0,"tmp/egx_backtest")
import backtest_v3_ml as v3

VAL1=("2023-01-01","2023-12-31");VAL2=("2024-01-01","2024-12-31");FINAL=("2025-01-01","2026-02-28")
INITIAL=100000.0;FRICTION=0.005;TARGET=0.12;STOP=0.045;HORIZON=7;WEEKLY_TARGET=0.02
MARKET20_THRESH=[-0.02,0.0,0.02,0.04]
BREADTH_THRESH=[0.45,0.50,0.55]
NEUTRAL_SIZE=[0.25,0.35,0.50]
WEAK_SIZE=[0.0,0.15,0.25]
WEEKLY_LOCK=[None,0.02,0.025,0.03]
MIN_WEALTH_RATIO=0.95;MIN_DD_REDUCTION=0.15


def in_period(d,p):return p[0]<=d<=p[1]
def week_start(s):
 d=datetime.fromisoformat(s).date();return (d-timedelta(days=(d.weekday()+1)%7)).isoformat()
def collect(sym,rows,market):
 out=[];nxt=60;t=60
 while t<len(rows)-HORIZON:
  if t<nxt:t+=1;continue
  ms=[]
  for n in range(v3.MIN_BASE,v3.MAX_BASE+1):
   c=v3.v1_candidate(rows,t,n)
   if c:ms.append(c)
  if ms:
   c=max(ms,key=lambda x:x["base_n"]);s=v3.make_signal(sym,rows,t,c,market)
   if s and s["v2_flag"]>0:
    out.append({"symbol":sym,"entry_date":rows[t]["date"],"entry":rows[t]["close"],"liquidity":c["median_base_value"],"market20":s["market20_ret"],"breadth20":s["market_breadth20"],"market5":s["market5_ret"],"rs20":s["rs20"],"future":rows[t+1:t+1+HORIZON]});nxt=t+11
  t+=1
 return out

def finalize(x):
 e=x["entry"];tgt=e*(1+TARGET);stp=e*(1-STOP);f=x["future"]
 for i,d in enumerate(f,1):
  if d["low"]<=stp:return {**{k:x[k] for k in ["symbol","entry_date","entry","liquidity","market20","breadth20","market5","rs20"]},"exit_date":d["date"],"exit_price":stp,"gross_return":-STOP,"holding":i}
  if d["high"]>=tgt:return {**{k:x[k] for k in ["symbol","entry_date","entry","liquidity","market20","breadth20","market5","rs20"]},"exit_date":d["date"],"exit_price":tgt,"gross_return":TARGET,"holding":i}
 d=f[-1];return {**{k:x[k] for k in ["symbol","entry_date","entry","liquidity","market20","breadth20","market5","rs20"]},"exit_date":d["date"],"exit_price":d["close"],"gross_return":d["close"]/e-1,"holding":HORIZON}
def maxdd(curve):
 peak=-1;m=0;pd=td=None;rp=None
 for r in curve:
  e=r["equity"]
  if e>peak:peak=e;rp=r["date"]
  dd=e/peak-1 if peak>0 else 0
  if dd<m:m=dd;pd=rp;td=r["date"]
 return m,pd,td
def weekly(curve):
 by=defaultdict(list)
 for r in curve:by[week_start(r["date"])].append(r)
 prev=INITIAL;vals=[];hit=0
 for wk in sorted(by):
  a=by[wk];end=a[-1]["equity"];ret=end/prev-1;mx=max(x["equity"] for x in a)/prev-1;vals.append(ret);hit+=mx>=WEEKLY_TARGET;prev=end
 return {"weeks":len(vals),"avg":sum(vals)/len(vals) if vals else 0,"median":sorted(vals)[len(vals)//2] if vals else 0,"positive_rate":sum(x>0 for x in vals)/len(vals) if vals else 0,"weekend_ge_2_rate":sum(x>=WEEKLY_TARGET for x in vals)/len(vals) if vals else 0,"hit_2_anytime_rate":hit/len(vals) if vals else 0,"worst":min(vals) if vals else 0,"best":max(vals) if vals else 0}
def maps(data):
 c={};ds=set()
 for s,rs in data.items():c[s]={r["date"]:r["close"] for r in rs};ds.update(c[s])
 return c,sorted(ds)
def regime_size(tr,cfg):
 good_m=tr["market20"]>=cfg["market20_thresh"];good_b=tr["breadth20"]>=cfg["breadth_thresh"]
 if good_m and good_b:return 0.50,"strong"
 if good_m or good_b:return cfg["neutral_size"],"neutral"
 return cfg["weak_size"],"weak"
def simulate(trades,closes,dates,p,cfg):
 eb=defaultdict(list);xb=defaultdict(list)
 for t in trades:eb[t["entry_date"]].append(t);xb[t["exit_date"]].append(t)
 for d in eb:eb[d].sort(key=lambda x:(-x["liquidity"],x["symbol"]))
 ds=[d for d in dates if p[0]<=d<=p[1]];half=FRICTION/2;cash=INITIAL;pos={};last={};curve=[];real=[];skip=0;wk=None;wk0=INITIAL;locked=False;states=defaultdict(int)
 def mark(d):
  pv=0
  for s,q in pos.items():
   px=closes.get(s,{}).get(d)
   if px is not None:last[s]=px
   pv+=q["shares"]*last.get(s,q["entry"])
  return cash+pv,pv
 for d in ds:
  w=week_start(d)
  if w!=wk:eq0,_=mark(d);wk=w;wk0=eq0;locked=False
  for s in list(pos):
   px=closes.get(s,{}).get(d)
   if px is not None:last[s]=px
  for tr in sorted(xb.get(d,[]),key=lambda x:x["symbol"]):
   s=tr["symbol"]
   if s not in pos:continue
   q=pos.pop(s);proceeds=q["shares"]*tr["exit_price"]*(1-half);cash+=proceeds;real.append(proceeds/q["budget"]-1)
  eq,_=mark(d)
  if cfg["weekly_lock"] is not None and eq/wk0-1<=-cfg["weekly_lock"]:locked=True
  for tr in eb.get(d,[]):
   if locked or tr["symbol"] in pos or len(pos)>=2:skip+=1;continue
   frac,state=regime_size(tr,cfg);states[state]+=1
   if frac<=0:skip+=1;continue
   eq,_=mark(d);budget=min(eq*frac,cash)
   if budget<=1:skip+=1;continue
   invested=budget*(1-half);shares=invested/tr["entry"];cash-=budget;pos[tr["symbol"]]={"shares":shares,"entry":tr["entry"],"budget":budget};last[tr["symbol"]]=tr["entry"]
  eq,pv=mark(d);curve.append({"date":d,"equity":eq,"exposure":pv/eq if eq else 0,"open":len(pos)})
 m,pd,td=maxdd(curve);final=curve[-1]["equity"];d0=datetime.fromisoformat(curve[0]["date"]).date();d1=datetime.fromisoformat(curve[-1]["date"]).date();yrs=max((d1-d0).days/365.25,1/365.25)
 return {"trades":len(real),"skipped":skip,"final_equity":final,"total_return":final/INITIAL-1,"cagr":(final/INITIAL)**(1/yrs)-1,"max_drawdown":m,"dd_peak":pd,"dd_trough":td,"avg_trade_return":sum(real)/len(real) if real else 0,"weekly":weekly(curve),"avg_exposure":sum(x["exposure"] for x in curve)/len(curve),"entry_states":dict(states)}
def baseline(trades,closes,dates,p):
 return simulate(trades,closes,dates,p,{"market20_thresh":-999,"breadth_thresh":-999,"neutral_size":0.5,"weak_size":0.5,"weekly_lock":None})
def main():
 root=os.environ.get("EGX_DATA_ROOT","egxdata/Dataset/raw");files=sorted(glob.glob(os.path.join(root,"*","*.csv")));data={}
 for fp in files:
  s=os.path.basename(fp).split(".")[0].upper();r=v3.load_csv_all(fp)
  if len(r)>=100:data[s]=r
 market=v3.build_market_maps(data);raw=[]
 for s,r in data.items():raw+=collect(s,r,market)
 tr=[finalize(x) for x in raw];closes,dates=maps(data)
 def tp(p):return [x for x in tr if in_period(x["entry_date"],p) and x["exit_date"]<=p[1]]
 b23=baseline(tp(VAL1),closes,dates,VAL1);b24=baseline(tp(VAL2),closes,dates,VAL2);bf=baseline(tp(FINAL),closes,dates,FINAL)
 ranked=[];tested=0
 for mt in MARKET20_THRESH:
  for bt in BREADTH_THRESH:
   for ns in NEUTRAL_SIZE:
    for ws in WEAK_SIZE:
     if ws>ns:continue
     for wl in WEEKLY_LOCK:
      tested+=1;cfg={"market20_thresh":mt,"breadth_thresh":bt,"neutral_size":ns,"weak_size":ws,"weekly_lock":wl}
      a=simulate(tp(VAL1),closes,dates,VAL1,cfg);b=simulate(tp(VAL2),closes,dates,VAL2,cfg)
      wr1=(1+a["total_return"])/(1+b23["total_return"]);wr2=(1+b["total_return"])/(1+b24["total_return"])
      dr1=1-abs(a["max_drawdown"])/abs(b23["max_drawdown"]);dr2=1-abs(b["max_drawdown"])/abs(b24["max_drawdown"])
      if min(wr1,wr2)<MIN_WEALTH_RATIO or min(dr1,dr2)<MIN_DD_REDUCTION:continue
      score=min(a["cagr"],b["cagr"]);ranked.append({"config":cfg,"2023":a,"2024":b,"min_wealth_ratio":min(wr1,wr2),"min_dd_reduction":min(dr1,dr2),"min_cagr":score,"min_week_avg":min(a["weekly"]["avg"],b["weekly"]["avg"])})
 ranked.sort(key=lambda x:(x["min_cagr"],x["min_week_avg"],x["min_dd_reduction"],x["min_wealth_ratio"]),reverse=True)
 best=ranked[0] if ranked else None;fin=simulate(tp(FINAL),closes,dates,FINAL,best["config"]) if best else None
 result={"pattern":"Defensive Lift v4.2 Regime-Adaptive Exposure","goal":"keep full 50% slot size in favorable market regimes and reduce exposure only in weak regimes","protocol":{"validation_2023":VAL1,"validation_2024":VAL2,"final_holdout":FINAL,"final_not_used_for_selection":True,"min_ending_wealth_ratio_vs_v32":MIN_WEALTH_RATIO,"min_drawdown_reduction_vs_v32":MIN_DD_REDUCTION},"baseline_v32":{"2023":b23,"2024":b24,"final":bf},"grid":{"tested":tested,"eligible":len(ranked)},"selected":best,"final_result":fin,"top20":ranked[:20]}
 if fin:result["comparison_final"]={"return_wealth_ratio":(1+fin["total_return"])/(1+bf["total_return"]),"drawdown_reduction":1-abs(fin["max_drawdown"])/abs(bf["max_drawdown"]),"weekly_avg_change":fin["weekly"]["avg"]-bf["weekly"]["avg"],"weekend_2_rate_change":fin["weekly"]["weekend_ge_2_rate"]-bf["weekly"]["weekend_ge_2_rate"]}
 with open("tmp/egx_backtest/results_v42_regime_adaptive.json","w",encoding="utf-8") as f:json.dump(result,f,ensure_ascii=False,indent=2)
 print(json.dumps({k:result.get(k) for k in ["pattern","baseline_v32","grid","selected","final_result","comparison_final"]},ensure_ascii=False,indent=2))
if __name__=="__main__":main()
