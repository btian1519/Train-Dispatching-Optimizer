import json
import sys
import os

def visualize(problem_file, solution_file):
    # Read problem and solution data
    with open(problem_file, 'r', encoding='utf-8') as f:
        prob = json.load(f)
    with open(solution_file, 'r', encoding='utf-8') as f:
        sol = json.load(f)
        
    events = sol['events']
    
    # Group and sort events by train
    train_events = {}
    for e in events:
        t = e['train']
        if t not in train_events:
            train_events[t] = []
        train_events[t].append(e)
        
    for t in train_events:
        train_events[t].sort(key=lambda x: x['operation'])
        
    print(f"\n========================================================")
    print(f" 🚆 Train Resource Allocation Schedule (Objective Value: {sol.get('objective_value', 'N/A')})")
    print(f"========================================================")
    
    for t_idx, t_ops in enumerate(prob['trains']):
        print(f"\n▶ Train {t_idx} Schedule:")
        t_evs = train_events.get(t_idx, [])
        for i in range(len(t_evs)):
            op_idx = t_evs[i]['operation']
            start_t = t_evs[i]['time']
            
            # Calculate end time
            if i + 1 < len(t_evs):
                end_t = t_evs[i+1]['time']
            else:
                dur = t_ops[op_idx].get('min_duration', 0)
                end_t = start_t + dur
                
            res_list = t_ops[op_idx].get('resources', [])
            res_names = [r['resource'] for r in res_list]
            
            if not res_names:
                res_str = "[No resource / Waiting]"
            else:
                res_str = f"Occupying track {', '.join(res_names)}"
                
            # Filter out virtual nodes with no duration and no resources
            if end_t == start_t and not res_names:
                continue 
                
            print(f"   ⏰ [{start_t:02d}s -> {end_t:02d}s] : {res_str}")
            
    # ==== Conflict Analysis ====
    resource_reqs = {}
    actual_times = {} # t_idx -> op_idx -> (start_t, end_t)
    
    for t_idx, t_ops in enumerate(prob['trains']):
        actual_times[t_idx] = {}
        t_evs = train_events.get(t_idx, [])
        for i in range(len(t_evs)):
            op_idx = t_evs[i]['operation']
            start_t = t_evs[i]['time']
            if i + 1 < len(t_evs):
                end_t = t_evs[i+1]['time']
            else:
                end_t = start_t + t_ops[op_idx].get('min_duration', 0)
            actual_times[t_idx][op_idx] = (start_t, end_t)
            
            for r in t_ops[op_idx].get('resources', []):
                res_name = r['resource']
                if res_name not in resource_reqs:
                    resource_reqs[res_name] = []
                resource_reqs[res_name].append({'train': t_idx, 'op': op_idx})
                
    print(f"\n========================================================")
    print(f" ⚔️ Conflict Analysis & Resolution Log")
    print(f"========================================================")
    
    conflict_count = 1
    for res_name, reqs in resource_reqs.items():
        if len(reqs) > 1: # Contention exists
            for i in range(len(reqs)):
                for j in range(i + 1, len(reqs)):
                    t1, op1 = reqs[i]['train'], reqs[i]['op']
                    t2, op2 = reqs[j]['train'], reqs[j]['op']
                    if t1 == t2: continue 
                    
                    st1, et1 = actual_times[t1].get(op1, (0,0))
                    st2, et2 = actual_times[t2].get(op2, (0,0))
                    
                    print(f"\n🚨 Conflict {conflict_count}: Contention for track [{res_name}] (Train {t1} vs Train {t2})")
                    
                    if st1 <= st2:
                        first, second = t1, t2
                        f_st, f_et = st1, et1
                        s_st, s_et = st2, et2
                    else:
                        first, second = t2, t1
                        f_st, f_et = st2, et2
                        s_st, s_et = st1, et1
                        
                    print(f"   -> Resolution: Train {first} proceeds first ({f_st:02d}s - {f_et:02d}s)")
                    print(f"                  Train {second} yields and proceeds later ({s_st:02d}s - {s_et:02d}s)")
                    
                    conflict_count += 1
                    
    if conflict_count == 1:
        print("\n🎉 Excellent! No resource conflicts detected in this instance.")

    print("\n")
    # CSV Generation completely removed as requested.

if __name__ == "__main__":
    if len(sys.argv) == 3:
        visualize(sys.argv[1], sys.argv[2])
    else:
        try:
            import tkinter as tk
            from tkinter import filedialog
            
            root = tk.Tk()
            root.withdraw() 
            root.attributes('-topmost', True) 
            
            print("Please select the [Problem JSON] file in the popup dialog...")
            problem_file = filedialog.askopenfilename(
                title="1. Select Problem JSON (e.g. displib_testinstances_swapping2.json)",
                filetypes=[("JSON Files", "*.json")]
            )
            
            if not problem_file:
                print("No problem file selected. Exiting.")
                sys.exit(0)
                
            print("Please select the [Solution JSON] file in the popup dialog...")
            solution_file = filedialog.askopenfilename(
                title="2. Select Solution JSON (e.g. solution_displib_testinstances_swapping2.json)",
                filetypes=[("JSON Files", "*.json")]
            )
            
            if not solution_file:
                print("No solution file selected. Exiting.")
                sys.exit(0)
                
            visualize(problem_file, solution_file)
            
        except Exception as e:
            print("Usage: python visualize_schedule.py <problem.json> <solution.json>")
            print(f"Dialog Error: {e}")
