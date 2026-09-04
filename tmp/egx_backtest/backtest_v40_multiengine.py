import glob,json,math,os,sys,statistics
from collections import defaultdict
from datetime import datetime,timedelta
sys.path.insert(0,"tmp/egx_backtest")
import backtest_v3_ml as v3

VAL1=("2023-01-01","2023-12-31");VAL2=("2024-01-01","2024-12-31");FINAL=("2025-01-01","2026-02-28")
INITIAL=100000.0;FRICTION=0.005;WEEKLY_TARGET=0.02
ENGINE_RULES={
 "DLP":{"target":0.12,"stop":0.045,"horizon":7},
 "BRT":{"target":0.10,"stop":0.04,"horizon":7},
 "PBC":{"target":0.08,"stop":0.035,"horizon":7},
 "FBR":{"target":0.08,"stop":0.035,"horizon":7},
}
RISK_PER_TRADE=[0.0075,0.01]
MAX_OPEN_RISK=[0.02,0.025,0.03]
MAX_POSITIONS=[3,4,5]
MAX_POSITION_FRAC=[0.25,0.30,0.35]
WEEKLY_LOSS_LOCK=[None,0.02,0.025,0.03]
MAX_VALIDATION_DD=0.10;MIN_TRADES=25


def mean(xs):return sum(xs)/len(xs) if xs else 0.0
def med(xs):return statistics.median(xs) if xs else 0.0
def in_period(d,p):return p[0]<=d<=p[1]
def week_start(s):
 d=datetime.fromisoformat(s).date();return (d-timedelta(days=(d.weekday()+1)%7)).isoformat()
def clv(r):
 z=r["high"]-r["low"];return (r["close"]-r["low"])/z if z>0 else 0.5

def dlp_signals(sym,rows,market):
 out=[];nxt=60;t=60
 while t<len(rows)-7:
  if t<nxt:t+=1;continue
  ms=[]
  for n in range(v3.MIN_BASE,v3.MAX_BASE+1):
   c=v3.v1_candidate(rows,t,n)
   if c:ms.append(c)
  if ms:
   c=max(ms,key=lambda x:x["base_n"]);s=v3.make_signal(sym,rows,t,c,market)
   if s and s["v2_flag"]>0:
    out.append({"engine":"DLP","symbol":sym,"entry_date":rows[t]["date"],"entry":rows[t]["close"],"liquidity":c["median_base_value"],"future":rows[t+1:t+8]});nxt=t+11
  t+=1
 return out

def brt_signals(sym,rows):
 out=[];last=-99
 for t in range(60,len(rows)-7):
  if t-last<10:continue
  entry=rows[t];prev=rows[t-1];found=None
  for j in range(max(21,t-4),t):
   prior=rows[j-20:j];level=max(x["high"] for x in prior);mv=med([x["volume"] for x in prior]);b=rows[j]
   if b["close"]<=level or b["close"]/rows[j-1]["close"]-1>0.12 or mv<=0 or b["volume"]<1.5*mv:continue
   after=rows[j+1:t+1]
   if not after:continue
   if min(x["low"] for x in after)>level*1.02:continue
   if min(x["close"] for x in after)<level*0.98:continue
   if entry["close"]<=level or entry["close"]<=entry["open"] or entry["close"]<=prev["high"]:continue
   if clv(entry)<0.55:continue
   found=(level,mv);break
  if found:
   liq=med([x["close"]*x["volume"] for x in rows[t-20:t]])
   out.append({"engine":"BRT","symbol":sym,"entry_date":entry["date"],"entry":entry["close"],"liquidity":liq,"future":rows[t+1:t+8]});last=t
 return out

