#!/usr/bin/env python3
"""
run_all.py — regenerate every figure and table in dependency order.

The pipeline is staged: panel build -> estimation -> aggregation -> figures/tables.
Each estimation stage declares the inputs it needs. A stage whose input is absent
(typically the licensed AlgoSeek-derived panels, which are not redistributed) is
skipped, not failed, so a non-licensee still reproduces the schedule, attention,
control, and free-data arms (Binance crypto and the daily home-equity / index /
currency panels), plus every figure and table that rebuilds from the committed
result CSVs in analysis/out/.

Usage:
    python run_all.py                # run everything whose inputs are present
    python run_all.py --list         # show stages and whether each will run/skip
    python run_all.py --only fig      # run only stages whose name matches a substring
    python run_all.py --check         # verify committed inputs against DATA_MANIFEST.sha256

What "present" means is decided per stage by the existence of its declared inputs,
not by a license flag, so the same script reproduces both for a holder and a
non-holder; the holder simply has more inputs on disk and therefore more live stages.
"""
import argparse, hashlib, os, subprocess, sys, time

ROOT = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable

# Derived panels. The crypto panel is built from free Binance klines; the all-market
# panel folds in the licensed AlgoSeek futures/equity/TAQ/options arms.
PANEL_ALL    = "data/market/panel/all_panel.parquet"
PANEL_CRYPTO = "data/market/panel/crypto_panel.parquet"
# Free, committed-or-public daily panels (always present in the repo).
INTL_EQ      = "data/market/equities_intl"
INDICES      = "data/market/indices_daily"
OUT          = "analysis/out"

# (name, script, [required inputs]).  Empty inputs => pure simulation or reads only
# committed CSVs => always runs.  Dependency order is top to bottom.
STAGES = [
    # --- panel build (optional; needs raw market data on disk) -------------------
    ("panel:crypto",      "analysis/build_panel_crypto.py", ["data/market/crypto"]),
    ("panel:all",         "analysis/build_panel.py",        ["data/market/futures"]),

    # --- aggregate channel (Hglobal) --------------------------------------------
    ("agg:crossmarket",   "analysis/regress_crossmarket.py", [PANEL_ALL]),
    ("agg:crypto-core",   "analysis/regressions.py",         [PANEL_CRYPTO]),
    ("agg:event-study",   "analysis/event_study.py",         [PANEL_ALL]),
    ("agg:pre-trend",     "analysis/pre_trend.py",           [PANEL_ALL]),
    ("agg:liquidity",     "analysis/liquidity.py",           ["data/market/liquidity"]),
    ("agg:options",       "analysis/options_analysis.py",    ["data/market/options"]),
    ("agg:efficiency",    "analysis/efficiency.py",          [PANEL_ALL]),
    ("agg:intensity",     "analysis/intensity.py",           [PANEL_ALL]),
    ("agg:breadth",       "analysis/breadth.py",             [PANEL_ALL]),
    ("agg:goal-timing",   "analysis/goal_timing.py",         [PANEL_ALL]),
    ("agg:stakes",        "analysis/stakes.py",              [PANEL_ALL]),

    # --- composition artifacts ---------------------------------------------------
    ("artifact:comov",    "analysis/comovement.py",          [PANEL_ALL]),
    ("artifact:montecarlo","analysis/artifact_montecarlo.py", []),   # pure simulation
    ("artifact:cash-eq",  "analysis/cash_equity.py",         ["data/market/equity"]),

    # --- local channel (Hlocal) and own-team cells ------------------------------
    ("local:domestic",    "analysis/domestic_attention.py",  [PANEL_ALL]),
    ("local:pooled",      "analysis/pooled_domestic.py",     [PANEL_ALL]),
    ("local:own-4tourn",  "analysis/own_team_4tourn.py",     [PANEL_ALL]),
    ("local:fx-country",  "analysis/fx_home_country.py",     [INDICES]),
    ("local:home-equity", "analysis/home_equities.py",       [INTL_EQ]),

    # --- next-day loser effect / sentiment (free daily panels) ------------------
    ("loser:indices",     "analysis/equities_extended.py",   [INDICES]),
    ("loser:fx",          "analysis/fx_exotic_extended.py",  [INDICES]),
    ("loser:calendar",    "analysis/loser_calendar_placebo.py", [INDICES]),
    ("loser:sentiment",   "analysis/sentiment.py",           [INDICES]),

    # --- attention validation (free Wikimedia dumps) ----------------------------
    ("attn:daily",        "analysis/attention_validation.py", ["data/market/crypto"]),
    ("attn:hourly",       "analysis/attention_final.py",      ["data/controls"]),

    # --- few-cluster inference + positive control -------------------------------
    ("infer:wild-boot",   "analysis/wild_bootstrap.py",      [PANEL_ALL]),
    ("infer:pooled-boot", "analysis/pooled_bootstrap.py",    [PANEL_ALL]),
    ("infer:inject",      "analysis/injection_power.py",     [PANEL_ALL]),
    ("infer:inject-conc", "analysis/injection_concentrated.py", [PANEL_ALL]),

    # --- robustness --------------------------------------------------------------
    ("robust:macro",      "analysis/robustness_macro.py",    [PANEL_ALL]),
    ("robust:windows",    "analysis/robustness_windows.py",  [PANEL_ALL]),

    # --- bounds + aggregation (read committed/regenerated out/ CSVs) -------------
    ("bounds:tost",       "analysis/equivalence_tost.py",    [OUT]),
    ("bounds:hypsplit",   "analysis/hypothesis_split.py",    [OUT]),
    ("bounds:validate",   "analysis/validate_and_bounds.py", [OUT]),
    ("bounds:hlocal-feas","analysis/hlocal_feasibility.py",  [OUT]),
    ("pool:master-fdr",   "analysis/master_fdr.py",          [OUT]),

    # --- figures + tables (rebuild from out/, so they always run) ---------------
    ("figures:main",      "figures/make_figures.py",         [OUT]),
    ("figures:paper",     "paper/make_paper_figs.py",        [OUT]),
    ("tables:main",       "analysis/make_tables.py",         [OUT]),
]


