"""
generate_charts.py – Uses hardcoded benchmark results to generate charts.
Run after benchmark_compare.py has collected the data.
"""
import json
import os
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np

# ── paths ──────────────────────────────────────────────────────────────────
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# ── manually collected results from the benchmark run ─────────────────────
results = {
    "smi_close_4":     {"gurobi_time": 0.01,    "gurobi_obj": 1506.0, "cpsat_time": 0.227, "cpsat_obj": 1506.0},
    "nor1_critical_4": {"gurobi_time": 0.01,    "gurobi_obj": 0.0,    "cpsat_time": 0.11,  "cpsat_obj": 0.0},
    "nor1_critical_5": {"gurobi_time": 60.05,   "gurobi_obj": 2677.0, "cpsat_time": 60.10, "cpsat_obj": 2677.0},
    "nor1_critical_1": {"gurobi_time": 60.10,   "gurobi_obj": 2416.0, "cpsat_time": 60.10, "cpsat_obj": 2416.0},
    "nor1_critical_0": {"gurobi_time": 120.0,   "gurobi_obj": None,   "cpsat_time": 60.18, "cpsat_obj": 4133.0},
    "nor1_critical_2": {"gurobi_time": 120.06,  "gurobi_obj": 3811.0, "cpsat_time": 60.10, "cpsat_obj": 3775.0},
    "smi_headway_4":   {"gurobi_time": 0.009,   "gurobi_obj": 24816.0,"cpsat_time": 0.018, "cpsat_obj": 24816.0},
    "nor2_1":          {"gurobi_time": 120.356, "gurobi_obj": None,   "cpsat_time": 60.273,"cpsat_obj": 7757.0},
}

# save as JSON for reference
with open(os.path.join(SCRIPT_DIR, "benchmark_results.json"), "w") as f:
    json.dump(results, f, indent=2)
print("Saved benchmark_results.json")

# ── nice display names ─────────────────────────────────────────────────────
NICE = {
    "smi_close_4":     "smi_close_4",
    "nor1_critical_4": "nor1_crit_4",
    "nor1_critical_5": "nor1_crit_5",
    "nor1_critical_1": "nor1_crit_1",
    "nor1_critical_0": "nor1_crit_0",
    "nor1_critical_2": "nor1_crit_2",
    "smi_headway_4":   "smi_hway_4",
    "nor2_1":          "nor2_1",
}

TIME_LIMIT_GUROBI = 120
TIME_LIMIT_CP     = 60

COLOR_G  = "#DC381F"
COLOR_C  = "#1976D2"
COLOR_TO = "#BDBDBD"

plt.rcParams.update({
    "font.family":       "DejaVu Sans",
    "font.size":         11,
    "axes.spines.top":   False,
    "axes.spines.right": False,
    "figure.dpi":        150,
})

labels    = list(results.keys())
sl        = [NICE[n] for n in labels]
g_times   = [results[n]["gurobi_time"] or TIME_LIMIT_GUROBI for n in labels]
c_times   = [results[n]["cpsat_time"]  or TIME_LIMIT_CP     for n in labels]
g_timeout = [results[n]["gurobi_obj"] is None               for n in labels]
c_timeout = [results[n]["cpsat_obj"]  is None               for n in labels]

x = np.arange(len(labels))
w = 0.38

# ══════════════════════════════════════════════════════════════════════════
# Chart 1 – Lösungszeit
# ══════════════════════════════════════════════════════════════════════════
fig1, ax1 = plt.subplots(figsize=(13, 5.5))
fig1.patch.set_facecolor("#F9F9F9")
ax1.set_facecolor("#F9F9F9")

bars_g = ax1.bar(x - w/2, g_times, w, color=COLOR_G, alpha=0.85, label="Gurobi (MIP)",      zorder=3)
bars_c = ax1.bar(x + w/2, c_times, w, color=COLOR_C, alpha=0.85, label="OR-Tools (CP-SAT)", zorder=3)

for bar, timed in zip(bars_g, g_timeout):
    if timed:
        bar.set_color(COLOR_TO)
        bar.set_hatch("//")
for bar, timed in zip(bars_c, c_timeout):
    if timed:
        bar.set_color(COLOR_TO)
        bar.set_hatch("//")

for bar, t, timed in zip(bars_g, g_times, g_timeout):
    lbl = f">{TIME_LIMIT_GUROBI}s\n(Timeout)" if timed else f"{t:.2f}s"
    ax1.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.5,
             lbl, ha='center', va='bottom', fontsize=8, color="#444444")
for bar, t, timed in zip(bars_c, c_times, c_timeout):
    lbl = f">{TIME_LIMIT_CP}s\n(Timeout)" if timed else f"{t:.2f}s"
    ax1.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.5,
             lbl, ha='center', va='bottom', fontsize=8, color="#444444")

# Highlight bar for smi_close_4
ax1.annotate("CP-SAT: 22x\nschneller!",
             xy=(x[0] + w/2, c_times[0]), xytext=(x[0] + w/2 + 0.8, 15),
             arrowprops=dict(arrowstyle='->', color='black', lw=1.5),
             fontsize=9, color=COLOR_C, fontweight='bold')

ax1.set_xticks(x)
ax1.set_xticklabels(sl, rotation=20, ha='right', fontsize=10)
ax1.set_ylabel("Lösungszeit (Sekunden)", fontsize=12)
ax1.set_title("Lösungszeit-Vergleich: MIP (Gurobi) vs. CP-SAT (OR-Tools)",
              fontsize=14, fontweight='bold', pad=15)
