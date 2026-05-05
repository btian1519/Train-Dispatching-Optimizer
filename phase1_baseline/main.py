import os
import sys
import time
import glob
import tkinter as tk
from tkinter import filedialog
from src.data_parser import DisplibInstance
from src.mip_model import DisplibMipModel
from src.mip_model_new import DisplibMipModel as DisplibMipModelNew
from gurobipy import GRB

sys.stdout.reconfigure(encoding='utf-8')

def run_single_test(test_file, script_dir, is_batch=False, use_colleague_model=False):
    filename = os.path.basename(test_file)
    test_name = filename.replace('.json', '')
    print(f"{'='*60}")
    model_name = "Colleague's MIP Model" if use_colleague_model else "MIP Model"
    print(f"Testing Instance [{model_name}]: {test_name}")
    print(f"{'='*60}")
    
    try:
        # Load testing instance
        instance = DisplibInstance.from_json(test_file)
        print(f"-> Loaded {len(instance.trains)} trains and {len(instance.find_conflict_pairs())} conflict pairs.")
        
        # Initialize Gurobi Engine
        start_time = time.time()
        if use_colleague_model:
            mip_model = DisplibMipModelNew(instance, M=1000000)
        else:
            mip_model = DisplibMipModel(instance, M=1000000)
        
        if is_batch:
            mip_model.model.setParam('OutputFlag', 0)
            time_limit = 60
        else:
            mip_model.model.setParam('OutputFlag', 1)
            time_limit = 180
            
        print(f"-> Model constructed in {time.time() - start_time:.2f} s. Optimizing (Max {time_limit}s)...")
        
        # Run optimization
        opt_start = time.time()
        mip_model.optimize(time_limit=time_limit)
        opt_time = time.time() - opt_start
        
        # Output Results
        status = mip_model.model.status
        if status == GRB.OPTIMAL:
            print(f"-> Status: OPTIMAL (Time: {opt_time:.2f}s, ObjVal: {mip_model.model.ObjVal})")
        elif status == GRB.INFEASIBLE:
            print(f"-> Status: INFEASIBLE (Time: {opt_time:.2f}s) - Model has no solution.")
        elif status == GRB.TIME_LIMIT:
            print(f"-> Status: TIME LIMIT (Time: {opt_time:.2f}s)")
            if mip_model.model.SolCount > 0:
                print(f"-> Found feasible sub-optimal solution. Best ObjVal: {mip_model.model.ObjVal}")
            else:
                print("-> No feasible solution found before timeout.")
        else:
            print(f"-> Status: OTHER (Code {status}, Time: {opt_time:.2f}s)")
        
        # Export solution
        if status in (GRB.OPTIMAL, GRB.TIME_LIMIT, GRB.SUBOPTIMAL) and mip_model.model.SolCount > 0:
            out_dir = os.path.join(script_dir, "output")
            os.makedirs(out_dir, exist_ok=True)
            suffix = "_colleague" if use_colleague_model else ""
            out_file = os.path.join(out_dir, f"solution_{test_name}{suffix}.json")
            mip_model.export_solution(out_file)
            print(f"-> Solution successfully exported to {out_file}")
        else:
            print(f"-> Skipped export: No feasible solution to export.")
            
    except Exception as e:
        print(f"!!! Error processing {test_name}: {e}")
        
    print("\n")

def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    
    print("=======================================================")
    print("  🧮 Train Dispatching Optimizer - Gurobi MIP Engine")
    print("=======================================================")
    print("Please select an execution mode:")
    print("  [1] Run Batch Testing (Quick check on basic test instances)")
    print("  [2] Select a specific dataset to solve (GUI Dialog)")
    print("  [3] Run Colleague's Model (mip_model_new.py) (GUI Dialog)")
    print("=======================================================")
    
    try:
        choice = input("Enter your choice (1, 2, or 3): ").strip()
    except KeyboardInterrupt:
        print("\nExiting.")
        return
        
    if choice == '1':
        test_dir = os.path.join(script_dir, "..", "dataset", "displib_instances_testing", "displib_instances_testing")
        test_files = glob.glob(os.path.join(test_dir, "*.json"))
        
        if not test_files:
            print(f"No test instances found in {test_dir}")
            return

        print(f"\nFound {len(test_files)} test instances. Starting Gurobi MIP batch tests...\n")
        for test_file in test_files:
            run_single_test(test_file, script_dir, is_batch=True)
            
    elif choice in ('2', '3'):
        use_colleague = (choice == '3')
        
        # Open a beautiful file dialog
        root = tk.Tk()
        root.withdraw() # Hide the main window
        root.attributes('-topmost', True) # Force window to foreground
        
        print("\nPlease select a dataset JSON file in the pop-up dialog window...")
        
        initial_dir = os.path.abspath(os.path.join(script_dir, "..", "dataset", "displib_problems"))
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
            
        run_single_test(file_path, script_dir, is_batch=False, use_colleague_model=use_colleague)
    else:
        print("Invalid choice. Exiting.")

if __name__ == "__main__":
    main()