def pbc_signals(sym,rows):
 out=[];last=-99
 for t in range(60,len(rows)-7):
  if t-last<10:continue
  prev=rows[t-1];cur=rows[t];w50=rows[t-50:t];w20=rows[t-20:t];w10=rows[t-10:t]
  sma20=mean([x["close"] for x in w20]);sma50=mean([x["close"] for x in w50]);h10=max(x["high"] for x in w10);ret20=prev["close"]/rows[t-20]["close"]-1
  dd=prev["close"]/h10-1;mv=med([x["volume"] for x in w20])
  if not(prev["close"]>sma20>sma50 and ret20>=0.05 and -0.08<=dd<=-0.025):continue
  if not(cur["close"]>cur["open"] and cur["close"]>prev["high"] and clv(cur)>=0.60):continue
  if mv<=0 or cur["volume"]<0.7*mv or cur["volume"]>2.5*mv:continue
  # Higher-low behavior inside the pullback.
  lows=[x["low"] for x in rows[t-5:t]]
  if len(lows)>=4 and min(lows[-2:])<=min(lows[:-2]):continue
  liq=med([x["close"]*x["volume"] for x in w20])
  out.append({"engine":"PBC","symbol":sym,"entry_date":cur["date"],"entry":cur["close"],"liquidity":liq,"future":rows[t+1:t+8]});last=t
 return out

def fbr_signals(sym,rows):
 out=[];last=-99
 for t in range(30,len(rows)-7):
  if t-last<10:continue
  cur=rows[t];prior=rows[t-20:t];support=min(x["low"] for x in prior);mv=med([x["volume"] for x in prior])
  if not(cur["low"]<support*0.99 and cur["close"]>support and cur["close"]>cur["open"] and clv(cur)>=0.65):continue
  if mv<=0 or cur["volume"]<1.5*mv:continue
  # Do not catch a strongly falling knife.
  if rows[t-1]["close"]/rows[t-20]["close"]-1<-0.12:continue
  liq=med([x["close"]*x["volume"] for x in prior])
  out.append({"engine":"FBR","symbol":sym,"entry_date":cur["date"],"entry":cur["close"],"liquidity":liq,"future":rows[t+1:t+8]});last=t
 return out

def finalize(sig):
 rule=ENGINE_RULES[sig["engine"]];e=sig["entry"];tgt=e*(1+rule["target"]);stp=e*(1-rule["stop"]);f=sig["future"][:rule["horizon"]]
 for i,d in enumerate(f,1):
  if d["low"]<=stp:return {**{k:sig[k] for k in ["engine","symbol","entry_date","entry","liquidity"]},"exit_date":d["date"],"exit_price":stp,"gross_return":-rule["stop"],"exit_type":"stop","holding":i,"stop":rule["stop"],"target":rule["target"]}
  if d["high"]>=tgt:return {**{k:sig[k] for k in ["engine","symbol","entry_date","entry","liquidity"]},"exit_date":d["date"],"exit_price":tgt,"gross_return":rule["target"],"exit_type":"target","holding":i,"stop":rule["stop"],"target":rule["target"]}
 d=f[-1];return {**{k:sig[k] for k in ["engine","symbol","entry_date","entry","liquidity"]},"exit_date":d["date"],"exit_price":d["close"],"gross_return":d["close"]/e-1,"exit_type":"timeout","holding":rule["horizon"],"stop":rule["stop"],"target":rule["target"]}

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
 prev=INITIAL;vals=[];hitany=0
 for wk in sorted(by):
  a=by[wk];end=a[-1]["equity"];ret=end/prev-1;mx=max(x["equity"] for x in a)/prev-1;vals.append(ret);hitany+=mx>=WEEKLY_TARGET;prev=end
 return {"weeks":len(vals),"avg":mean(vals),"median":med(vals),"positive_rate":sum(x>0 for x in vals)/len(vals) if vals else 0,"weekend_ge_2_rate":sum(x>=WEEKLY_TARGET for x in vals)/len(vals) if vals else 0,"hit_2_anytime_rate":hitany/len(vals) if vals else 0,"worst":min(vals) if vals else 0,"best":max(vals) if vals else 0}

def build_maps(data):
 c={};ds=set()
 for s,rs in data.items():c[s]={r["date"]:r["close"] for r in rs};ds.update(c[s])
 return c,sorted(ds)

