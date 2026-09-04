import glob,json,math,os,sys
from collections import defaultdict,deque
from datetime import datetime
sys.path.insert(0,"tmp/egx_backtest")
import analyze_v58_hazard_attribution as hz
import backtest_v58_selective_hazard_gate as v58

V23=("2023-01-01","2023-12-31"); V24=("2024-01-01","2024-12-31"); FINAL=("2025-01-01","2026-02-28")
INITIAL=100000.0; TARGET=.12; STOP=.045; H=7; SLOTS=2; HALF=.0025
EPS=1e-12

# Strict historical frontier built from the six strongest prior research versions.
# A single v5.12 rule must beat the best return AND the best drawdown among all six in every period.
FRONTIER={
 "2023":{"return":0.4292181660960166,"dd":-0.04308669143288557,"active_ge2":0.4230769230769231},
 "2024":{"return":0.5068743074573163,"dd":-0.08011330922812487,"active_ge2":0.38461538461538464},
 "final":{"return":0.710060075535486,"dd":-0.059472498119147454,"active_ge2":0.37209302325581395},
}
REFERENCES={
 "v3.2":{"2023":{"return":.38783533147468163,"dd":-.06497255722349737},"2024":{"return":.46219461778908233,"dd":-.1116567654875591},"final":{"return":.710060075535486,"dd":-.06909077753849246}},
 "v5.10C":{"2023":{"return":.4003763476700404,"dd":-.05781411126020031},"2024":{"return":.48000687652845,"dd":-.1046462370726311},"final":None},
 "v5.11B":{"2023":{"return":.41794386415448614,"dd":-.051134510455982496},"2024":{"return":.5068743074573163,"dd":-.10232861327447729},"final":{"return":.6919395310578205,"dd":-.06875966283196833}},
 "v5.11D":{"2023":{"return":.4085360344127298,"dd":-.05542796260576777},"2024":{"return":.49302680678437993,"dd":-.10232861327447762},"final":{"return":.6915547651623803,"dd":-.06912190031672982}},
 "v5.11E":{"2023":{"return":.4292181660960166,"dd":-.051134510455982496},"2024":{"return":.5068743074573163,"dd":-.10232861327447729},"final":{"return":.6915547651623803,"dd":-.06912190031672982}},
 "v5.1":{"2023":{"return":.35801885440523384,"dd":-.04308669143288557},"2024":{"return":.45974828893706676,"dd":-.08011330922812487},"final":{"return":.6677658089405043,"dd":-.059472498119147454}},
}

def slim(x): return {k:v for k,v in x.items() if k not in {"curve","realized"}}
def inper(t,p): return p[0]<=t["entry_date"]<=p[1] and t["exit_date"]<=p[1]
def load_data():
 root=os.environ.get("EGX_DATA_ROOT","egxdata/Dataset/raw"); data={}
 for fp in sorted(glob.glob(os.path.join(root,"*","*.csv"))):
  s=os.path.basename(fp).split(".")[0].upper(); rows=hz.v3.load_csv_all(fp)
  if len(rows)>=100:data[s]=rows
 return data

def prep_period(data,trades,period):
 dates=sorted({r["date"] for rows in data.values() for r in rows if period[0]<=r["date"]<=period[1]})
 eb=defaultdict(list)
 arr=[t for t in trades if inper(t,period)]
 for t in arr: eb[t["entry_date"]].append(t)
 for d in eb: eb[d].sort(key=lambda x:(-x["liquidity"],x["symbol"]))
 closes={s:{r["date"]:r["close"] for r in rows if period[0]<=r["date"]<=period[1]} for s,rows in data.items()}
 highs={s:{r["date"]:r["high"] for r in rows if period[0]<=r["date"]<=period[1]} for s,rows in data.items()}
 lows={s:{r["date"]:r["low"] for r in rows if period[0]<=r["date"]<=period[1]} for s,rows in data.items()}
 return {"period":period,"dates":dates,"entries":eb,"trades":arr,"closes":closes,"highs":highs,"lows":lows}

def protect_condition(family,t,portfolio_dd,recent_stops,cfg):
 breadth=t.get("market_breadth20")
 weakb=hz.finite(breadth) and breadth<=cfg.get("breadth_th",-999)
 ddown=portfolio_dd<=cfg.get("dd_trigger",-999)
 recent=recent_stops>=cfg.get("loss_count",999)
 if family=="A": return ddown
 if family=="B": return weakb
 if family=="C": return recent
 if family=="D": return ddown or weakb
 if family=="E": return (ddown or weakb or recent)
 raise ValueError(family)

