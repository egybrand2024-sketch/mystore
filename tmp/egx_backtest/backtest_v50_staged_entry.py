import glob,json,os,sys,statistics
from collections import defaultdict
from datetime import datetime,timedelta
sys.path.insert(0,"tmp/egx_backtest")
import backtest_v3_ml as v3

VAL1=("2023-01-01","2023-12-31");VAL2=("2024-01-01","2024-12-31");FINAL=("2025-01-01","2026-02-28")
INITIAL=100000.0;FRICTION=0.005
TARGET=0.12;BREAKOUT_STOP=0.045;POST_BREAK_H=7
PRE_FRACTIONS=[0.15,0.20,0.25]
ADD_FRACTIONS=[0.25,0.30,0.35]
PRE_STOPS=[0.02,0.025,0.03]
EXPIRIES=[2,3,4]
DIST_MAX=[0.015,0.02,0.03]
MIN_DD_IMPROVEMENT=0.10
MIN_WEALTH_RATIO=0.95
WEEKLY_TARGET=0.02

def mean(x):return sum(x)/len(x) if x else 0.0
def med(x):return statistics.median(x) if x else 0.0
def in_period(d,p):return p[0]<=d<=p[1]
def week_start(s):
 d=datetime.fromisoformat(s).date();return (d-timedelta(days=(d.weekday()+1)%7)).isoformat()
def clv(r):
 z=r["high"]-r["low"];return (r["close"]-r["low"])/z if z>0 else 0.5

def mature_precursor(rows,t,dist_max):
 # Same core DLP base logic, but BEFORE breakout. Must be close to resistance and still below it.
 matches=[]
 for n in range(v3.MIN_BASE,v3.MAX_BASE+1):
  if t-n+1<0:continue
  base=rows[t-n+1:t+1]
  low=min(x["low"] for x in base);high=max(x["high"] for x in base)
  if low<=0 or (high-low)/low>0.08:continue
  closes=[x["close"] for x in base]
  mini=min(range(len(closes)),key=lambda i:closes[i])
  if mini>=len(base)-3:continue
  lift=base[-1]["close"]/low-1
  if not(0.03<=lift<=0.08):continue
  if min(x["low"] for x in base[-3:])<=min(x["low"] for x in base[:-3]):continue
  mv=med([x["volume"] for x in base]);avg3=mean([x["volume"] for x in base[-3:]])
  if mv<=0 or avg3<1.5*mv:continue
  c=base[-1]["close"]
  # resistance should pre-exist: exclude today's high from level.
  prior_high=max(x["high"] for x in base[:-1]) if len(base)>1 else high
  if not(c<prior_high and 0<prior_high/c-1<=dist_max):continue
  matches.append({"base_n":n,"low":low,"resistance":prior_high,"median_vol":mv,"median_value":med([x["close"]*x["volume"] for x in base])})
 return max(matches,key=lambda x:x["base_n"]) if matches else None

def breakout_quality(rows,t,resistance,median_vol):
 if t<=0:return False
 r=rows[t];p=rows[t-1];rng=max(r["high"]-r["low"],1e-12);body=(r["close"]-r["open"])/r["open"]
 if r["close"]<=resistance:return False
 if body<0.02:return False
 if (r["close"]-r["low"])/rng<0.55:return False
 ret=r["close"]/p["close"]-1
 if ret<0 or ret>0.06:return False
 if median_vol<=0 or r["volume"]<2.0*median_vol:return False
 # approximate v2 pre20 trend safeguard.
 if t>=20 and p["close"]/rows[t-20]["close"]-1<-0.03:return False
 return True