def simulate(trades,closes,dates,period,cfg):
 eb=defaultdict(list);xb=defaultdict(list)
 for t in trades:eb[t["entry_date"]].append(t);xb[t["exit_date"]].append(t)
 # Prioritize liquidity, then higher nominal R:R.
 for d in eb:eb[d].sort(key=lambda x:(-x["liquidity"],-(x["target"]/x["stop"]),x["symbol"]))
 ds=[d for d in dates if period[0]<=d<=period[1]];half=FRICTION/2;cash=INITIAL;pos={};last={};curve=[];real=[];skipped=0;wk=None;wk0=INITIAL;locked=False
 def mark(d):
  pv=0
  for key,p in pos.items():
   px=closes.get(p["symbol"],{}).get(d)
   if px is not None:last[p["symbol"]]=px
   pv+=p["shares"]*last.get(p["symbol"],p["entry"])
  return cash+pv,pv
 for d in ds:
  w=week_start(d)
  if w!=wk:eq0,_=mark(d);wk=w;wk0=eq0;locked=False
  for key,p in list(pos.items()):
   px=closes.get(p["symbol"],{}).get(d)
   if px is not None:last[p["symbol"]]=px
  for tr in sorted(xb.get(d,[]),key=lambda x:(x["symbol"],x["engine"])):
   key=(tr["symbol"],tr["engine"],tr["entry_date"])
   if key not in pos:continue
   p=pos.pop(key);proceeds=p["shares"]*tr["exit_price"]*(1-half);cash+=proceeds;real.append({"engine":tr["engine"],"net":proceeds/p["budget"]-1,"exit_type":tr["exit_type"]})
  eq,_=mark(d)
  if cfg["weekly_loss_lock"] is not None and eq/wk0-1<=-cfg["weekly_loss_lock"]:locked=True
  held_symbols={p["symbol"] for p in pos.values()}
  for tr in eb.get(d,[]):
   if locked or tr["symbol"] in held_symbols or len(pos)>=cfg["max_positions"]:skipped+=1;continue
   eq,_=mark(d);openrisk=sum(p["risk_amt"] for p in pos.values())/eq if eq else 1
   if openrisk+cfg["risk_per_trade"]>cfg["max_open_risk"]+1e-12:skipped+=1;continue
   risk_amt=eq*cfg["risk_per_trade"];desired=risk_amt/tr["stop"];budget=min(desired,eq*cfg["max_position_frac"],cash)
   if budget<=1:skipped+=1;continue
   invested=budget*(1-half);shares=invested/tr["entry"];cash-=budget;key=(tr["symbol"],tr["engine"],tr["entry_date"]);pos[key]={"symbol":tr["symbol"],"entry":tr["entry"],"shares":shares,"budget":budget,"risk_amt":budget*tr["stop"]};last[tr["symbol"]]=tr["entry"];held_symbols.add(tr["symbol"])
  eq,pv=mark(d);curve.append({"date":d,"equity":eq,"exposure":pv/eq if eq else 0,"open":len(pos),"open_risk":sum(p["risk_amt"] for p in pos.values())/eq if eq else 0})
 if not curve:return None
 m,pd,td=maxdd(curve);final=curve[-1]["equity"];d0=datetime.fromisoformat(curve[0]["date"]).date();d1=datetime.fromisoformat(curve[-1]["date"]).date();yrs=max((d1-d0).days/365.25,1/365.25);wm=weekly(curve)
 return {"trades":len(real),"skipped":skipped,"final_equity":final,"total_return":final/INITIAL-1,"cagr":(final/INITIAL)**(1/yrs)-1,"max_drawdown":m,"dd_peak":pd,"dd_trough":td,"weekly":wm,"avg_exposure":mean([x["exposure"] for x in curve]),"max_open_risk":max(x["open_risk"] for x in curve),"engine_trades":{e:sum(1 for x in real if x["engine"]==e) for e in ENGINE_RULES},"engine_positive":{e:(sum(1 for x in real if x["engine"]==e and x["net"]>0)/sum(1 for x in real if x["engine"]==e) if sum(1 for x in real if x["engine"]==e) else None) for e in ENGINE_RULES}}

def stats(signals,p):
 ts=[finalize(x) for x in signals if in_period(x["entry_date"],p) and x["future"][-1]["date"]<=p[1]]
 return {"signals":len(ts),"positive":sum(1 for x in ts if x["gross_return"]>0),"positive_rate":sum(1 for x in ts if x["gross_return"]>0)/len(ts) if ts else None,"targets":sum(1 for x in ts if x["exit_type"]=="target"),"stops":sum(1 for x in ts if x["exit_type"]=="stop"),"avg_gross":mean([x["gross_return"] for x in ts]) if ts else None}

