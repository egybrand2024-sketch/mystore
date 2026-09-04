import itertools, json, math, os, glob, sys
sys.path.insert(0, "tmp/egx_backtest")
import backtest_v3_ml as v3

# High-selectivity interpretable research.
# Atomic rule thresholds are derived ONLY from 2021-2022 distributions.
# Rule combinations are selected on separate 2023 and 2024 folds.
# 2025-2026 is evaluated only after selection.

CAL = ("2021-01-01", "2022-12-31")
VAL1 = ("2023-01-01", "2023-12-31")
VAL2 = ("2024-01-01", "2024-12-31")
FINAL = ("2025-01-01", "2026-02-28")
MIN_FOLD_SIGNALS = 10
MIN_FOLD_SYMBOLS = 8
MAX_RULES = 5


def q(vals, p):
    vals = sorted(float(x) for x in vals if x is not None and math.isfinite(float(x)))
    if not vals:
        return 0.0
    idx = (len(vals)-1)*p
    lo = int(math.floor(idx)); hi = int(math.ceil(idx))
    if lo == hi: return vals[lo]
    return vals[lo]*(hi-idx)+vals[hi]*(idx-lo)


def in_period(s, period):
    return period[0] <= s["date"] <= period[1]


def build_signals():
    root=os.environ.get("EGX_DATA_ROOT","egxdata/Dataset/raw")
    files=sorted(glob.glob(os.path.join(root,"*","*.csv")))
    data={}
    for path in files:
        sym=os.path.basename(path).split(".")[0].upper()
        rows=v3.load_csv_all(path)
        if len(rows)>=100: data[sym]=rows
    market=v3.build_market_maps(data)
    sigs=[]
    for sym,rows in data.items(): sigs.extend(v3.collect_signals(sym,rows,market))
    sigs.sort(key=lambda s:(s["date"],s["symbol"]))
    return sigs, len(files), len(data)


def atom(name, fn, desc):
    return {"name":name,"fn":fn,"desc":desc}


def build_atoms(cal):
    atoms=[]
    # Distribution-based thresholds avoid tuning literal values on validation years.
    specs=[
      ("clv","ge",[0.50,0.65,0.75]),
      ("upper_wick","le",[0.25,0.35,0.50]),
      ("base_range","le",[0.25,0.40,0.55]),
      ("body","ge",[0.50,0.65,0.75]),
      ("breakout_ret","le",[0.50,0.65,0.80]),
      ("breakout_vol_ratio","ge",[0.50,0.65,0.75]),
      ("breakout_vs_60_high","ge",[0.40,0.55,0.70]),
      ("dist_60_high","ge",[0.40,0.55,0.70]),
      ("pre60_ret","ge",[0.40,0.55,0.70]),
      ("close_vs_sma50","ge",[0.40,0.55,0.70]),
      ("rs20","ge",[0.40,0.55,0.70]),
      ("market20_ret","ge",[0.35,0.50,0.65]),
      ("market_breadth20","ge",[0.35,0.50,0.65]),
      ("compression_ratio","le",[0.35,0.50,0.65]),
      ("base_vs_prior_atr","le",[0.35,0.50,0.65]),
      ("nearest_overhead_pct","ge",[0.40,0.55,0.70]),
      ("up_volume_share","ge",[0.40,0.55,0.70]),
      ("resistance_touches","ge",[0.35,0.50,0.65]),
      ("base_low_slope","ge",[0.40,0.55,0.70]),
      ("prebreak_vol_ratio","ge",[0.40,0.55,0.70]),
    ]
    for feat,op,ps in specs:
        vals=[s[feat] for s in cal if s.get(feat) is not None]
        for p in ps:
            thr=q(vals,p)
            if op=="ge":
                atoms.append(atom(f"{feat}_ge_q{int(p*100)}",lambda s,f=feat,t=thr: s.get(f) is not None and s[f]>=t,f"{feat} >= {thr:.6g} (calibration q{p:.2f})"))
            else:
                atoms.append(atom(f"{feat}_le_q{int(p*100)}",lambda s,f=feat,t=thr: s.get(f) is not None and s[f]<=t,f"{feat} <= {thr:.6g} (calibration q{p:.2f})"))
    # Structural atoms not optimized by literal value.
    atoms.append(atom("v2_flag","lambda", "v2_flag == 1"))
    atoms[-1]["fn"] = lambda s: s.get("v2_flag",0)>0
    atoms.append(atom("bullish_market20","lambda", "market20_ret > 0")); atoms[-1]["fn"] = lambda s: s.get("market20_ret",0)>0
    atoms.append(atom("near_60d_high","lambda", "dist_60_high >= -5%")); atoms[-1]["fn"] = lambda s: s.get("dist_60_high",-9)>=-0.05
    atoms.append(atom("small_upper_wick","lambda", "upper_wick <= 20% of candle")); atoms[-1]["fn"] = lambda s: s.get("upper_wick",9)<=0.20
    return atoms


def passes_combo(s, combo):
    return all(a["fn"](s) for a in combo)


def eval_combo(sigs, combo):
    sel=[s for s in sigs if passes_combo(s,combo)]
    sm=v3.summary(sel)
    return sel,sm


