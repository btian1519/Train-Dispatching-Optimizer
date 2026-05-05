import os
import sys
import time
import glob
import tkinter as tk
from tkinter import filedialog
from src.data_parser import DisplibInstance
from src.cp_model import DisplibCPModel

sys.stdout.reconfigure(encoding='utf-8')

def run_single_test(test_file, script_dir, is_batch=False):
    filename = os.path.basename(test_file)
    test_name = filename.replace('.json', '')
    print(f"{'='*60}")
    print(f"Testing Instance [CP Model]: {test_name}")
    print(f"{'='*60}")
    
    try:
        # Load testing instance
        instance = DisplibInstance.from_json(test_file)
        print(f"-> Loaded {len(instance.trains)} trains and their interval requirements.")
        
        # Initialize CP Model
        start_time = time.time()
        cp_model = DisplibCPModel(instance)
        
        # In batch mode we keep logs quiet, in single mode we show progress
        if is_batch:
            cp_model.solver.parameters.log_search_progress = False
            time_limit = 60
        else:
            cp_model.solver.parameters.log_search_progress = True
            time_limit = 10
            
        print(f"-> CP Model constructed in {time.time() - start_time:.2f} s. Optimizing (Max {time_limit}s)...")
        
        # Run optimization
        opt_start = time.time()
        status = cp_model.optimize(time_limit=time_limit)
        opt_time = time.time() - opt_start
        
        # Output Results
        if status in ["OPTIMAL", "FEASIBLE"]:
            print(f"-> Status: {status} (Time: {opt_time:.2f}s, ObjVal: {cp_model.obj_val})")
            out_dir = os.path.join(script_dir, "output")
            os.makedirs(out_dir, exist_ok=True)
            out_file = os.path.join(out_dir, f"solution_{test_name}.json")
            cp_model.export_solution(out_file)
            print(f"Solution successfully exported to {out_file}")
        elif status == "INFEASIBLE":
            print(f"-> Status: INFEASIBLE (Time: {opt_time:.2f}s) - Model has no solution.")
            print(f"-> Skipped export: No feasible solution found.")
        else:
            print(f"-> Status: {status} (Time: {opt_time:.2f}s)")
            
    except Exception as e:
        print(f"!!! Error processing {test_name}: {e}")
        
    print("\n")

def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    
    print("=======================================================")
    print("  🚄 Train Dispatching Optimizer - CP-SAT Engine")
    print("=======================================================")
    print("Please select an execution mode:")
    print("  [1] Run Batch Testing (Quick check on basic test instances)")
    print("  [2] Select a specific dataset to solve (GUI Dialog)")
    print("=======================================================")
    
    try:
        choice = input("Enter your choice (1 or 2): ").strip()
    except KeyboardInterrupt:
        print("\nExiting.")
        return
        
    if choice == '1':
        test_dir = os.path.join(script_dir, "..", "dataset", "displib_instances_testing", "displib_instances_testing")
        test_files = glob.glob(os.path.join(test_dir, "*.json"))
        
        if not test_files:
            print(f"No test instances found in {test_dir}")
            return

        print(f"\nFound {len(test_files)} test instances. Starting OR-Tools CP-SAT batch tests...\n")
        for test_file in test_files:
            run_single_test(test_file, script_dir, is_batch=True)
            
    elif choice == '2':
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
            
        print(f"Selected: {file_path}\n")
        run_single_test(file_path, script_dir, is_batch=False)
        
    else:
        print("Invalid choice. Exiting.")

if __name__ == "__main__":
    main()