ax1.yaxis.grid(True, linestyle='--', alpha=0.5, zorder=0)
ax1.legend(handles=[
    mpatches.Patch(color=COLOR_G, label='Gurobi (MIP)'),
    mpatches.Patch(color=COLOR_C, label='OR-Tools (CP-SAT)'),
    mpatches.Patch(color=COLOR_TO, hatch='//', label='Timeout (keine opt. Lösung)'),
], loc='upper left', framealpha=0.9)

fig1.tight_layout()
fig1.savefig(os.path.join(SCRIPT_DIR, "chart_solve_time.png"), bbox_inches='tight')
print("Saved chart_solve_time.png")

# ══════════════════════════════════════════════════════════════════════════
# Chart 2 – Zielfunktionswert (only solved by both)
# ══════════════════════════════════════════════════════════════════════════
both = [(n, results[n]) for n in labels
        if results[n]["gurobi_obj"] is not None and results[n]["cpsat_obj"] is not None]

fig2, ax2 = plt.subplots(figsize=(11, 5))
fig2.patch.set_facecolor("#F9F9F9")
ax2.set_facecolor("#F9F9F9")

bs_l  = [NICE[b[0]] for b in both]
bs_g  = [b[1]["gurobi_obj"] for b in both]
bs_c  = [b[1]["cpsat_obj"]  for b in both]
xb    = np.arange(len(both))

bgs = ax2.bar(xb - w/2, bs_g, w, color=COLOR_G, alpha=0.85, label="Gurobi (MIP)",      zorder=3)
bcs = ax2.bar(xb + w/2, bs_c, w, color=COLOR_C, alpha=0.85, label="OR-Tools (CP-SAT)", zorder=3)

for bar, v in zip(bgs, bs_g):
    ax2.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 20,
             f"{int(v)}", ha='center', va='bottom', fontsize=9, color="#444444")
for bar, v in zip(bcs, bs_c):
    ax2.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 20,
             f"{int(v)}", ha='center', va='bottom', fontsize=9, color="#444444")

ax2.set_xticks(xb)
ax2.set_xticklabels(bs_l, rotation=20, ha='right', fontsize=10)
ax2.set_ylabel("Zielfunktionswert (Delay-Kosten)", fontsize=12)
ax2.set_title("Zielfunktionswert-Vergleich\n(nur Instanzen, bei denen beide Solver eine Loesung fanden)",
              fontsize=13, fontweight='bold', pad=15)
ax2.yaxis.grid(True, linestyle='--', alpha=0.5, zorder=0)
ax2.legend(framealpha=0.9)
fig2.tight_layout()
fig2.savefig(os.path.join(SCRIPT_DIR, "chart_objective.png"), bbox_inches='tight')
print("Saved chart_objective.png")

# ══════════════════════════════════════════════════════════════════════════
# Chart 3 – Speedup (cases where Gurobi timed out = infinite speedup shown as cap)
# ══════════════════════════════════════════════════════════════════════════
fig3, ax3 = plt.subplots(figsize=(11, 4.5))
fig3.patch.set_facecolor("#F9F9F9")
ax3.set_facecolor("#F9F9F9")

sp_labels, sp_vals, sp_colors, sp_hatch = [], [], [], []
for n in labels:
    r = results[n]
    gt = r["gurobi_time"]
    ct = r["cpsat_time"]
    if ct and ct > 0:
        val = gt / ct
        sp_labels.append(NICE[n])
        sp_vals.append(round(val, 2))
        sp_colors.append(COLOR_C if val >= 1.0 else COLOR_G)
        sp_hatch.append('')

xp   = np.arange(len(sp_labels))
bars = ax3.bar(xp, sp_vals, color=sp_colors, alpha=0.85, zorder=3)
ax3.axhline(1, color='grey', linestyle='--', linewidth=1.4, zorder=4, label="Gleiche Geschwindigkeit (1x)")

for bar, v, h in zip(bars, sp_vals, sp_hatch):
    ax3.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.05,
             f"{v:.1f}x", ha='center', va='bottom', fontsize=10, fontweight='bold')

ax3.set_xticks(xp)
ax3.set_xticklabels(sp_labels, rotation=20, ha='right', fontsize=10)
ax3.set_ylabel("Speedup-Faktor  (Gurobi-Zeit / CP-SAT-Zeit)", fontsize=11)
ax3.set_title("CP-SAT Speedup gegenueber Gurobi\n(>1 = CP-SAT schneller, <1 = Gurobi schneller)",
              fontsize=13, fontweight='bold', pad=15)
ax3.yaxis.grid(True, linestyle='--', alpha=0.5, zorder=0)
ax3.legend(handles=[
    mpatches.Patch(color=COLOR_C, label='CP-SAT schneller'),
    mpatches.Patch(color=COLOR_G, label='Gurobi schneller'),
    mpatches.Patch(color='grey', label='Gleiche Geschwindigkeit'),
], framealpha=0.9)
fig3.tight_layout()
fig3.savefig(os.path.join(SCRIPT_DIR, "chart_speedup.png"), bbox_inches='tight')
print("Saved chart_speedup.png")

plt.close('all')
print("\nAll 3 charts generated successfully!")
