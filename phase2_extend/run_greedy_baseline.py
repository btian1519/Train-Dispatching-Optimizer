import os
import sys
import json
import time

# Ensure we can import from the rest of the project
sys.path.append(os.path.abspath("phase1_baseline"))
sys.path.append(os.path.abspath("phase2_extend"))

from src.data_parser import DisplibInstance
from ortools.sat.python import cp_model


def solve_greedy(problem_file, output_file, horizon=86400*7, time_limit_per_train=5.0, global_time_limit=None):
    print("=" * 60)
    print(f"[*] STARTING GREEDY BASELINE (Train-by-Train)")
    print(f"    Problem: {problem_file}")
    print("=" * 60)
    
    instance = DisplibInstance.from_json(problem_file)
    
    # 1. Greedy Sorting Strategy
    # To simulate a simple rule-based greedy approach, we sort trains by ID.
    # Alternatively, you could sort by objective penalty coefficients to prioritize "expensive" trains.
    sorted_trains = sorted(instance.trains, key=lambda t: t.id)
    
    # Global state tracking
    global_resource_blocks = {} # res_name -> list of (start_time, end_time)
    
    final_events = []
    total_obj = 0
    failed_trains = []
    COEFF_SCALE = 1000
    
    start_time_all = time.time()
    
    for train in sorted_trains:
        elapsed = time.time() - start_time_all
        if global_time_limit is not None and elapsed >= global_time_limit:
            print(f"    [!] Global time limit reached after scheduling {len(final_events)} events.")
            if os.path.exists(output_file):
                os.remove(output_file)
            return {
                "status": "TIME_LIMIT",
                "objective_value": None,
                "failed_trains": failed_trains,
                "elapsed": elapsed,
            }

        t_id = train.id
        
        # Build a miniature CP-SAT model strictly for this SINGLE train
        model = cp_model.CpModel()
        
        x = {}
        y = {}
        u = {}
        starts = {}
        durations = {}
        ends = {}
        
        resource_ivs = {} # res_name -> list of IntervalVars
        
        # Inject previously locked resources as immutable blocks
        for res_name, blocks in global_resource_blocks.items():
            if res_name not in resource_ivs:
                resource_ivs[res_name] = []
            for i, (b_start, b_end) in enumerate(blocks):
                b_start = max(0, min(horizon, int(b_start)))
                # Enforce the train-by-train priority strictly. Without the
                # extra integer tick, two trains can swap resources at the
                # same timestamp and create a cyclic DISPLIB event order.
                b_end = max(b_start, min(horizon * 2, int(b_end) + 1))
                f_st = model.NewIntVar(b_start, b_start, f"fix_st_{res_name}_{i}")
                f_dur = model.NewIntVar(b_end - b_start, b_end - b_start, f"fix_dur_{res_name}_{i}")
                f_end = model.NewIntVar(b_end, b_end, f"fix_end_{res_name}_{i}")
                f_iv = model.NewIntervalVar(f_st, f_dur, f_end, f"fix_iv_{res_name}_{i}")
                resource_ivs[res_name].append(f_iv)
        
        # Build routing and temporal logic for this train
        for op in train.operations:
            o_id = op.id
            x[o_id] = model.NewBoolVar(f"x_{o_id}")
            u[o_id] = model.NewIntVar(0, len(train.operations), f"u_{o_id}")
            
            lb = max(0, int(op.start_lb))
            ub_val = op.start_ub
            ub = horizon if (ub_val is None or ub_val == float('inf')) else min(horizon, int(ub_val))
            if ub < lb: ub = lb
            
            starts[o_id] = model.NewIntVar(lb, ub, f"st_{o_id}")
            durations[o_id] = model.NewIntVar(int(op.min_duration), horizon, f"dur_{o_id}")
            ends[o_id] = model.NewIntVar(lb + int(op.min_duration), horizon * 2, f"end_{o_id}")
            
            iv = model.NewOptionalIntervalVar(starts[o_id], durations[o_id], ends[o_id], x[o_id], f"iv_{o_id}")
            
            for r_data in op.resources:
                res_name = r_data.resource
                rel_time = int(r_data.release_time)
                
                if res_name not in resource_ivs:
                    resource_ivs[res_name] = []
                
                if rel_time > 0:
                    ext_dur = model.NewIntVar(int(op.min_duration) + rel_time, horizon + rel_time, f"ext_dur_{o_id}_{res_name}")
                    model.Add(ext_dur == durations[o_id] + rel_time)
                    ext_end = model.NewIntVar(lb + int(op.min_duration) + rel_time, horizon * 2 + rel_time, f"ext_end_{o_id}_{res_name}")
                    model.Add(ext_end == ends[o_id] + rel_time)
                    ext_iv = model.NewOptionalIntervalVar(starts[o_id], ext_dur, ext_end, x[o_id], f"ext_iv_{o_id}_{res_name}")
                    resource_ivs[res_name].append(ext_iv)
                else:
                    resource_ivs[res_name].append(iv)
                    
            for succ in op.successors:
                y[o_id, succ] = model.NewBoolVar(f"y_{o_id}_{succ}")

        # Add Global AddNoOverlap
        for res_name, ivs in resource_ivs.items():
            model.AddNoOverlap(ivs)
            
        # Flow Constraints (Entering/Leaving)
        predecessors = {op.id: [] for op in train.operations}
        for op in train.operations:
            for succ in op.successors:
                predecessors[succ].append(op.id)
                
        starts_idx = [op.id for op in train.operations if len(predecessors[op.id]) == 0]
        ends_idx = [op.id for op in train.operations if len(op.successors) == 0]
        
        for o_idx in starts_idx:
            model.Add(x[o_idx] == 1)
        for o_idx in ends_idx:
            model.Add(x[o_idx] == 1)
            
        for op in train.operations:
            o_id = op.id
            if o_id not in ends_idx:
                model.Add(sum(y[o_id, succ] for succ in op.successors) == x[o_id])
            if o_id not in starts_idx:
                model.Add(sum(y[p, o_id] for p in predecessors[o_id]) == x[o_id])
                
            for succ in op.successors:
                model.Add(starts[succ] == ends[o_id]).OnlyEnforceIf(y[o_id, succ])
                model.Add(u[succ] >= u[o_id] + 1).OnlyEnforceIf(y[o_id, succ])
                
        # Objective Cost Calculation for this Train
        obj_costs = []
        for comp in instance.objective:
            if comp.train != t_id:
                continue
            o_id = comp.operation
            th = int(comp.threshold)
            cf = comp.coeff
            scaled_cf = int(cf * COEFF_SCALE)
            
            if o_id not in x:
                continue
                
            over_time = model.NewIntVar(0, horizon * 2, f"ov_{o_id}")
            model.Add(over_time >= starts[o_id] - th).OnlyEnforceIf(x[o_id])
            
            cost_var = model.NewIntVar(0, int(horizon * 2 * max(1, scaled_cf)), f"cost_{o_id}")
            model.Add(cost_var == over_time * scaled_cf).OnlyEnforceIf(x[o_id])
            model.Add(cost_var == 0).OnlyEnforceIf(x[o_id].Not())
            obj_costs.append(cost_var)
            
        if len(obj_costs) > 0:
            model.Minimize(sum(obj_costs))
            
        # Solve the single-train model
        solver = cp_model.CpSolver()
        solver.parameters.num_search_workers = 1 # Single thread is enough for 1 train
        solver.parameters.log_search_progress = False

        remaining_global = None
        if global_time_limit is not None:
            remaining_global = max(0.001, global_time_limit - (time.time() - start_time_all))

        local_time_limit = time_limit_per_train if remaining_global is None else min(time_limit_per_train, remaining_global)
        solver.parameters.max_time_in_seconds = max(0.001, float(local_time_limit))
        
        status = solver.Solve(model)
        
        if status == cp_model.OPTIMAL or status == cp_model.FEASIBLE:
            if len(obj_costs) > 0:
                total_obj += solver.ObjectiveValue() / COEFF_SCALE
                
            # Commit decisions to the global resource pool
            train_events = []
            for op in train.operations:
                o_id = op.id
                if solver.BooleanValue(x[o_id]):
                    st = solver.Value(starts[o_id])
                    en = solver.Value(ends[o_id])
                    u_val = solver.Value(u[o_id])
                    
                    train_events.append({
                        "operation": o_id,
                        "time": int(st),
                        "train": t_id,
                        "u": u_val
                    })
                    
                    for r_data in op.resources:
                        res_name = r_data.resource
                        rel_time = int(r_data.release_time)
                        if res_name not in global_resource_blocks:
                            global_resource_blocks[res_name] = []
                        global_resource_blocks[res_name].append((st, en + rel_time))
            
            train_events.sort(key=lambda item: (item["time"], item["u"]))
            for item in train_events:
                del item["u"] 
                final_events.append(item)
        else:
            print(f"    [!] Deadlock/Infeasible path for Train {t_id}")
            failed_trains.append(t_id)

    elapsed = time.time() - start_time_all
    print(f"\n[*] Greedy Baseline completed in {elapsed:.2f}s")
    print(f"    -> Total Objective Penalty: {total_obj}")

    if failed_trains:
        print(f"    -> FAILED: no complete solution for trains {failed_trains}")
        print("    -> No partial solution will be exported.\n")
        if os.path.exists(output_file):
            os.remove(output_file)
        return {
            "status": "FAILED",
            "objective_value": None,
            "failed_trains": failed_trains,
            "elapsed": elapsed,
        }

    # Output to JSON
    final_events.sort(key=lambda x: x["time"])
    output_data = {
        "events": final_events,
        "objective_value": int(round(total_obj))
    }
    
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, indent=4)
    print(f"[*] Solution exported to {output_file}\n")
    return {
        "status": "FEASIBLE",
        "objective_value": int(round(total_obj)),
        "failed_trains": [],
        "elapsed": elapsed,
        "output_file": output_file,
    }


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Run the Train-by-Train Greedy Baseline")
    parser.add_argument("--problem", type=str, default="dataset/displib_problems/smi_close_2.json")
    parser.add_argument("--output", type=str, default="dataset/displib_solutions/greedy_smi_close_2.json")
    parser.add_argument("--per-train-time", type=float, default=5.0)
    parser.add_argument("--global-time", type=float, default=None)
    args = parser.parse_args()
    
    solve_greedy(
        args.problem,
        args.output,
        time_limit_per_train=args.per_train_time,
        global_time_limit=args.global_time,
    )
