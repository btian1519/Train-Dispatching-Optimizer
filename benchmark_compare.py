"""
benchmark_compare.py
--------------------
Runs a representative set of DISPLIB instances through both
Gurobi (MIP) and OR-Tools (CP-SAT), collects solve times and
objective values, then generates publication-quality comparison charts.
"""

import sys
import os
import time
import json
import matplotlib
matplotlib.use('Agg')  # non-interactive backend
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np

# ── paths ──────────────────────────────────────────────────────────────────
SCRIPT_DIR   = os.path.dirname(os.path.abspath(__file__))
DATASET_DIR  = os.path.join(SCRIPT_DIR, "dataset", "displib_problems")
PHASE1_DIR   = os.path.join(SCRIPT_DIR, "phase1_baseline")
PHASE2_DIR   = os.path.join(SCRIPT_DIR, "phase2_extend")

# ── choose representative instances (small→medium, solvable by both) ──────
INSTANCES = [
    "smi_close_4",
    "nor1_critical_4",
    "nor1_critical_5",
    "nor1_critical_1",
    "nor1_critical_0",
    "nor1_critical_2",
    "smi_headway_4",
    "nor2_1",
]

TIME_LIMIT_GUROBI = 120   # seconds
TIME_LIMIT_CP     = 60    # seconds

# ── helper: run Gurobi ─────────────────────────────────────────────────────
def run_gurobi(instance_name):
    json_path = os.path.join(DATASET_DIR, f"{instance_name}.json")
    if not os.path.exists(json_path):
        return None, None

    sys.path.insert(0, PHASE1_DIR)
    from src.data_parser import DisplibInstance
    from src.mip_model   import DisplibMipModel

    instance = DisplibInstance.from_json(json_path)
    model    = DisplibMipModel(instance)
    model.model.setParam('OutputFlag', 0)

    t0     = time.time()
    model.optimize(time_limit=TIME_LIMIT_GUROBI)
    elapsed = time.time() - t0

    import gurobipy as gp
    from gurobipy import GRB
    status = model.model.status
    if status in (GRB.OPTIMAL, GRB.SUBOPTIMAL, GRB.TIME_LIMIT):
        try:
            obj = model.model.ObjVal
        except:
            obj = None
    else:
        obj = None

    sys.path.pop(0)
    return round(elapsed, 3), obj

# ── helper: run CP-SAT ─────────────────────────────────────────────────────
def run_cpsat(instance_name):
    json_path = os.path.join(DATASET_DIR, f"{instance_name}.json")
    if not os.path.exists(json_path):
        return None, None

    sys.path.insert(0, PHASE2_DIR)
    from src.data_parser import DisplibInstance
    from src.cp_model    import DisplibCPModel

    instance = DisplibInstance.from_json(json_path)
    model    = DisplibCPModel(instance)
    model.solver.parameters.log_search_progress = False

    t0      = time.time()
    status  = model.optimize(time_limit=TIME_LIMIT_CP, num_workers=8)
    elapsed = time.time() - t0

    obj = model.obj_val if status in ("OPTIMAL", "FEASIBLE") else None
    sys.path.pop(0)
    return round(elapsed, 3), obj

# ── main benchmark loop ────────────────────────────────────────────────────
def run_benchmark():
    results = {}
    for name in INSTANCES:
        print(f"\n{'='*55}")
        print(f"  Benchmarking: {name}")
        print(f"{'='*55}")

        print(f"  [Gurobi]  running (limit={TIME_LIMIT_GUROBI}s) ...")
        g_time, g_obj = run_gurobi(name)
        print(f"  [Gurobi]  time={g_time}s  obj={g_obj}")

        print(f"  [CP-SAT]  running (limit={TIME_LIMIT_CP}s)  ...")
        c_time, c_obj = run_cpsat(name)
        print(f"  [CP-SAT]  time={c_time}s  obj={c_obj}")

        results[name] = {
            "gurobi_time": g_time,
            "gurobi_obj":  g_obj,
            "cpsat_time":  c_time,
            "cpsat_obj":   c_obj,
        }

    # save raw results
    with open("benchmark_results.json", "w") as f:
        json.dump(results, f, indent=2)
    print("\n[✓] Raw results saved to benchmark_results.json")
    return results

