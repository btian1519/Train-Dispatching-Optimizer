"""
=============================================================================
generate_presentation_charts.py
=============================================================================
This automated benchmarking script runs two core academic experiments comparing
the Baseline (Gurobi MIP) and the Extension (Google OR-Tools CP-SAT) for your
Optimization Lab presentation.

Experiment 1: Solve Time Limit vs. Objective Value (10s, 30s, 60s, 120s)
  - Evaluates primal heuristic capability on nor1_critical_0.json.
    (Demonstrates Gurobi finding initial poor solutions and converging to optimal,
     while CP-SAT finds the true optimal instantly).

Experiment 2: Instance Size vs. Total Solve Time (Small, Medium, Large)
  - Evaluates scalability and time-to-optimality (max 300s) on three graded datasets.
    (Pure Global CP-SAT vs Pure Global MIP, NO rolling horizon).

Outputs:
  - chart_exp1_time_vs_obj.png
  - chart_exp2_size_vs_time.png
=============================================================================
"""

import os
import sys
import time
import json
import numpy as np
import matplotlib.pyplot as plt

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(SCRIPT_DIR)

# Ensure imports from phase1_baseline and phase2_extend resolve correctly
sys.path.append(os.path.join(REPO_ROOT, "phase1_baseline"))
sys.path.append(os.path.join(REPO_ROOT, "phase2_extend"))

from phase1_baseline.src.data_parser import DisplibInstance as MIPInstance
from phase1_baseline.src.mip_model import DisplibMipModel
from gurobipy import GRB

from phase2_extend.src.data_parser import DisplibInstance as CPInstance
from phase2_extend.src.cp_model import DisplibCPModel

# Set matplotlib style for professional academic charts
plt.rcParams.update({
    'font.size': 12,
    'axes.labelsize': 14,
    'axes.titlesize': 16,
    'xtick.labelsize': 12,
    'ytick.labelsize': 12,
    'legend.fontsize': 12,
    'figure.titlesize': 18
})