def simulate(ctx,family,cfg):
 dates=ctx["dates"]; eb=ctx["entries"]; closes=ctx["closes"]; highs=ctx["highs"]; lows=ctx["lows"]
 cash=INITIAL; pos={}; last={}; curve=[]; real=[]; skipped=defaultdict(int); runtime=defaultdict(int)
 peak=INITIAL; recent_exit_types=deque(maxlen=cfg.get("loss_window_trades",3))
 def mark(d):
  pv=0.0
  for s,p in pos.items():
   px=closes.get(s,{}).get(d,last.get(s,p["entry"]))
   if px is not None:last[s]=px
   pv+=p["shares"]*last[s]
  return cash+pv,pv
 def add_to(s,p,d,target_frac):
  nonlocal cash
  if target_frac is None:return
  eq_now,_=mark(d); target_budget=min(p["entry_equity"]*target_frac,eq_now*target_frac)
  need=max(0,target_budget-p["budget"]); add=min(need,cash)
  if add>1:
   px=closes[s][d]; p["shares"]+=add*(1-HALF)/px; p["budget"]+=add; cash-=add; runtime["adds"]+=1
   if target_frac>.50+EPS:runtime["pyramids"]+=1
 for d in dates:
  # Manage positions first; stop-first for same-bar target/stop ambiguity.
  for s in list(pos):
   p=pos[s]; px=closes.get(s,{}).get(d)
   if px is None:continue
   last[s]=px
   if d==p["entry_date"]:continue
   p["age"]+=1; age=p["age"]; e=p["entry"]
   p["cum_mfe"]=max(p["cum_mfe"],highs[s][d]/e-1)
   stop_dist=STOP
   if p["protected"] and cfg.get("early_stop",STOP)<STOP and age<=cfg.get("stop_days",0) and not p["relaxed"]:
    stop_dist=cfg["early_stop"]
   stop_px=e*(1-stop_dist); target_px=e*(1+TARGET); xt=None; xp=None
   if lows[s][d]<=stop_px:xt="early_stop" if stop_dist<STOP-EPS else "stop";xp=stop_px
   elif highs[s][d]>=target_px:xt="target";xp=target_px
   elif age>=H:xt="timeout";xp=px
   if xt:
    proceeds=p["shares"]*xp*(1-HALF); cash+=proceeds
    nr=proceeds/p["budget"]-1; real.append({"symbol":s,"entry_date":p["entry_date"],"exit_date":d,"exit_type":xt,"protected":p["protected"],"net_return":nr})
    recent_exit_types.append(xt); runtime[xt]+=1; pos.pop(s); continue
   if p["protected"] and cfg.get("relax_mfe") is not None and p["cum_mfe"]>=cfg["relax_mfe"]:p["relaxed"]=True
   cr=px/e-1
   if p["protected"] and age==1 and p["cum_mfe"]>=cfg.get("d1_mfe",999) and cr>=cfg.get("d1_close",999):
    add_to(s,p,d,cfg.get("restore_frac",.50)); runtime["d1_confirms"]+=1
   if age==2 and p["cum_mfe"]>=cfg.get("d2_mfe",999) and cr>=cfg.get("d2_close",999):
    # Pyramiding may apply to protected or all strong winners, depending on config.
    if p["protected"] or cfg.get("pyramid_all",False):
     add_to(s,p,d,cfg.get("pyramid_frac")); runtime["d2_confirms"]+=1
  eq_before,_=mark(d); portfolio_dd=eq_before/peak-1 if peak>0 else 0
  stop_count=sum(x in ("stop","early_stop") for x in recent_exit_types)
  for t in eb.get(d,[]):
   s=t["symbol"]
   if s in pos:skipped["duplicate_symbol"]+=1;continue
   if len(pos)>=SLOTS:skipped["max_positions"]+=1;continue
   eq,_=mark(d); protected=protect_condition(family,t,portfolio_dd,stop_count,cfg)
   frac=cfg["protected_frac"] if protected else .50
   budget=min(eq*frac,cash)
   if budget<=1:skipped["cash"]+=1;continue
   sh=budget*(1-HALF)/t["entry"];cash-=budget
   pos[s]={"shares":sh,"budget":budget,"entry_equity":eq,"entry":t["entry"],"entry_date":d,"age":0,"cum_mfe":0.0,"protected":protected,"relaxed":False}
   if protected:runtime["protected_entries"]+=1
   last[s]=t["entry"]
  eq,pv=mark(d); peak=max(peak,eq); curve.append({"date":d,"equity":eq,"exposure":pv/eq if eq else 0})
 mdd,pd,td=v58.maxdd(curve); final=curve[-1]["equity"]; d0=datetime.fromisoformat(curve[0]["date"]).date();d1=datetime.fromisoformat(curve[-1]["date"]).date();yrs=max((d1-d0).days/365.25,1/365.25)
 rs=[r["net_return"] for r in real]
 return {"trades":len(real),"skipped":sum(skipped.values()),"skip_reasons":dict(skipped),"final_equity":final,"total_return":final/INITIAL-1,"cagr":(final/INITIAL)**(1/yrs)-1,"max_drawdown":mdd,"dd_peak":pd,"dd_trough":td,"avg_trade_return":v58.mean(rs),"positive_trade_rate":sum(x>0 for x in rs)/len(rs) if rs else 0,"weekly":v58.weekly(curve),"avg_exposure":v58.mean([x["exposure"] for x in curve]),"runtime":dict(runtime),"curve":curve,"realized":real}