def build_trades(sym,rows,cfg):
 out=[];last_entry=-99;t=60
 while t<len(rows)-POST_BREAK_H-cfg["expiry"]-1:
  if t-last_entry<8:t+=1;continue
  pre=mature_precursor(rows,t,cfg["dist_max"])
  if not pre:t+=1;continue
  entry=rows[t]["close"];pre_stop=entry*(1-cfg["pre_stop"]);break_t=None;exit_t=None;exit_price=None;kind=None
  # Monitor precursor until stop / breakout / expiry. Same-bar stop first.
  for k in range(1,cfg["expiry"]+1):
   d=rows[t+k]
   if d["low"]<=pre_stop:
    exit_t=t+k;exit_price=pre_stop;kind="pre_stop";break
   if breakout_quality(rows,t+k,pre["resistance"],pre["median_vol"]):
    break_t=t+k;break
  if break_t is None and exit_t is None:
   exit_t=t+cfg["expiry"];exit_price=rows[exit_t]["close"];kind="pre_timeout"
  if break_t is None:
   out.append({"symbol":sym,"entry_date":rows[t]["date"],"pre_entry":entry,"pre_fraction":cfg["pre_fraction"],"add_fraction":0.0,"breakout_date":None,"breakout_entry":None,"exit_date":rows[exit_t]["date"],"pre_exit_price":exit_price,"break_exit_price":None,"kind":kind,"liquidity":pre["median_value"]})
   last_entry=t;t+=1;continue
  # Breakout confirmed. Add second tranche and manage both to +12% target from breakout, -4.5% stop from breakout, 7 sessions.
  be=rows[break_t]["close"];tgt=be*(1+TARGET);stp=be*(1-BREAKOUT_STOP);ex=None;px=None;kind="post_timeout"
  for k in range(1,POST_BREAK_H+1):
   d=rows[break_t+k]
   if d["low"]<=stp:ex=break_t+k;px=stp;kind="post_stop";break
   if d["high"]>=tgt:ex=break_t+k;px=tgt;kind="target";break
  if ex is None:ex=break_t+POST_BREAK_H;px=rows[ex]["close"]
  out.append({"symbol":sym,"entry_date":rows[t]["date"],"pre_entry":entry,"pre_fraction":cfg["pre_fraction"],"add_fraction":cfg["add_fraction"],"breakout_date":rows[break_t]["date"],"breakout_entry":be,"exit_date":rows[ex]["date"],"pre_exit_price":px,"break_exit_price":px,"kind":kind,"liquidity":pre["median_value"]})
  last_entry=t;t=ex+1
 return out

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
  a=by[wk];ret=a[-1]["equity"]/prev-1;mx=max(x["equity"] for x in a)/prev-1;vals.append(ret);hit+=mx>=WEEKLY_TARGET;prev=a[-1]["equity"]
 return {"weeks":len(vals),"avg":mean(vals),"median":med(vals),"positive_rate":sum(x>0 for x in vals)/len(vals) if vals else 0,"weekend_ge_2_rate":sum(x>=WEEKLY_TARGET for x in vals)/len(vals) if vals else 0,"hit_2_anytime_rate":hit/len(vals) if vals else 0,"worst":min(vals) if vals else 0,"best":max(vals) if vals else 0}
def price_maps(data):
 m={};dates=set()
 for s,rs in data.items():m[s]={r["date"]:r["close"] for r in rs};dates.update(m[s])
 return m,sorted(dates)

def simulate(trades,data,p):
 # Two portfolio slots maximum. A staged trade reserves only actual deployed fractions; unused cash remains free.
 by_entry=defaultdict(list);by_break=defaultdict(list);by_exit=defaultdict(list)
 for x in trades:
  by_entry[x["entry_date"]].append(x)
  if x["breakout_date"]:by_break[x["breakout_date"]].append(x)
  by_exit[x["exit_date"]].append(x)
 for d in by_entry:by_entry[d].sort(key=lambda x:(-x["liquidity"],x["symbol"]))
 closes,dates=price_maps(data);dates=[d for d in dates if p[0]<=d<=p[1]];half=FRICTION/2;cash=INITIAL;pos={};last={};curve=[];real=[];skip=0
 def mark(d):
  pv=0
  for key,q in pos.items():
   px=closes.get(q["symbol"],{}).get(d)
   if px is not None:last[q["symbol"]]=px
   pv+=q["pre_shares"]*last.get(q["symbol"],q["pre_entry"])
   if q.get("add_shares",0):pv+=q["add_shares"]*last.get(q["symbol"],q["breakout_entry"])
  return cash+pv,pv
 for d in dates:
  # exits first
  for tr in sorted(by_exit.get(d,[]),key=lambda x:x["symbol"]):
   key=(tr["symbol"],tr["entry_date"])
   if key not in pos:continue
   q=pos.pop(key);proceeds=q["pre_shares"]*tr["pre_exit_price"]*(1-half)
   if q.get("add_shares",0):proceeds+=q["add_shares"]*tr["break_exit_price"]*(1-half)
   cash+=proceeds;real.append(proceeds/q["cash_spent"]-1)
  # stage B adds, if position survived and cash available
  for tr in by_break.get(d,[]):
   key=(tr["symbol"],tr["entry_date"])
   if key not in pos:continue
   q=pos[key];eq,_=mark(d);desired=eq*tr["add_fraction"];budget=min(desired,cash)
   if budget<=1:continue
   invested=budget*(1-half);q["add_shares"]=invested/tr["breakout_entry"];q["breakout_entry"]=tr["breakout_entry"];q["cash_spent"]+=budget;cash-=budget
  # new precursor entries; max two active staged ideas
  for tr in by_entry.get(d,[]):
   if len(pos)>=2 or any(q["symbol"]==tr["symbol"] for q in pos.values()):skip+=1;continue
   eq,_=mark(d);budget=min(eq*tr["pre_fraction"],cash)
   if budget<=1:skip+=1;continue
   invested=budget*(1-half);key=(tr["symbol"],tr["entry_date"]);pos[key]={"symbol":tr["symbol"],"pre_entry":tr["pre_entry"],"pre_shares":invested/tr["pre_entry"],"add_shares":0.0,"cash_spent":budget};cash-=budget;last[tr["symbol"]]=tr["pre_entry"]
  eq,pv=mark(d);curve.append({"date":d,"equity":eq,"exposure":pv/eq if eq else 0,"open":len(pos)})
 if not curve:return None
 m,pd,td=maxdd(curve);final=curve[-1]["equity"];d0=datetime.fromisoformat(curve[0]["date"]).date();d1=datetime.fromisoformat(curve[-1]["date"]).date();yrs=max((d1-d0).days/365.25,1/365.25)
 return {"trades":len(real),"skipped":skip,"final_equity":final,"total_return":final/INITIAL-1,"cagr":(final/INITIAL)**(1/yrs)-1,"max_drawdown":m,"dd_peak":pd,"dd_trough":td,"avg_trade_return":mean(real),"positive_trade_rate":sum(x>0 for x in real)/len(real) if real else 0,"weekly":weekly(curve),"avg_exposure":mean([x["exposure"] for x in curve])}

