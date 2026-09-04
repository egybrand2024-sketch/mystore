import glob, json, os, sys
sys.path.insert(0,"tmp/egx_backtest")
import backtest_v3_ml as v3

VAL1=("2023-01-01","2023-12-31")
VAL2=("2024-01-01","2024-12-31")
FINAL=("2025-01-01","2026-02-28")


def in_period(x,p): return p[0] <= x["date"] <= p[1]

def collect_v2_with_future(sym,rows,market,max_h=15):
    out=[]; next_allowed=v3.MAX_BASE; t=max(v3.MAX_BASE,60)
    while t < len(rows)-max_h:
        if t<next_allowed: t+=1; continue
        matches=[]
        for n in range(v3.MIN_BASE,v3.MAX_BASE+1):
            c=v3.v1_candidate(rows,t,n)
            if c: matches.append(c)
        if matches:
            c=max(matches,key=lambda x:x["base_n"])
            # Need 10 bars so v3.make_signal can compute the frozen v2 flag.
            s=v3.make_signal(sym,rows,t,c,market)
            if s and s["v2_flag"]>0:
                out.append({"symbol":sym,"date":rows[t]["date"],"entry":rows[t]["close"],"future":rows[t+1:t+1+max_h]})
            next_allowed=t+v3.COOLDOWN+1
        t+=1
    return out

def evaluate_trade(tr,target,stop,horizon):
    entry=tr["entry"]; tgt=entry*(1+target); stp=entry*(1-stop)
    future=tr["future"][:horizon]
    for d in future:
        # Conservative daily-bar ambiguity: stop first if both touched.
        if d["low"]<=stp: return -stop,"stop"
        if d["high"]>=tgt: return target,"target"
    return future[-1]["close"]/entry-1,"timeout"

def summarize(trades,target,stop,horizon):
    rets=[]; kinds=[]
    for tr in trades:
        r,k=evaluate_trade(tr,target,stop,horizon); rets.append(r); kinds.append(k)
    n=len(rets)
    return {
      "trades":n,"avg_return":sum(rets)/n if n else None,"median_return":v3.median(rets) if n else None,
      "target_rate":kinds.count("target")/n if n else None,"stop_rate":kinds.count("stop")/n if n else None,
      "timeout_rate":kinds.count("timeout")/n if n else None,
      "targets":kinds.count("target"),"stops":kinds.count("stop"),"timeouts":kinds.count("timeout")
    }

def main():
    root=os.environ.get("EGX_DATA_ROOT","egxdata/Dataset/raw")
    files=sorted(glob.glob(os.path.join(root,"*","*.csv")))
    data={}
    for p in files:
        sym=os.path.basename(p).split(".")[0].upper(); rows=v3.load_csv_all(p)
        if len(rows)>=100:data[sym]=rows
    market=v3.build_market_maps(data)
    trades=[]
    for sym,rows in data.items():trades.extend(collect_v2_with_future(sym,rows,market,15))
    a=[x for x in trades if in_period(x,VAL1)]; b=[x for x in trades if in_period(x,VAL2)]; f=[x for x in trades if in_period(x,FINAL)]

    baseline={"target":0.08,"stop":0.04,"horizon":10}
    ba=summarize(a,**baseline); bb=summarize(b,**baseline); bf=summarize(f,**baseline)
    ranked=[]
    for target in [0.04,0.05,0.06,0.07,0.08,0.09,0.10,0.12]:
      for stop in [0.02,0.025,0.03,0.035,0.04,0.045,0.05,0.06]:
        for horizon in [5,7,10,12,15]:
          sa=summarize(a,target,stop,horizon); sb=summarize(b,target,stop,horizon)
          # Optimize the weaker year's expectancy, then average expectancy.
          minret=min(sa["avg_return"],sb["avg_return"]); avgret=(sa["avg_return"]+sb["avg_return"])/2
          ranked.append({"target":target,"stop":stop,"horizon":horizon,"2023":sa,"2024":sb,"min_avg_return":minret,"avg_of_year_avg_returns":avgret})
    ranked.sort(key=lambda x:(x["min_avg_return"],x["avg_of_year_avg_returns"]),reverse=True)
    best=ranked[0]
    final=summarize(f,best["target"],best["stop"],best["horizon"])
    rel=(final["avg_return"]/bf["avg_return"]-1) if bf["avg_return"] else None
    result={
      "pattern":"Defensive Lift v3 trade-management research",
      "protocol":{"validation_2023":VAL1,"validation_2024":VAL2,"final":FINAL,"final_not_used_for_selection":True,"ranking":"maximize weaker validation year's average realized return","same_bar":"stop first"},
      "dataset":{"files":len(files),"stocks":len(data),"v2_trades_total":len(trades)},
      "baseline_8_4_10":{"2023":ba,"2024":bb,"final":bf},
      "configs_tested":len(ranked),
      "selected":{"target":best["target"],"stop":best["stop"],"horizon":best["horizon"],"2023":best["2023"],"2024":best["2024"]},
      "final_result":final,
      "relative_improvement_in_avg_return_vs_v2_management":rel,
      "meets_30pct_relative_expectancy_target":bool(rel is not None and rel>=0.30),
      "top20":ranked[:20]
    }
    with open("tmp/egx_backtest/results_v3_management.json","w",encoding="utf-8") as fh:json.dump(result,fh,ensure_ascii=False,indent=2)
    print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=="__main__":main()