def frontier_score(r23,r24,rf):
 per={"2023":r23,"2024":r24,"final":rf}; details={}; strict=True
 for k,r in per.items():
  f=FRONTIER[k]; ret_edge=100*(r["total_return"]-f["return"]); dd_edge=100*(abs(f["dd"])-abs(r["max_drawdown"])); active_edge=100*(r["weekly"]["active_ge_2_rate"]-f["active_ge2"])
  ok=ret_edge>0 and dd_edge>0 and active_edge>=-EPS
  details[k]={"return_edge_pp":ret_edge,"dd_improvement_pp":dd_edge,"active_ge2_edge_pp":active_edge,"pass":ok};strict=strict and ok
 return {"strict_beats_all_six":strict,"periods":details,"min_return_edge_pp":min(v["return_edge_pp"] for v in details.values()),"min_dd_improvement_pp":min(v["dd_improvement_pp"] for v in details.values()),"min_active_edge_pp":min(v["active_ge2_edge_pp"] for v in details.values())}

def configs():
 out=[]
 # A: drawdown-state sizing + recovery pyramid
 for dd in [-.01,-.015,-.02,-.025,-.03]:
  for frac in [.25,.30,.35,.40,.45]:
   for d1 in [.005,.01,.015,.02]:
    for pyr in [.55,.60,.65,.70]:
     for d2 in [.015,.025]:
      out.append(("A",{"dd_trigger":dd,"protected_frac":frac,"d1_mfe":d1,"d1_close":0.0,"restore_frac":.50,"d2_mfe":d2,"d2_close":0.0,"pyramid_frac":pyr,"pyramid_all":False,"loss_count":999,"loss_window_trades":3,"early_stop":STOP,"stop_days":0,"relax_mfe":None}))
 # B: weak-breadth sizing + recovery pyramid
 for b in [.30,.35,.40,.45]:
  for frac in [.25,.30,.35,.40,.45]:
   for d1 in [.005,.01,.015,.02]:
    for pyr in [.55,.60,.65,.70]:
     for d2 in [.015,.025]:
      out.append(("B",{"breadth_th":b,"protected_frac":frac,"d1_mfe":d1,"d1_close":0.0,"restore_frac":.50,"d2_mfe":d2,"d2_close":0.0,"pyramid_frac":pyr,"pyramid_all":False,"loss_count":999,"loss_window_trades":3,"early_stop":STOP,"stop_days":0,"relax_mfe":None}))
 # C: realized-loss cluster sizing, never skip; winner recovery
 for lc in [1,2]:
  for lw in [2,3,4]:
   for frac in [.25,.30,.35,.40]:
    for d1 in [.005,.01,.015]:
     for pyr in [.55,.60,.65]:
      out.append(("C",{"loss_count":lc,"loss_window_trades":lw,"protected_frac":frac,"d1_mfe":d1,"d1_close":0.0,"restore_frac":.50,"d2_mfe":.02,"d2_close":0.0,"pyramid_frac":pyr,"pyramid_all":False,"early_stop":STOP,"stop_days":0,"relax_mfe":None}))
 # D: drawdown OR weak breadth, broader risk net with strong-winner recovery
 for dd in [-.015,-.02,-.025,-.03]:
  for b in [.30,.35,.40,.45]:
   for frac in [.25,.30,.35,.40]:
    for d1 in [.005,.01,.015]:
     for pyr in [.55,.60,.65]:
      out.append(("D",{"dd_trigger":dd,"breadth_th":b,"protected_frac":frac,"d1_mfe":d1,"d1_close":0.0,"restore_frac":.50,"d2_mfe":.02,"d2_close":0.0,"pyramid_frac":pyr,"pyramid_all":False,"loss_count":999,"loss_window_trades":3,"early_stop":STOP,"stop_days":0,"relax_mfe":None}))
 # E: adaptive hybrid + temporary early stop + optional pyramid of all confirmed winners.
 for dd in [-.015,-.025]:
  for b in [.35,.40]:
   for lc in [1,2]:
    for frac in [.25,.30,.35]:
     for es in [.025,.03,.035]:
      for d1 in [.01,.015]:
       for pyrall in [False,True]:
        out.append(("E",{"dd_trigger":dd,"breadth_th":b,"loss_count":lc,"loss_window_trades":3,"protected_frac":frac,"early_stop":es,"stop_days":1,"relax_mfe":.015,"d1_mfe":d1,"d1_close":0.0,"restore_frac":.50,"d2_mfe":.02,"d2_close":0.0,"pyramid_frac":.60,"pyramid_all":pyrall}))
 return out

