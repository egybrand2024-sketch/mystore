import itertools, json, math, os, glob, sys
sys.path.insert(0, "tmp/egx_backtest")
import backtest_v3_ml as v3

CAL=("2021-01-01","2022-12-31")
VAL1=("2023-01-01","2023-12-31")
VAL2=("2024-01-01","2024-12-31")
FINAL=("2025-01-01","2026-02-28")
MIN_SIG=10
MIN_SYM=8


def in_period(s,p): return p[0] <= s["date"] <= p[1]

def quant(vals,p):
    vals=sorted(float(x) for x in vals if x is not None and math.isfinite(float(x)))
    if not vals: return 0.0
    pos=(len(vals)-1)*p; lo=int(math.floor(pos)); hi=int(math.ceil(pos))
    return vals[lo] if lo==hi else vals[lo]*(hi-pos)+vals[hi]*(pos-lo)

def build_signals():
    root=os.environ.get("EGX_DATA_ROOT","egxdata/Dataset/raw")
    files=sorted(glob.glob(os.path.join(root,"*","*.csv")))
    data={}
    for path in files:
        sym=os.path.basename(path).split(".")[0].upper(); rows=v3.load_csv_all(path)
        if len(rows)>=100: data[sym]=rows
    market=v3.build_market_maps(data)
    sigs=[]
    for sym,rows in data.items(): sigs.extend(v3.collect_signals(sym,rows,market))
    sigs.sort(key=lambda s:(s["date"],s["symbol"]))
    return sigs,len(files),len(data)