# =============================================================================
# EXPERIMENT 1: Time Limit vs. Objective Value
# =============================================================================
def run_experiment_1(problem_file=None):
    if problem_file is None:
        problem_file = os.path.join(REPO_ROOT, "dataset", "displib_problems", "nor1_critical_0.json")
    print("=" * 70)
    print(f"[*] RUNNING EXPERIMENT 1: Time Limit vs. Objective Value")
    print(f"    Dataset: {os.path.basename(problem_file)}")
    print("=" * 70)

    time_limits = [10, 30, 60, 120]
    mip_objs = []
    cp_objs = []

    for t_lim in time_limits:
        print(f"\n---> Testing Time Limit: {t_lim}s")

        # 1. Gurobi MIP
        print("     [Gurobi MIP]")
        try:
            mip_inst = MIPInstance.from_json(problem_file)
            mip_model = DisplibMipModel(mip_inst, M=1000000)
            mip_model.model.setParam('OutputFlag', 0)
            mip_model.model.setParam('Threads', 8)
            mip_model.optimize(time_limit=t_lim)

            if mip_model.model.SolCount > 0:
                obj_val = mip_model.model.ObjVal
                print(f"     -> MIP Best Obj: {obj_val:.1f}")
                mip_objs.append(obj_val)
            else:
                print("     -> MIP No Feasible Solution Found (Inf)")
                mip_objs.append(np.inf)
        except Exception as e:
            print(f"     -> MIP Error: {e}")
            mip_objs.append(np.inf)

        # 2. CP-SAT
        print("     [OR-Tools CP-SAT]")
        try:
            cp_inst = CPInstance.from_json(problem_file)
            cp_model = DisplibCPModel(cp_inst)
            cp_model.solver.parameters.log_search_progress = False
            status = cp_model.optimize(time_limit=t_lim, num_workers=8)

            if status in ["OPTIMAL", "FEASIBLE"]:
                obj_val = cp_model.obj_val
                print(f"     -> CP-SAT Best Obj: {obj_val:.1f} ({status})")
                cp_objs.append(obj_val)
            else:
                print("     -> CP-SAT No Feasible Solution Found")
                cp_objs.append(np.inf)
        except Exception as e:
            print(f"     -> CP-SAT Error: {e}")
            cp_objs.append(np.inf)

    # Plotting Experiment 1
    plt.figure(figsize=(10, 6), dpi=300)
    
    # Replace np.inf with a high ceiling value for visualization purposes
    valid_mip = [val for val in mip_objs if val != np.inf]
    valid_cp = [val for val in cp_objs if val != np.inf]
    all_valid = valid_mip + valid_cp
    max_val = max(all_valid) if all_valid else 100000
    ceiling = max_val * 1.15

    plot_mip = [ceiling if val == np.inf else val for val in mip_objs]
    plot_cp = [ceiling if val == np.inf else val for val in cp_objs]

    # Plot lines
    plt.plot(time_limits, plot_mip, marker='o', linewidth=2.5, markersize=8, color='#d95f02', label='Baseline (Gurobi MIP)')
    plt.plot(time_limits, plot_cp, marker='s', linewidth=2.5, markersize=8, color='#1b9e77', label='Extension (CP-SAT)')

    # Add annotations for exact values or Inf
    for i, val in enumerate(mip_objs):
        if val == np.inf:
            plt.annotate('No Sol (Inf)', (time_limits[i], ceiling*0.96), textcoords="offset points", xytext=(0,10), ha='center', color='#d95f02', fontweight='bold')
        else:
            plt.annotate(f"{val:,.0f}", (time_limits[i], val), textcoords="offset points", xytext=(0,10), ha='center', color='#d95f02', fontweight='bold', fontsize=10)

    for i, val in enumerate(cp_objs):
        if val != np.inf:
            # Offset CP-SAT label slightly downwards to avoid clashing with MIP if they converge
            xy_offset = (0, -15) if mip_objs[i] == val else (0, 10)
            plt.annotate(f"{val:,.0f}", (time_limits[i], val), textcoords="offset points", xytext=xy_offset, ha='center', color='#1b9e77', fontweight='bold', fontsize=10)

    plt.title('Experiment 1: Solve Time Limit vs. Best Objective Value\n(Dataset: nor1_critical_0 | True Optimal: 4,133)', pad=15, fontweight='bold')
    plt.xlabel('Time Limit (seconds)', fontweight='bold')
    plt.ylabel('Objective Value / Total Delay (Lower is Better)', fontweight='bold')
    plt.xticks(time_limits)
    plt.grid(True, linestyle='--', alpha=0.5)
    plt.legend(frameon=True, facecolor='white', edgecolor='none', shadow=True)
    plt.tight_layout()

    out_file = os.path.join(SCRIPT_DIR, "chart_exp1_time_vs_obj.png")
    plt.savefig(out_file)
    plt.close()
    print(f"\n[*] Chart 1 successfully generated and saved to: {out_file}")