def main():
 root=os.environ.get("EGX_DATA_ROOT","egxdata/Dataset/raw");files=sorted(glob.glob(os.path.join(root,"*","*.csv")));data={}
 for p in files:
  s=os.path.basename(p).split(".")[0].upper();r=v3.load_csv_all(p)
  if len(r)>=100:data[s]=r
 market=v3.build_market_maps(data);signals=[]
 for s,r in data.items():signals+=dlp_signals(s,r,market)+brt_signals(s,r)+pbc_signals(s,r)+fbr_signals(s,r)
 # exact duplicate engine/symbol/date impossible by construction, but sort for reproducibility.
 signals.sort(key=lambda x:(x["entry_date"],x["symbol"],x["engine"]));finalized=[finalize(x) for x in signals];closes,dates=build_maps(data)
 engstats={e:{"2023":stats([x for x in signals if x["engine"]==e],VAL1),"2024":stats([x for x in signals if x["engine"]==e],VAL2),"final":stats([x for x in signals if x["engine"]==e],FINAL)} for e in ENGINE_RULES}
 ranked=[];tested=0
 for rpt in RISK_PER_TRADE:
  for mor in MAX_OPEN_RISK:
   if mor<rpt:continue
   for mp in MAX_POSITIONS:
    for cap in MAX_POSITION_FRAC:
     for wll in WEEKLY_LOSS_LOCK:
      tested+=1;cfg={"risk_per_trade":rpt,"max_open_risk":mor,"max_positions":mp,"max_position_frac":cap,"weekly_loss_lock":wll}
      a=simulate([x for x in finalized if in_period(x["entry_date"],VAL1) and x["exit_date"]<=VAL1[1]],closes,dates,VAL1,cfg);b=simulate([x for x in finalized if in_period(x["entry_date"],VAL2) and x["exit_date"]<=VAL2[1]],closes,dates,VAL2,cfg)
      if not a or not b or a["trades"]<MIN_TRADES or b["trades"]<MIN_TRADES:continue
      if max(abs(a["max_drawdown"]),abs(b["max_drawdown"]))>MAX_VALIDATION_DD:continue
      minavg=min(a["weekly"]["avg"],b["weekly"]["avg"]);min2=min(a["weekly"]["weekend_ge_2_rate"],b["weekly"]["weekend_ge_2_rate"]);minc=min(a["cagr"],b["cagr"]);worst=max(abs(a["max_drawdown"]),abs(b["max_drawdown"]))
      ranked.append({"config":cfg,"2023":a,"2024":b,"min_avg_weekly":minavg,"min_weekend_2_rate":min2,"min_cagr":minc,"worst_dd":worst})
 ranked.sort(key=lambda x:(x["min_avg_weekly"],x["min_weekend_2_rate"],x["min_cagr"],-x["worst_dd"]),reverse=True)
 best=ranked[0] if ranked else None;fin=None
 if best:fin=simulate([x for x in finalized if in_period(x["entry_date"],FINAL) and x["exit_date"]<=FINAL[1]],closes,dates,FINAL,best["config"])
 result={"pattern":"EGX Multi-Engine Weekly Return Portfolio v4.0","goal":"increase opportunity frequency so 2%+ weeks can come from diversified setups instead of increasing risk on DLP alone","engines":ENGINE_RULES,"friction_round_trip":FRICTION,"protocol":{"validation_2023":VAL1,"validation_2024":VAL2,"final_holdout":FINAL,"final_not_used_for_selection":True,"max_validation_drawdown":MAX_VALIDATION_DD,"ranking":"maximize weaker validation-year average weekly return, then week-end >=2% rate, CAGR, lower DD"},"dataset":{"stocks":len(data),"signals_total":len(signals)},"engine_standalone":engstats,"grid":{"tested":tested,"eligible":len(ranked)},"selected":best,"final_result":fin,"top20":ranked[:20]}
 with open("tmp/egx_backtest/results_v40_multiengine.json","w",encoding="utf-8") as f:json.dump(result,f,ensure_ascii=False,indent=2)
 print(json.dumps({k:result[k] for k in ["pattern","dataset","engine_standalone","grid","selected","final_result"]},ensure_ascii=False,indent=2))
if __name__=="__main__":main()