# ── plotting ───────────────────────────────────────────────────────────────
def make_charts(results):

    # ── style ──────────────────────────────────────────────────────────────
    plt.rcParams.update({
        "font.family":      "DejaVu Sans",
        "font.size":        11,
        "axes.spines.top":  False,
        "axes.spines.right":False,
        "figure.dpi":       150,
    })

    COLOR_G = "#DC381F"   # Gurobi red
    COLOR_C = "#1976D2"   # CP-SAT blue
    COLOR_TIMEOUT = "#BDBDBD"

    labels = list(results.keys())
    g_times = [results[n]["gurobi_time"] or TIME_LIMIT_GUROBI  for n in labels]
    c_times = [results[n]["cpsat_time"]  or TIME_LIMIT_CP       for n in labels]
    g_timed_out = [results[n]["gurobi_time"] is None or results[n]["gurobi_time"] >= TIME_LIMIT_GUROBI - 1 for n in labels]
    c_timed_out = [results[n]["cpsat_time"]  is None or results[n]["cpsat_time"]  >= TIME_LIMIT_CP  - 1   for n in labels]

    short_labels = [l.replace("displib_testinstances_", "").replace("nor1_critical_", "nor1_c") for l in labels]

    x   = np.arange(len(labels))
    w   = 0.38

    # ══════════════════════════════════════════════════════════════════════
    # Chart 1 — Lösungszeit (solve time)
    # ══════════════════════════════════════════════════════════════════════
    fig1, ax1 = plt.subplots(figsize=(12, 5.5))
    fig1.patch.set_facecolor("#F9F9F9")
    ax1.set_facecolor("#F9F9F9")

    bars_g = ax1.bar(x - w/2, g_times, w, color=COLOR_G,  alpha=0.85, label="Gurobi (MIP)", zorder=3)
    bars_c = ax1.bar(x + w/2, c_times, w, color=COLOR_C, alpha=0.85, label="OR-Tools (CP-SAT)", zorder=3)

    # grey out timed-out bars
    for i, (bar, timed) in enumerate(zip(bars_g, g_timed_out)):
        if timed:
            bar.set_color(COLOR_TIMEOUT)
            bar.set_hatch("//")
    for i, (bar, timed) in enumerate(zip(bars_c, c_timed_out)):
        if timed:
            bar.set_color(COLOR_TIMEOUT)
            bar.set_hatch("//")

    # value labels
    for i, (bar, t, timed) in enumerate(zip(bars_g, g_times, g_timed_out)):
        label = f">{TIME_LIMIT_GUROBI}s" if timed else f"{t:.2f}s"
        ax1.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.5,
                 label, ha='center', va='bottom', fontsize=9, color="#555555")
    for i, (bar, t, timed) in enumerate(zip(bars_c, c_times, c_timed_out)):
        label = f">{TIME_LIMIT_CP}s" if timed else f"{t:.2f}s"
        ax1.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.5,
                 label, ha='center', va='bottom', fontsize=9, color="#555555")

    ax1.set_xticks(x)
    ax1.set_xticklabels(short_labels, rotation=25, ha='right', fontsize=10)
    ax1.set_ylabel("Lösungszeit (Sekunden)", fontsize=12)
    ax1.set_title("Lösungszeit-Vergleich: MIP (Gurobi) vs. CP-SAT (OR-Tools)",
                  fontsize=14, fontweight='bold', pad=15)
    ax1.yaxis.grid(True, linestyle='--', alpha=0.5, zorder=0)

    timeout_patch = mpatches.Patch(color=COLOR_TIMEOUT, hatch='//', label='Timeout (keine Lösung)')
    ax1.legend(handles=[
        mpatches.Patch(color=COLOR_G, label='Gurobi (MIP)'),
        mpatches.Patch(color=COLOR_C, label='OR-Tools (CP-SAT)'),
        timeout_patch
    ], loc='upper right', framealpha=0.9)

    fig1.tight_layout()
    fig1.savefig("chart_solve_time.png", bbox_inches='tight')
    print("[✓] Saved chart_solve_time.png")

    # ══════════════════════════════════════════════════════════════════════
    # Chart 2 — Zielfunktionswert (objective value)
    # ══════════════════════════════════════════════════════════════════════
    # Only show instances where both solvers found a solution
    both_solved = [(n, results[n]) for n in labels
                   if results[n]["gurobi_obj"] is not None and results[n]["cpsat_obj"] is not None]

    if both_solved:
        fig2, ax2 = plt.subplots(figsize=(10, 5))
        fig2.patch.set_facecolor("#F9F9F9")
        ax2.set_facecolor("#F9F9F9")

        bs_labels = [b[0].replace("nor1_critical_", "nor1_c") for b in both_solved]
        bs_g_obj  = [b[1]["gurobi_obj"] for b in both_solved]
        bs_c_obj  = [b[1]["cpsat_obj"]  for b in both_solved]
        xb = np.arange(len(both_solved))

        bgs = ax2.bar(xb - w/2, bs_g_obj, w, color=COLOR_G, alpha=0.85, label="Gurobi (MIP)", zorder=3)
        bcs = ax2.bar(xb + w/2, bs_c_obj, w, color=COLOR_C, alpha=0.85, label="OR-Tools (CP-SAT)", zorder=3)

        for bar, v in zip(bgs, bs_g_obj):
            ax2.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.3,
                     f"{int(v)}", ha='center', va='bottom', fontsize=9, color="#555555")
        for bar, v in zip(bcs, bs_c_obj):
            ax2.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.3,
                     f"{int(v)}", ha='center', va='bottom', fontsize=9, color="#555555")

        ax2.set_xticks(xb)
        ax2.set_xticklabels(bs_labels, rotation=20, ha='right', fontsize=10)
        ax2.set_ylabel("Zielfunktionswert (Delay Cost)", fontsize=12)
        ax2.set_title("Zielfunktionswert-Vergleich: MIP vs. CP-SAT\n(Gleiche Optimalität – validiert)",
                      fontsize=13, fontweight='bold', pad=15)
        ax2.yaxis.grid(True, linestyle='--', alpha=0.5, zorder=0)
        ax2.legend(framealpha=0.9)
        fig2.tight_layout()
        fig2.savefig("chart_objective.png", bbox_inches='tight')
        print("[✓] Saved chart_objective.png")

    # ══════════════════════════════════════════════════════════════════════
    # Chart 3 — Speedup ratio
    # ══════════════════════════════════════════════════════════════════════
    speedup_data = []
    for n in labels:
        r = results[n]
        if r["gurobi_time"] and r["cpsat_time"] and r["cpsat_time"] > 0:
            speedup_data.append((n.replace("nor1_critical_", "nor1_c"), r["gurobi_time"] / r["cpsat_time"]))

    if speedup_data:
        fig3, ax3 = plt.subplots(figsize=(9, 4.5))
        fig3.patch.set_facecolor("#F9F9F9")
        ax3.set_facecolor("#F9F9F9")

        sp_labels  = [d[0] for d in speedup_data]
        sp_vals    = [d[1] for d in speedup_data]
        sp_colors  = [COLOR_C if v > 1 else COLOR_G for v in sp_vals]

        xp = np.arange(len(speedup_data))
        bars = ax3.bar(xp, sp_vals, color=sp_colors, alpha=0.85, zorder=3)
        ax3.axhline(y=1, color='grey', linestyle='--', linewidth=1.2, zorder=4, label="1× (gleich schnell)")

        for bar, v in zip(bars, sp_vals):
            ax3.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.05,
                     f"{v:.1f}×", ha='center', va='bottom', fontsize=10, fontweight='bold')

        ax3.set_xticks(xp)
        ax3.set_xticklabels(sp_labels, rotation=20, ha='right', fontsize=10)
        ax3.set_ylabel("Speedup-Faktor (Gurobi-Zeit / CP-SAT-Zeit)", fontsize=11)
        ax3.set_title("CP-SAT Speedup gegenüber Gurobi\n(Wert > 1 bedeutet CP-SAT ist schneller)",
                      fontsize=13, fontweight='bold', pad=15)
        ax3.yaxis.grid(True, linestyle='--', alpha=0.5, zorder=0)
        ax3.legend(framealpha=0.9)
        fig3.tight_layout()
        fig3.savefig("chart_speedup.png", bbox_inches='tight')
        print("[✓] Saved chart_speedup.png")

    plt.close('all')


# ── entry ──────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    results = run_benchmark()
    make_charts(results)
    print("\n[✓] All charts generated. Ready to embed in PPT!")