def baseline_v32(data,market,p):
 # Reuse confirmed DLP only; 2x50% slots, +12/-4.5/7.
 raw=[]
 for s,rows in data.items():
  nxt=60;t=60
  while t<len(rows)-7:
   if t<nxt:t+=1;continue
   ms=[]
   for n in range(v3.MIN_BASE,v3.MAX_BASE+1):
    c=v3.v1_candidate(rows,t,n)
    if c:ms.append(c)
   if ms:
    c=max(ms,key=lambda x:x["base_n"]);sig=v3.make_signal(s,rows,t,c,market)
    if sig and sig["v2_flag"]>0:
     e=rows[t]["close"];f=rows[t+1:t+8];tgt=e*(1+TARGET);stp=e*(1-BREAKOUT_STOP);ex=None;px=None
     for k,d in enumerate(f,1):
      if d["low"]<=stp:ex=t+k;px=stp;break
      if d["high"]>=tgt:ex=t+k;px=tgt;break
     if ex is None:ex=t+7;px=rows[ex]["close"]
     if in_period(rows[t]["date"],p) and rows[ex]["date"]<=p[1]:raw.append({"symbol":s,"entry_date":rows[t]["date"],"exit_date":rows[ex]["date"],"entry":e,"exit":px,"liq":c["median_base_value"]})
     nxt=t+11
   t+=1
 # simple 2-slot simulation
 eb=defaultdict(list);xb=defaultdict(list)
 for x in raw:eb[x["entry_date"]].append(x);xb[x["exit_date"]].append(x)
 for d in eb:eb[d].sort(key=lambda x:(-x["liq"],x["symbol"]))
 closes,dates=price_maps(data);dates=[d for d in dates if p[0]<=d<=p[1]];half=FRICTION/2;cash=INITIAL;pos={};last={};curve=[];real=[]
 def mark(d):
  pv=0
  for s,q in pos.items():
   px=closes.get(s,{}).get(d)
   if px is not None:last[s]=px
   pv+=q["shares"]*last.get(s,q["entry"])
  return cash+pv,pv
 for d in dates:
  for x in xb.get(d,[]):
   if x["symbol"] not in pos:continue
   q=pos.pop(x["symbol"]);proc=q["shares"]*x["exit"]*(1-half);cash+=proc;real.append(proc/q["budget"]-1)
  for x in eb.get(d,[]):
   if len(pos)>=2 or x["symbol"] in pos:continue
   eq,_=mark(d);budget=min(eq/2,cash);invested=budget*(1-half);pos[x["symbol"]]={"shares":invested/x["entry"],"entry":x["entry"],"budget":budget};cash-=budget;last[x["symbol"]]=x["entry"]
  eq,pv=mark(d);curve.append({"date":d,"equity":eq,"exposure":pv/eq if eq else 0})
 m,pd,td=maxdd(curve);final=curve[-1]["equity"];d0=datetime.fromisoformat(curve[0]["date"]).date();d1=datetime.fromisoformat(curve[-1]["date"]).date();yrs=max((d1-d0).days/365.25,1/365.25)
 return {"trades":len(real),"final_equity":final,"total_return":final/INITIAL-1,"cagr":(final/INITIAL)**(1/yrs)-1,"max_drawdown":m,"weekly":weekly(curve)}