def main():
    sigs,files_found,stocks=build_signals()
    cal=[s for s in sigs if in_period(s,CAL)]
    a=[s for s in sigs if in_period(s,VAL1)]
    b=[s for s in sigs if in_period(s,VAL2)]
    final=[s for s in sigs if in_period(s,FINAL)]

    # Focused feature set from robust v2 + v3 diagnostics. Quantile thresholds are calibrated only on 2021-2022.
    specs=[
      ("clv","ge",[0.60,0.75]),
      ("upper_wick","le",[0.25,0.40]),
      ("base_range","le",[0.25,0.40]),
      ("body","ge",[0.60,0.75]),
      ("breakout_vs_60_high","ge",[0.50,0.70]),
      ("close_vs_sma50","ge",[0.50,0.70]),
      ("pre60_ret","ge",[0.50,0.70]),
      ("market20_ret","ge",[0.40,0.60]),
      ("compression_ratio","le",[0.35,0.50]),
      ("breakout_vol_ratio","ge",[0.50,0.70]),
      ("nearest_overhead_pct","ge",[0.50,0.70]),
      ("prebreak_vol_ratio","ge",[0.50,0.70]),
    ]
    atoms=[]
    for feat,op,qs in specs:
        vals=[s.get(feat) for s in cal]
        for qq in qs:
            t=quant(vals,qq)
            if op=="ge": fn=lambda s,f=feat,t=t: s.get(f) is not None and s[f]>=t
            else: fn=lambda s,f=feat,t=t: s.get(f) is not None and s[f]<=t
            atoms.append({"family":feat,"name":f"{feat}_{op}_q{int(qq*100)}","desc":f"{feat} {op} {t:.6g} (cal q{qq:.2f})","fn":fn})
    atoms += [
      {"family":"v2","name":"v2_flag","desc":"v2_flag == 1","fn":lambda s:s.get("v2_flag",0)>0},
      {"family":"market_sign","name":"market20_positive","desc":"market20_ret > 0","fn":lambda s:s.get("market20_ret",0)>0},
      {"family":"near60","name":"within5pct_60d_high","desc":"dist_60_high >= -5%","fn":lambda s:s.get("dist_60_high",-9)>=-0.05},
      {"family":"wick_abs","name":"upper_wick_le20","desc":"upper_wick <= 20%","fn":lambda s:s.get("upper_wick",9)<=0.20},
    ]

    def choose(src,combo): return [s for s in src if all(x["fn"](s) for x in combo)]
    ranked=[]
    for k in (2,3,4):
        for combo in itertools.combinations(atoms,k):
            fam=[x["family"] for x in combo]
            if len(set(fam))<len(fam): continue
            sa=choose(a,combo); sb=choose(b,combo)
            ma=v3.summary(sa); mb=v3.summary(sb)
            if ma["signals"]<MIN_SIG or mb["signals"]<MIN_SIG: continue
            if ma["unique_symbols"]<MIN_SYM or mb["unique_symbols"]<MIN_SYM: continue
            la=v3.wilson_lower(ma["wins"],ma["signals"],1.0); lb=v3.wilson_lower(mb["wins"],mb["signals"],1.0)
            ranked.append({
              "rules":[x["desc"] for x in combo],"names":[x["name"] for x in combo],"combo":combo,
              "fold_2023":ma,"fold_2024":mb,"min_wilson":min(la,lb),"avg_wilson":v3.mean([la,lb]),
              "min_win_rate":min(ma["win_rate"],mb["win_rate"]),"combined_signals":ma["signals"]+mb["signals"]
            })
    ranked.sort(key=lambda r:(r["min_wilson"],r["avg_wilson"],r["min_win_rate"],r["combined_signals"]),reverse=True)
    best=ranked[0]
    fs=choose(final,best["combo"]); fm=v3.summary(fs)
    v2a=v3.summary([s for s in a if s["v2_flag"]>0]); v2b=v3.summary([s for s in b if s["v2_flag"]>0]); v2f=v3.summary([s for s in final if s["v2_flag"]>0])
    targeta=v2a["win_rate"]*1.30; targetb=v2b["win_rate"]*1.30; targetf=v2f["win_rate"]*1.30
    rel=(fm["win_rate"]/v2f["win_rate"]-1) if fm["win_rate"] is not None and v2f["win_rate"] else None

    stable=[]
    for r in ranked:
        if r["fold_2023"]["win_rate"]>=targeta and r["fold_2024"]["win_rate"]>=targetb:
            combo=r["combo"]; ff=v3.summary(choose(final,combo))
            stable.append({"rules":r["rules"],"fold_2023":r["fold_2023"],"fold_2024":r["fold_2024"],"final":ff})
            if len(stable)>=20: break

    result={
      "pattern":"Defensive Lift v3 focused high-selectivity rules",
      "protocol":{"calibration":CAL,"validation_2023":VAL1,"validation_2024":VAL2,"final":FINAL,"final_not_used_for_selection":True,"min_signals_per_fold":MIN_SIG,"min_symbols_per_fold":MIN_SYM,"max_rules":4},
      "dataset":{"files_found":files_found,"stocks_loaded":stocks,"signals":len(sigs)},
      "v2_benchmark":{"2023":v2a,"2024":v2b,"final":v2f},
      "relative_30pct_targets":{"2023":targeta,"2024":targetb,"final":targetf},
      "atoms":len(atoms),"eligible_combos":len(ranked),
      "selected":{"rules":best["rules"],"fold_2023":best["fold_2023"],"fold_2024":best["fold_2024"],"min_wilson":best["min_wilson"],"combined_signals":best["combined_signals"]},
      "final_result":fm,"relative_improvement_vs_v2_final":rel,"meets_30pct_relative_final":bool(rel is not None and rel>=0.30),
      "validation_stable_30pct_candidates":stable,
      "top20":[{"rules":r["rules"],"fold_2023":r["fold_2023"],"fold_2024":r["fold_2024"],"min_wilson":r["min_wilson"],"combined_signals":r["combined_signals"]} for r in ranked[:20]],
      "final_signals":fs,
    }
    with open("tmp/egx_backtest/results_v3_rules.json","w",encoding="utf-8") as f: json.dump(result,f,ensure_ascii=False,indent=2)
    print(json.dumps({k:result[k] for k in ["pattern","protocol","dataset","v2_benchmark","relative_30pct_targets","atoms","eligible_combos","selected","final_result","relative_improvement_vs_v2_final","meets_30pct_relative_final","validation_stable_30pct_candidates"]},ensure_ascii=False,indent=2))

if __name__=="__main__": main()
