import glob,json,os,sys
sys.path.insert(0,"tmp/egx_backtest")
import backtest_v3_ml as v3
import backtest_v40_multiengine as v40

VAL1=v40.VAL1;VAL2=v40.VAL2;FINAL=v40.FINAL
MIN_CAGR=0.30;MAX_DD=0.08;MIN_TRADES=15
RISK=[0.005,0.006,0.0075,0.01]
OPEN=[0.015,0.02,0.025,0.03]
POSITIONS=[3,4]
CAPS=[0.25,0.30,0.35]
WLOCK=[None,0.02,0.025]
SUBSETS=[("DLP",),("DLP","BRT"),("DLP","PBC"),("DLP","BRT","PBC")]


def brt2(sym,rows):
 out=[];last=-99
 for t in range(60,len(rows)-7):
  if t-last<10:continue
  cur=rows[t];prev=rows[t-1];found=False
  for j in range(max(21,t-3),t):
   prior=rows[j-20:j];level=max(x["high"] for x in prior);mv=v40.med([x["volume"] for x in prior]);b=rows[j]
   clearance=b["close"]/level-1
   body=(b["close"]-b["open"])/b["open"]
   if not(0.008<=clearance<=0.06 and body>=0.015 and v40.clv(b)>=0.70 and mv>0 and b["volume"]>=2.0*mv):continue
   after=rows[j+1:t+1]
   if not after or min(x["low"] for x in after)>level*1.015:continue
   if min(x["close"] for x in after)<level*0.99:continue
   if not(cur["close"]>cur["open"] and cur["close"]>prev["high"] and cur["close"]>level and cur["close"]<=level*1.055 and v40.clv(cur)>=0.65):continue
   if cur["volume"]<0.8*mv:continue
   found=True;break
  if found:
   liq=v40.med([x["close"]*x["volume"] for x in rows[t-20:t]])
   out.append({"engine":"BRT","symbol":sym,"entry_date":cur["date"],"entry":cur["close"],"liquidity":liq,"future":rows[t+1:t+8]});last=t
 return out

def pbc2(sym,rows):
 out=[];last=-99
 for t in range(60,len(rows)-7):
  if t-last<10:continue
  cur=rows[t];prev=rows[t-1];w50=rows[t-50:t];w20=rows[t-20:t];w10=rows[t-10:t]
  sma20=v40.mean([x["close"] for x in w20]);sma50=v40.mean([x["close"] for x in w50]);sma20old=v40.mean([x["close"] for x in rows[t-25:t-5]])
  h10=max(x["high"] for x in w10);h20=max(x["high"] for x in w20);ret20=prev["close"]/rows[t-20]["close"]-1;dd=prev["close"]/h10-1;mv=v40.med([x["volume"] for x in w20])
  if not(prev["close"]>sma20>sma50 and sma20>sma20old and 0.08<=ret20<=0.30 and -0.06<=dd<=-0.025):continue
  lows=[x["low"] for x in rows[t-5:t]]
  if min(lows[-2:])<=min(lows[:-2]):continue
  if not(cur["close"]>cur["open"] and cur["close"]>prev["high"] and cur["close"]>sma20 and cur["close"]<=h20*1.02 and v40.clv(cur)>=0.65):continue
  if mv<=0 or not(0.8*mv<=cur["volume"]<=2.0*mv):continue
  liq=v40.med([x["close"]*x["volume"] for x in w20])
  out.append({"engine":"PBC","symbol":sym,"entry_date":cur["date"],"entry":cur["close"],"liquidity":liq,"future":rows[t+1:t+8]});last=t
 return out

def run_port(sig,closes,dates,p,cfg):
 ts=[v40.finalize(x) for x in sig if v40.in_period(x["entry_date"],p) and x["future"][-1]["date"]<=p[1]]
 return v40.simulate(ts,closes,dates,p,cfg)

def main():
 root=os.environ.get("EGX_DATA_ROOT","egxdata/Dataset/raw");files=sorted(glob.glob(os.path.join(root,"*","*.csv")));data={}
 for p in files:
  s=os.path.basename(p).split(".")[0].upper();r=v3.load_csv_all(p)
  if len(r)>=100:data[s]=r
 market=v3.build_market_maps(data);by={"DLP":[],"BRT":[],"PBC":[]}
 for s,r in data.items():
  by["DLP"]+=v40.dlp_signals(s,r,market);by["BRT"]+=brt2(s,r);by["PBC"]+=pbc2(s,r)
 closes,dates=v40.build_maps(data)
 standalone={e:{"2023":v40.stats(ss,VAL1),"2024":v40.stats(ss,VAL2),"final":v40.stats(ss,FINAL)} for e,ss in by.items()}
 ranked=[];tested=0
 for subset in SUBSETS:
  sig=[]
  for e in subset:sig+=by[e]
  for rpt in RISK:
   for mor in OPEN:
    if mor<rpt:continue
    for mp in POSITIONS:
     for cap in CAPS:
      for wl in WLOCK:
       tested+=1;cfg={"risk_per_trade":rpt,"max_open_risk":mor,"max_positions":mp,"max_position_frac":cap,"weekly_loss_lock":wl}
       a=run_port(sig,closes,dates,VAL1,cfg);b=run_port(sig,closes,dates,VAL2,cfg)
       if not a or not b or a["trades"]<MIN_TRADES or b["trades"]<MIN_TRADES:continue
       if max(abs(a["max_drawdown"]),abs(b["max_drawdown"]))>MAX_DD:continue
       if min(a["cagr"],b["cagr"])<MIN_CAGR:continue
       minavg=min(a["weekly"]["avg"],b["weekly"]["avg"]);min2=min(a["weekly"]["weekend_ge_2_rate"],b["weekly"]["weekend_ge_2_rate"]);minc=min(a["cagr"],b["cagr"]);worst=max(abs(a["max_drawdown"]),abs(b["max_drawdown"]))
       ranked.append({"subset":subset,"config":cfg,"2023":a,"2024":b,"min_avg_weekly":minavg,"min_weekend_2_rate":min2,"min_cagr":minc,"worst_dd":worst})
 ranked.sort(key=lambda x:(x["min_avg_weekly"],x["min_weekend_2_rate"],x["min_cagr"],-x["worst_dd"]),reverse=True)
 best=ranked[0] if ranked else None;fin=None
 if best:
  sig=[]
  for e in best["subset"]:sig+=by[e]
  fin=run_port(sig,closes,dates,FINAL,best["config"])
 result={"pattern":"EGX Multi-Engine Quality Gate v4.1","goal":"add only secondary setups that survive strict quality gates while keeping portfolio DD <=8% in both validation years","protocol":{"validation_2023":VAL1,"validation_2024":VAL2,"final_holdout":FINAL,"final_not_used_for_selection":True,"min_validation_cagr":MIN_CAGR,"max_validation_drawdown":MAX_DD,"ranking":"weaker-year average weekly return then >=2% week rate then CAGR"},"standalone":standalone,"grid":{"tested":tested,"eligible":len(ranked),"subsets":[list(x) for x in SUBSETS]},"selected":best,"final_result":fin,"top20":ranked[:20]}
 with open("tmp/egx_backtest/results_v41_quality_gate.json","w",encoding="utf-8") as f:json.dump(result,f,ensure_ascii=False,indent=2)
 print(json.dumps({k:result[k] for k in ["pattern","standalone","grid","selected","final_result"]},ensure_ascii=False,indent=2))
if __name__=="__main__":main()
