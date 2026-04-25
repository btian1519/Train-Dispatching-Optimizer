import os
import time
import glob
from src.data_parser import DisplibInstance
from src.cp_model import DisplibCPModel

def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    test_dir = os.path.join(script_dir, "..", "dataset", "displib_instances_testing", "displib_instances_testing")
    test_files = glob.glob(os.path.join(test_dir, "*.json"))
    
    if not test_files:
        print(f"No test instances found in {test_dir}")
        return

    print(f"Found {len(test_files)} test instances. Starting OR-Tools CP-SAT batch tests...\n")
    
    for test_file in test_files:
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
            
            # Reduce solver output noise
            cp_model.solver.parameters.log_search_progress = False
            
            print(f"-> CP Model constructed in {time.time() - start_time:.2f} s. Optimizing...")
            
            # Run optimization
            opt_start = time.time()
            status = cp_model.optimize(time_limit=60)
            opt_time = time.time() - opt_start
            
            # Output Results
            if status in ["OPTIMAL", "FEASIBLE"]:
                print(f"-> Status: {status} (Time: {opt_time:.2f}s, ObjVal: {cp_model.obj_val})")
                out_dir = os.path.join(script_dir, "output")
                os.makedirs(out_dir, exist_ok=True)
                out_file = os.path.join(out_dir, f"solution_{test_name}.json")
                cp_model.export_solution(out_file)
                print(f"Solution successfully exported to output/solution_{test_name}.json")
            elif status == "INFEASIBLE":
                print(f"-> Status: INFEASIBLE (Time: {opt_time:.2f}s) - Model has no solution.")
                print(f"-> Skipped export: No feasible solution found.")
            else:
                print(f"-> Status: {status} (Time: {opt_time:.2f}s)")
                
        except Exception as e:
            print(f"!!! Error processing {test_name}: {e}")
            
        print("\n")

if __name__ == "__main__":
    main()
