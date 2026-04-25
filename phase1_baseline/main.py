import os
import time
import glob
from src.data_parser import DisplibInstance
from src.mip_model import DisplibMipModel
from gurobipy import GRB

def main():
    # Adjusted path to be completely independent of terminal CWD
    script_dir = os.path.dirname(os.path.abspath(__file__))
    test_dir = os.path.join(script_dir, "..", "dataset", "displib_instances_testing", "displib_instances_testing")
    test_files = glob.glob(os.path.join(test_dir, "*.json"))
    
    if not test_files:
        print(f"No test instances found in {test_dir}")
        return

    print(f"Found {len(test_files)} test instances. Starting batch tests...\n")
    
    for test_file in test_files:
        filename = os.path.basename(test_file)
        test_name = filename.replace('.json', '')
        print(f"{'='*60}")
        print(f"Testing Instance: {test_name}")
        print(f"{'='*60}")
        
        try:
            # Load testing instance
            instance = DisplibInstance.from_json(test_file)
            print(f"-> Loaded {len(instance.trains)} trains and {len(instance.find_conflict_pairs())} conflict pairs.")
            
            # Initialize Gurobi Engine
            start_time = time.time()
            mip_model = DisplibMipModel(instance, M=1000000)
            
            # Reduce Gurobi output noise
            mip_model.model.setParam('OutputFlag', 0)
            
            print(f"-> Model constructed in {time.time() - start_time:.2f} s. Optimizing...")
            
            # Run optimization
            opt_start = time.time()
            mip_model.optimize(time_limit=60)
            opt_time = time.time() - opt_start
            
            # Output Results
            status = mip_model.model.status
            if status == GRB.OPTIMAL:
                print(f"-> Status: OPTIMAL (Time: {opt_time:.2f}s, ObjVal: {mip_model.model.ObjVal})")
            elif status == GRB.INFEASIBLE:
                print(f"-> Status: INFEASIBLE (Time: {opt_time:.2f}s) - Model has no solution.")
            elif status == GRB.TIME_LIMIT:
                print(f"-> Status: TIME LIMIT (Time: {opt_time:.2f}s) - Best ObjVal: {mip_model.model.ObjVal}")
            else:
                print(f"-> Status: OTHER (Code {status}, Time: {opt_time:.2f}s)")
            
            # Export solution
            if status in (GRB.OPTIMAL, GRB.TIME_LIMIT, GRB.SUBOPTIMAL):
                out_dir = os.path.join(script_dir, "output")
                os.makedirs(out_dir, exist_ok=True)
                out_file = os.path.join(out_dir, f"solution_{test_name}.json")
                mip_model.export_solution(out_file)
            else:
                print(f"-> Skipped export: No feasible solution found.")
                
        except Exception as e:
            print(f"!!! Error processing {test_name}: {e}")
            
        print("\n")

if __name__ == "__main__":
    main()