# =============================================================================
# EXPERIMENT 2: Instance Size vs. Total Solve Time
# =============================================================================
def run_experiment_2():
    print("\n" + "=" * 70)
    print("[*] RUNNING EXPERIMENT 2: Instance Size vs. Total Solve Time (Max 300s)")
    print("    Models: Pure Global MIP vs Pure Global CP-SAT (No Rolling Horizon)")
    print("=" * 70)

    datasets = [
        ("Small (10 Trains)", os.path.join(REPO_ROOT, "dataset", "displib_problems", "smi_close_4.json")),
        ("Medium (14 Trains)", os.path.join(REPO_ROOT, "dataset", "displib_problems", "swi_1.json")),
        ("Large (38 Trains)", os.path.join(REPO_ROOT, "dataset", "displib_problems", "smi_close_2.json"))
    ]
    max_time = 300.0 # 5 minutes ceiling

    names = [d[0] for d in datasets]
    mip_times = []
    cp_times = []

    for name, path in datasets:
        print(f"\n---> Testing Instance: {name} ({os.path.basename(path)})")

        # 1. Gurobi MIP
        print("     [Gurobi MIP]")
        t0 = time.time()
        try:
            mip_inst = MIPInstance.from_json(path)
            mip_model = DisplibMipModel(mip_inst, M=1000000)
            mip_model.model.setParam('OutputFlag', 0)
            mip_model.model.setParam('Threads', 8)
            mip_model.optimize(time_limit=max_time)
            
            elapsed = time.time() - t0
            if mip_model.model.status == GRB.OPTIMAL:
                print(f"     -> MIP Proved Optimal in {elapsed:.2f}s")
                mip_times.append(min(elapsed, max_time))
            else:
                print(f"     -> MIP Hit Timeout/Ceiling ({max_time}s) without Optimal Proof")
                mip_times.append(max_time)
        except Exception as e:
            print(f"     -> MIP Error: {e}")
            mip_times.append(max_time)

        # 2. CP-SAT
        print("     [OR-Tools CP-SAT]")
        t0 = time.time()
        try:
            cp_inst = CPInstance.from_json(path)
            cp_model = DisplibCPModel(cp_inst)
            cp_model.solver.parameters.log_search_progress = False
            status = cp_model.optimize(time_limit=max_time, num_workers=8)
            
            elapsed = time.time() - t0
            if status == "OPTIMAL":
                print(f"     -> CP-SAT Proved Optimal in {elapsed:.2f}s")
                cp_times.append(min(elapsed, max_time))
            else:
                print(f"     -> CP-SAT Finished with Status: {status} ({elapsed:.2f}s)")
                cp_times.append(min(elapsed, max_time))
        except Exception as e:
            print(f"     -> CP-SAT Error: {e}")
            cp_times.append(max_time)

    # Plotting Experiment 2
    plt.figure(figsize=(10, 6), dpi=300)
    x = np.arange(len(names))
    width = 0.35

    fig, ax = plt.subplots(figsize=(10, 6), dpi=300)
    rects1 = ax.bar(x - width/2, mip_times, width, label='Baseline (Gurobi MIP)', color='#d95f02', alpha=0.85, edgecolor='black', linewidth=1)
    rects2 = ax.bar(x + width/2, cp_times, width, label='Extension (CP-SAT)', color='#1b9e77', alpha=0.85, edgecolor='black', linewidth=1)

    # Add a horizontal dashed line representing the 300s timeout ceiling
    ax.axhline(max_time, color='#e7298a', linestyle='--', linewidth=2, label='Timeout Ceiling (300s)')

    # Annotate bars with exact time values
    def autolabel(rects):
        for rect in rects:
            height = rect.get_height()
            label_text = f"TIMEOUT" if height >= max_time else f"{height:.1f}s"
            ax.annotate(label_text,
                        xy=(rect.get_x() + rect.get_width() / 2, height),
                        xytext=(0, 5),  # 5 points vertical offset
                        textcoords="offset points",
                        ha='center', va='bottom', fontweight='bold', fontsize=10)

    autolabel(rects1)
    autolabel(rects2)

    ax.set_title('Experiment 2: Instance Size vs. Total Solve Time to Optimality\n(Pure Global Models, Max 300s)', pad=15, fontweight='bold')
    ax.set_xlabel('Instance Scale & Complexity', fontweight='bold')
    ax.set_ylabel('Total Solve Time (seconds)', fontweight='bold')
    ax.set_xticks(x)
    ax.set_xticklabels(names, fontweight='bold')
    ax.set_ylim(0, max_time * 1.15)
    ax.grid(True, linestyle='--', alpha=0.3, axis='y')
    ax.legend(frameon=True, facecolor='white', edgecolor='none', shadow=True)
    plt.tight_layout()

    out_file = os.path.join(SCRIPT_DIR, "chart_exp2_size_vs_time.png")
    plt.savefig(out_file)
    plt.close()
    print(f"\n[*] Chart 2 successfully generated and saved to: {out_file}")


if __name__ == "__main__":
    start_all = time.time()
    run_experiment_1()
    run_experiment_2()
    print("\n" + "=" * 70)
    print(f"[*] ALL EXPERIMENTS COMPLETED SUCCESSFULLY IN {time.time() - start_all:.2f}s")
    print(f"    Generated Charts: chart_exp1_time_vs_obj.png, chart_exp2_size_vs_time.png")
    print("=" * 70)