def main():
 root=os.environ.get("EGX_DATA_ROOT","egxdata/Dataset/raw");files=sorted(glob.glob(os.path.join(root,"*","*.csv")));data={}
 for fp in files:
  s=os.path.basename(fp).split(".")[0].upper();r=v3.load_csv_all(fp)
  if len(r)>=100:data[s]=r
 market=v3.build_market_maps(data);base={p[0]:baseline_v32(data,market,p) for p in [VAL1,VAL2,FINAL]}
 ranked=[];tested=0
 for pf in PRE_FRACTIONS:
  for af in ADD_FRACTIONS:
   if pf+af>0.55:continue
   for ps in PRE_STOPS:
    for ex in EXPIRIES:
     for dm in DIST_MAX:
      tested+=1;cfg={"pre_fraction":pf,"add_fraction":af,"pre_stop":ps,"expiry":ex,"dist_max":dm};alltr=[]
      for s,rows in data.items():alltr+=build_trades(s,rows,cfg)
      a=simulate([x for x in alltr if in_period(x["entry_date"],VAL1) and x["exit_date"]<=VAL1[1]],data,VAL1);b=simulate([x for x in alltr if in_period(x["entry_date"],VAL2) and x["exit_date"]<=VAL2[1]],data,VAL2)
      if not a or not b:continue
      wr1=(1+a["total_return"])/(1+base[VAL1[0]]["total_return"]);wr2=(1+b["total_return"])/(1+base[VAL2[0]]["total_return"])
      dr1=1-abs(a["max_drawdown"])/abs(base[VAL1[0]]["max_drawdown"]);dr2=1-abs(b["max_drawdown"])/abs(base[VAL2[0]]["max_drawdown"])
      row={"config":cfg,"2023":a,"2024":b,"min_wealth_ratio":min(wr1,wr2),"min_dd_reduction":min(dr1,dr2),"min_cagr":min(a["cagr"],b["cagr"]),"min_week_avg":min(a["weekly"]["avg"],b["weekly"]["avg"])}
      if row["min_wealth_ratio"]>=MIN_WEALTH_RATIO and row["min_dd_reduction"]>=MIN_DD_IMPROVEMENT:ranked.append(row)
 ranked.sort(key=lambda x:(x["min_cagr"],x["min_week_avg"],x["min_dd_reduction"],x["min_wealth_ratio"]),reverse=True)
 best=ranked[0] if ranked else None;fin=None
 if best:
  tr=[]
  for s,rows in data.items():tr+=build_trades(s,rows,best["config"])
  fin=simulate([x for x in tr if in_period(x["entry_date"],FINAL) and x["exit_date"]<=FINAL[1]],data,FINAL)
 result={"pattern":"Defensive Lift v5.0 Staged Pre-Breakout Entry","goal":"lower blended entry cost and precursor risk while retaining confirmed-breakout +12% upside","protocol":{"validation_2023":VAL1,"validation_2024":VAL2,"final_holdout":FINAL,"final_not_used_for_selection":True,"min_wealth_ratio_vs_v32":MIN_WEALTH_RATIO,"min_drawdown_reduction_vs_v32":MIN_DD_IMPROVEMENT},"baseline_v32":{"2023":base[VAL1[0]],"2024":base[VAL2[0]],"final":base[FINAL[0]]},"grid":{"tested":tested,"eligible":len(ranked)},"selected":best,"final_result":fin,"top20":ranked[:20]}
 if fin:result["comparison_final"]={"wealth_ratio":(1+fin["total_return"])/(1+base[FINAL[0]]["total_return"]),"drawdown_reduction":1-abs(fin["max_drawdown"])/abs(base[FINAL[0]]["max_drawdown"]),"weekly_avg_change":fin["weekly"]["avg"]-base[FINAL[0]]["weekly"]["avg"],"weekend_ge2_change":fin["weekly"]["weekend_ge_2_rate"]-base[FINAL[0]]["weekly"]["weekend_ge_2_rate"]}
 with open("tmp/egx_backtest/results_v50_staged_entry.json","w",encoding="utf-8") as f:json.dump(result,f,ensure_ascii=False,indent=2)
 print(json.dumps({k:result.get(k) for k in ["pattern","baseline_v32","grid","selected","final_result","comparison_final"]},ensure_ascii=False,indent=2))
if __name__=="__main__":main()
