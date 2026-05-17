import os
import sys
import time
import glob
import tkinter as tk
from tkinter import filedialog
from src.data_parser import DisplibInstance
from src.cp_model import DisplibCPModel

sys.stdout.reconfigure(encoding='utf-8')

# =============================================================================
# Solver Mode Constants
# =============================================================================
MODE_STANDARD = "standard"  # Direct CP-SAT, global solve
MODE_DISJOINT = "disjoint"  # Rolling Horizon – Disjoint / Greedy batches
MODE_OVERLAP  = "overlap"   # Rolling Horizon – Overlapping / Look-ahead


def run_single_test(test_file, script_dir, is_batch=False, mode=MODE_STANDARD):
    filename  = os.path.basename(test_file)
    test_name = filename.replace('.json', '')
    print(f"{'='*60}")
    print(f"Testing Instance [CP Model]: {test_name}")
    print(f"{'='*60}")

    try:
        out_dir = os.path.join(script_dir, "output")
        os.makedirs(out_dir, exist_ok=True)

        # ------------------------------------------------------------------
        # Mode: Disjoint Rolling Horizon (rolling_horizon.py)
        # ------------------------------------------------------------------
        if mode == MODE_DISJOINT:
            from rolling_horizon import solve_rolling_horizon
            out_file = os.path.join(out_dir, f"solution_rh_{test_name}.json")
            solve_rolling_horizon(test_file, out_file, batch_size=10, time_limit_per_batch=30)
            return

        # ------------------------------------------------------------------
        # Mode: Overlapping Rolling Horizon (rolling_horizon_overlap.py)
        # ------------------------------------------------------------------
        if mode == MODE_OVERLAP:
            from rolling_horizon_overlap import solve_overlapping_rolling_horizon
            out_file = os.path.join(out_dir, f"solution_rh_overlap_{test_name}.json")
            solve_overlapping_rolling_horizon(
                dataset_path=test_file,
                output_path=out_file,
                window_size=10,
                step_size=5,
                time_limit_per_batch=30
            )
            return

        # ------------------------------------------------------------------
        # Mode: Standard CP-SAT – global solve, no decomposition
        # ------------------------------------------------------------------
        instance = DisplibInstance.from_json(test_file)
        print(f"-> Loaded {len(instance.trains)} trains and their interval requirements.")

        start_time = time.time()
        cp_model = DisplibCPModel(instance)

        if is_batch:
            cp_model.solver.parameters.log_search_progress = False
            time_limit = 60
        else:
            cp_model.solver.parameters.log_search_progress = True
            time_limit = 30

        print(f"-> CP Model constructed in {time.time() - start_time:.2f} s. "
              f"Optimizing (Max {time_limit}s)...")

        opt_start = time.time()
        status    = cp_model.optimize(time_limit=time_limit)
        opt_time  = time.time() - opt_start

        if status in ["OPTIMAL", "FEASIBLE"]:
            print(f"-> Status: {status} (Time: {opt_time:.2f}s, ObjVal: {cp_model.obj_val})")
            out_file = os.path.join(out_dir, f"solution_{test_name}.json")
            cp_model.export_solution(out_file)
            print(f"Solution successfully exported to {out_file}")
        elif status == "INFEASIBLE":
            print(f"-> Status: INFEASIBLE (Time: {opt_time:.2f}s) - Model has no solution.")
            print(f"-> Skipped export: No feasible solution found.")
        else:
            print(f"-> Status: {status} (Time: {opt_time:.2f}s)")

    except Exception as e:
        import traceback
        print(f"!!! Error processing {test_name}: {e}")
        traceback.print_exc()

    print("\n")


def pick_solver_mode() -> str:
    """Interactive sub-menu: let the user pick which solver to use."""
    print()
    print("  ┌─────────────────────────────────────────────────────────────┐")
    print("  │            Select a Solving Algorithm                       │")
    print("  ├─────────────────────────────────────────────────────────────┤")
    print("  │  [1]  Standard CP-SAT          (Global, exact)             │")
    print("  │       Best for small/medium instances  (< ~50 trains)      │")
    print("  │                                                             │")
    print("  │  [2]  Disjoint Rolling Horizon (Greedy, fastest)           │")
    print("  │       Batch = 10 trains, no look-ahead                     │")
    print("  │       Great for very large datasets (speed priority)        │")
    print("  │                                                             │")
    print("  │  [3]  Overlapping Rolling Horizon (Look-ahead, better obj) │")
    print("  │       Window = 10 trains, commit = 5, look-ahead = 5       │")
    print("  │       Trades ~2× time for improved solution quality         │")
    print("  └─────────────────────────────────────────────────────────────┘")
    mode_input = input("  Enter your choice (1 / 2 / 3): ").strip()

    if mode_input == '2':
        print("\n  -> Mode: Disjoint Rolling Horizon  [rolling_horizon.py]")
        return MODE_DISJOINT
    elif mode_input == '3':
        print("\n  -> Mode: Overlapping Rolling Horizon / Look-ahead  [rolling_horizon_overlap.py]")
        return MODE_OVERLAP
    else:
        if mode_input != '1':
            print(f"\n  (Unrecognised input '{mode_input}', defaulting to Standard CP-SAT)")
        print("\n  -> Mode: Standard CP-SAT  [cp_model.py]")
        return MODE_STANDARD


def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir)   # make sure src/ imports resolve correctly

    print("=======================================================")
    print("  🚄 Train Dispatching Optimizer - CP-SAT Engine")
    print("=======================================================")
    print("Please select an execution mode:")
    print("  [1]  Batch Testing   – run all standard test instances")
    print("  [2]  Single Dataset  – pick a file via GUI dialog")
    print("=======================================================")

    try:
        choice = input("Enter your choice (1 or 2): ").strip()
    except KeyboardInterrupt:
        print("\nExiting.")
        return

    if choice == '1':
        # Batch mode always uses standard CP-SAT (small benchmark instances)
        test_dir = os.path.join(script_dir, "..", "dataset",
                                "displib_instances_testing", "displib_instances_testing")
        test_files = glob.glob(os.path.join(test_dir, "*.json"))

        if not test_files:
            print(f"No test instances found in {test_dir}")
            return

        print(f"\nFound {len(test_files)} test instances. "
              "Starting OR-Tools CP-SAT batch tests...\n")
        for test_file in sorted(test_files):
            run_single_test(test_file, script_dir, is_batch=True, mode=MODE_STANDARD)

    elif choice == '2':
        root = tk.Tk()
        root.withdraw()
        root.attributes('-topmost', True)

        print("\nPlease select a dataset JSON file in the pop-up dialog window...")
        initial_dir = os.path.abspath(
            os.path.join(script_dir, "..", "dataset", "displib_problems"))
        if not os.path.exists(initial_dir):
            initial_dir = os.path.abspath(os.path.join(script_dir, "..", "dataset"))

        file_path = filedialog.askopenfilename(
            title="Select a DISPLIB Problem JSON",
            initialdir=initial_dir,
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
        )

        if not file_path:
            print("No file selected. Exiting.")
            return

        print(f"\nSelected: {file_path}")

        mode = pick_solver_mode()
        run_single_test(file_path, script_dir, is_batch=False, mode=mode)

    else:
        print("Invalid choice. Exiting.")


if __name__ == "__main__":
    main()