def main():
    all_sigs,files_found,stocks=build_signals()
    cal=[s for s in all_sigs if in_period(s,CAL)]
    va=[s for s in all_sigs if in_period(s,VAL1)]
    vb=[s for s in all_sigs if in_period(s,VAL2)]
    final=[s for s in all_sigs if in_period(s,FINAL)]
    atoms=build_atoms(cal)

    # Remove same-feature alternatives from a combo to reduce threshold-cherry-picking.
    def family(atom):
        n=atom["name"]
        for f in v3.FEATURES:
            if n.startswith(f+"_"): return f
        return n

    ranked=[]
    for k in range(2,MAX_RULES+1):
        for combo in itertools.combinations(atoms,k):
            fam=[family(a) for a in combo]
            if len(set(fam))<len(fam): continue
            sa,a=eval_combo(va,combo); sb,b=eval_combo(vb,combo)
            if a["signals"]<MIN_FOLD_SIGNALS or b["signals"]<MIN_FOLD_SIGNALS: continue
            if a["unique_symbols"]<MIN_FOLD_SYMBOLS or b["unique_symbols"]<MIN_FOLD_SYMBOLS: continue
            la=v3.wilson_lower(a["wins"],a["signals"],1.0); lb=v3.wilson_lower(b["wins"],b["signals"],1.0)
            ranked.append({
              "rules":[x["desc"] for x in combo],"rule_names":[x["name"] for x in combo],
              "fold_2023":a,"fold_2024":b,"min_wilson":min(la,lb),"avg_wilson":v3.mean([la,lb]),
              "min_win_rate":min(a["win_rate"],b["win_rate"]),"avg_win_rate":v3.mean([a["win_rate"],b["win_rate"]]),
              "combined_signals":a["signals"]+b["signals"],
              "combo":combo,
            })
    ranked.sort(key=lambda x:(x["min_wilson"],x["avg_wilson"],x["min_win_rate"],x["combined_signals"]),reverse=True)
    best=ranked[0]
    _,fs=eval_combo(final,best["combo"])
    final_sigs=[s for s in final if passes_combo(s,best["combo"])]
    v2_final=v3.summary([s for s in final if s["v2_flag"]>0])
    rel=(fs["win_rate"]/v2_final["win_rate"]-1) if fs["win_rate"] is not None and v2_final["win_rate"] else None

    # Also report every validation-stable configuration that exceeded the requested relative target
    # against the frozen v2 validation baselines, without using final-period results for ranking.
    v2a=v3.summary([s for s in va if s["v2_flag"]>0]); v2b=v3.summary([s for s in vb if s["v2_flag"]>0])
    target_a=(v2a["win_rate"] or 0)*1.30; target_b=(v2b["win_rate"] or 0)*1.30
    stable30=[]
    for r in ranked:
        if r["fold_2023"]["win_rate"]>=target_a and r["fold_2024"]["win_rate"]>=target_b:
            combo=next(x["combo"] for x in ranked if x["rule_names"]==r["rule_names"])
            _,ff=eval_combo(final,combo)
            stable30.append({k:r[k] for k in ["rules","rule_names","fold_2023","fold_2024","min_wilson","avg_wilson","combined_signals"]}|{"final":ff})
            if len(stable30)>=20: break

    result={
      "pattern":"Defensive Lift v3 high-selectivity rule research",
      "protocol":{
        "threshold_calibration":CAL,"validation_fold_1":VAL1,"validation_fold_2":VAL2,"final_evaluation":FINAL,
        "final_not_used_for_selection":True,"minimum_signals_per_fold":MIN_FOLD_SIGNALS,"minimum_symbols_per_fold":MIN_FOLD_SYMBOLS,
        "max_rules":MAX_RULES,"ranking":"maximize weaker fold 1-sigma Wilson lower bound",
      },
      "dataset":{"files_found":files_found,"stocks_loaded":stocks,"signals":len(all_sigs)},
      "v2_benchmark":{"2023":v2a,"2024":v2b,"final":v2_final},
      "requested_30pct_relative_validation_targets":{"2023":target_a,"2024":target_b,"final_reference":(v2_final["win_rate"] or 0)*1.30},
      "atoms_count":len(atoms),"eligible_combos":len(ranked),
      "selected":{"rules":best["rules"],"rule_names":best["rule_names"],"fold_2023":best["fold_2023"],"fold_2024":best["fold_2024"],"min_wilson":best["min_wilson"],"avg_wilson":best["avg_wilson"],"combined_signals":best["combined_signals"]},
      "final_result":fs,"relative_improvement_vs_v2_final":rel,"meets_30pct_relative_final":bool(rel is not None and rel>=0.30),
      "validation_stable_30pct_candidates":stable30,
      "top20":[{k:r[k] for k in ["rules","rule_names","fold_2023","fold_2024","min_wilson","avg_wilson","min_win_rate","avg_win_rate","combined_signals"]} for r in ranked[:20]],
      "final_signals":final_sigs,
    }
    with open("tmp/egx_backtest/results_v3_rules.json","w",encoding="utf-8") as f: json.dump(result,f,ensure_ascii=False,indent=2)
    compact={k:result[k] for k in ["pattern","protocol","dataset","v2_benchmark","requested_30pct_relative_validation_targets","atoms_count","eligible_combos","selected","final_result","relative_improvement_vs_v2_final","meets_30pct_relative_final","validation_stable_30pct_candidates"]}
    print(json.dumps(compact,ensure_ascii=False,indent=2))

if __name__=="__main__": main()