def present(rel):
    return os.path.exists(os.path.join(ROOT, rel))


def inputs_ready(needs):
    return all(present(n) for n in needs)


def verify_manifest():
    man = os.path.join(ROOT, "DATA_MANIFEST.sha256")
    if not os.path.exists(man):
        print("DATA_MANIFEST.sha256 not found"); return 1
    bad = miss = ok = 0
    with open(man) as fh:
        for line in fh:
            line = line.rstrip("\n")
            if not line:
                continue
            digest, path = line[:64], line[66:]
            full = os.path.join(ROOT, path)
            if not os.path.exists(full):
                miss += 1; print(f"MISSING  {path}"); continue
            h = hashlib.sha256()
            with open(full, "rb") as f:
                for chunk in iter(lambda: f.read(1 << 20), b""):
                    h.update(chunk)
            if h.hexdigest() == digest:
                ok += 1
            else:
                bad += 1; print(f"MISMATCH {path}")
    print(f"\nmanifest: {ok} ok, {bad} mismatched, {miss} missing")
    return 0 if bad == 0 and miss == 0 else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true", help="show stages and run/skip status")
    ap.add_argument("--only", default=None, help="run only stages whose name contains this")
    ap.add_argument("--check", action="store_true", help="verify inputs against DATA_MANIFEST.sha256")
    ap.add_argument("--keep-going", action="store_true", default=True)
    args = ap.parse_args()

    if args.check:
        sys.exit(verify_manifest())

    stages = [s for s in STAGES if (args.only is None or args.only in s[0])]

    if args.list:
        for name, script, needs in stages:
            status = "RUN " if (present(script) and inputs_ready(needs)) else "skip"
            why = "" if status == "RUN " else " (missing: " + ", ".join(
                n for n in needs if not present(n)) + ")" if needs else " (no script)"
            print(f"  [{status}] {name:22s} {script}{why}")
        return

    ran = skipped = failed = 0
    t0 = time.time()
    for name, script, needs in stages:
        if not present(script):
            print(f"[skip] {name}: {script} not in repo"); skipped += 1; continue
        if not inputs_ready(needs):
            miss = ", ".join(n for n in needs if not present(n))
            print(f"[skip] {name}: input absent ({miss}) — committed CSV retained"); skipped += 1; continue
        print(f"[run ] {name}: {script}")
        rc = subprocess.call([PY, os.path.join(ROOT, script)], cwd=ROOT)
        if rc == 0:
            ran += 1
        else:
            failed += 1; print(f"[FAIL] {name}: exit {rc}")
            if not args.keep_going:
                sys.exit(rc)

    print(f"\ndone in {time.time()-t0:.0f}s — {ran} ran, {skipped} skipped, {failed} failed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