def main():
 data=load_data(); trades=hz.build(data); contexts={"2023":prep_period(data,trades,V23),"2024":prep_period(data,trades,V24),"final":prep_period(data,trades,FINAL)}
 baseline={k:slim(v58.simulate(c["trades"],data,c["period"],None)) for k,c in contexts.items()}
 rows=[]; strict=[]
 cfgs=configs()
 for i,(fam,cfg) in enumerate(cfgs,1):
  r23=simulate(contexts["2023"],fam,cfg);r24=simulate(contexts["2024"],fam,cfg);rf=simulate(contexts["final"],fam,cfg);sc=frontier_score(r23,r24,rf)
  z={"family":fam,"config":cfg,"2023":slim(r23),"2024":slim(r24),"final":slim(rf),**sc};rows.append(z)
  if sc["strict_beats_all_six"]:strict.append(z)
 key=lambda z:(z["strict_beats_all_six"],z["min_dd_improvement_pp"],z["min_return_edge_pp"],z["min_active_edge_pp"],sum(v["return_edge_pp"]+v["dd_improvement_pp"] for v in z["periods"].values()))
 rows.sort(key=key,reverse=True);strict.sort(key=key,reverse=True)
 best=strict[0] if strict else rows[0]
 # Also report best by each bottleneck so a failed strict search is diagnostic rather than opaque.
 best_return=max(rows,key=lambda z:z["min_return_edge_pp"]);best_dd=max(rows,key=lambda z:z["min_dd_improvement_pp"])
 result={"version":"v5.12","name":"Strict Historical Champion Search","status":"STRICT CHAMPION" if strict else "NO STRICT CHAMPION FOUND","selection_note":"Because the 2025-Feb2026 research period has already been observed in earlier research, v5.12 is a historical frontier search, not a pristine out-of-sample validation.","strict_rule":"One identical causal rule must simultaneously exceed the best return and the best max-drawdown result among v3.2, v5.10C, v5.11B, v5.11D, v5.11E and v5.1 in 2023, 2024 and the final research period, while preserving the strongest active-week >=2% rate frontier.","references":REFERENCES,"frontier":FRONTIER,"dataset":{"stocks":len(data),"signals":len(trades),"configs_tested":len(cfgs)},"baseline_v32":baseline,"strict_count":len(strict),"champion":best if strict else None,"best_near_miss":best,"best_min_return":best_return,"best_min_drawdown":best_dd,"top20":rows[:20],"method_notes":["No leverage: additions are capped by available cash.","Maximum two open ideas remains fixed.","Target +12%, structural stop -4.5%, H7 and 0.5% round-trip friction sensitivity remain fixed.","All entry-state decisions are causal: portfolio drawdown, already-realized losses and current signal breadth only.","All confirmation additions use session-close information after same-session stop/target evaluation.","Stop-first is retained for same-bar ambiguity.","The final research period is included in the historical frontier objective only because the user explicitly requested one version that beats all six already-observed references; this removes any claim of pristine holdout validation."]}
 with open("tmp/egx_backtest/results_v512_historical_champion.json","w",encoding="utf-8") as f:json.dump(result,f,ensure_ascii=False,indent=2)
 print(json.dumps({"status":result["status"],"configs_tested":len(cfgs),"strict_count":len(strict),"champion":result["champion"],"best_near_miss":best,"best_min_return":best_return,"best_min_drawdown":best_dd},ensure_ascii=False,indent=2))
if __name__=="__main__":main()
