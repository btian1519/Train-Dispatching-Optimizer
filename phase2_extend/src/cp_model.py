import time
import json
import math
import warnings
from ortools.sat.python import cp_model
from src.data_parser import DisplibInstance

class DisplibCPModel:
    def __init__(self, instance: DisplibInstance, horizon=86400*7): # Default 7 days max scheduling horizon
        self.instance = instance
        self.model = cp_model.CpModel()
        self.solver = cp_model.CpSolver()
        self.horizon = int(horizon)
        
        # Core CP Variables
        self.x = {}  # x[train_id, op_id]: Boolean, 1 if operation is selected
        self.y = {}  # y[train_id, op_a, op_b]: Boolean, 1 if sequence A -> B is taken
        self.u = {}  # u[train_id, op_id]: Integer, topological sequence rank
        
        self.starts = {}   # starts[train_id, op_id]: Integer, start time
        self.durations = {} # durations[train_id, op_id]: Integer, duration
        self.ends = {}     # ends[train_id, op_id]: Integer, end time
        
        self.status = None
        self.obj_val = float('inf')
        
        # Use a scaling factor since CP-SAT only supports integers, but cost coefficients might be floats
        self.COEFF_SCALE = 1000 
        
        self._build_model()
        
    def _build_model(self):
        resource_intervals = {} # {resource_name: [list of extended IntervalVars]}
        
        obj_costs = [] # List of integer cost variables
        
        # -----------------------------------------------------
        # 1. Variables & Interval Construction
        # -----------------------------------------------------
        for train in self.instance.trains:
            for op in train.operations:
                t_id = train.id
                o_id = op.id
                
                # Active boolean var
                self.x[t_id, o_id] = self.model.NewBoolVar(f"x_{t_id}_{o_id}")
                self.u[t_id, o_id] = self.model.NewIntVar(0, sum(len(tr.operations) for tr in self.instance.trains), f"u_{t_id}_{o_id}")
                
                # Time bounds mapping
                lb = max(0, int(op.start_lb))
                ub_val = op.start_ub
                ub = self.horizon if (ub_val is None or ub_val == float('inf')) else min(self.horizon, int(ub_val))
                if ub < lb: ub = lb # Safety fallback
                
                self.starts[t_id, o_id] = self.model.NewIntVar(lb, ub, f"st_{t_id}_{o_id}")
                self.durations[t_id, o_id] = self.model.NewIntVar(int(op.min_duration), self.horizon, f"dur_{t_id}_{o_id}")
                self.ends[t_id, o_id] = self.model.NewIntVar(lb + int(op.min_duration), self.horizon + self.horizon, f"end_{t_id}_{o_id}")
                
                # The heart of CP: Optional Interval Variable
                iv = self.model.NewOptionalIntervalVar(
                    self.starts[t_id, o_id], 
                    self.durations[t_id, o_id], 
                    self.ends[t_id, o_id], 
                    self.x[t_id, o_id], 
                    f"iv_{t_id}_{o_id}"
                )
                
                # Process resources for AddNoOverlap
                for r_data in op.resources:
                    res_name = r_data.resource
                    rel_time = int(r_data.release_time)
                    
                    if res_name not in resource_intervals:
                        resource_intervals[res_name] = []
                        
                    # If there's a headway (release_time), we must artificially extend the block's end.
                    if rel_time > 0:
                        ext_dur = self.model.NewIntVar(int(op.min_duration) + rel_time, self.horizon + rel_time, f"ext_dur_{t_id}_{o_id}_{res_name}")
                        self.model.Add(ext_dur == self.durations[t_id, o_id] + rel_time)
                        
                        ext_end = self.model.NewIntVar(lb + int(op.min_duration) + rel_time, self.horizon * 2 + rel_time, f"ext_end_{t_id}_{o_id}_{res_name}")
                        self.model.Add(ext_end == self.ends[t_id, o_id] + rel_time)
                        
                        ext_iv = self.model.NewOptionalIntervalVar(
                            self.starts[t_id, o_id], ext_dur, ext_end, self.x[t_id, o_id], f"ext_iv_{t_id}_{o_id}_{res_name}"
                        )
                        resource_intervals[res_name].append(ext_iv)
                    else:
                        resource_intervals[res_name].append(iv)
                
                # Sequence tracking variables y
                for succ in op.successors:
                    self.y[t_id, o_id, succ] = self.model.NewBoolVar(f"y_{t_id}_{o_id}_{succ}")
                    


        # -----------------------------------------------------
        # 2. Resource Exclusivity (The elegant AddNoOverlap)
        # -----------------------------------------------------
        # This absolutely annihilates the logic of Big-M!
        for res_name, intervals in resource_intervals.items():
            self.model.AddNoOverlap(intervals)

        # -----------------------------------------------------
        # 2b. Topological Swapping / Deadlock Prevention
        # -----------------------------------------------------
        conflicts = self.instance.find_conflict_pairs()
        for c in conflicts:
            t1, o1, t2, o2, res, l1, l2 = c
            
            # Need strict boolean vars mimicking z_ab to crush teleportation cycles
            z_ab = self.model.NewBoolVar(f"z_{t1}_{o1}_{t2}_{o2}_{res}")
            z_ba = self.model.NewBoolVar(f"z_{t2}_{o2}_{t1}_{o1}_{res}")
            
            x_a = self.x[t1, o1]
            x_b = self.x[t2, o2]
            
            self.model.Add(z_ab + z_ba == 1).OnlyEnforceIf([x_a, x_b])
            self.model.Add(z_ab == 0).OnlyEnforceIf(x_a.Not())
            self.model.Add(z_ab == 0).OnlyEnforceIf(x_b.Not())
            self.model.Add(z_ba == 0).OnlyEnforceIf(x_a.Not())
            self.model.Add(z_ba == 0).OnlyEnforceIf(x_b.Not())
            
            op_a = self.instance.trains[t1].get_operation(o1)
            op_b = self.instance.trains[t2].get_operation(o2)
            
            for succ_a in op_a.successors:
                # If Train 1 goes before Train 2 (z_ab==1), Train 1 must reach succ_a before Train 2 starts o2.
                self.model.Add(self.starts[t2, o2] >= self.starts[t1, succ_a] + l1).OnlyEnforceIf([z_ab, self.y[t1, o1, succ_a]])
                self.model.Add(self.u[t2, o2] >= self.u[t1, succ_a] + 1).OnlyEnforceIf([z_ab, self.y[t1, o1, succ_a]])
            
            for succ_b in op_b.successors:
                self.model.Add(self.starts[t1, o1] >= self.starts[t2, succ_b] + l2).OnlyEnforceIf([z_ba, self.y[t2, o2, succ_b]])
                self.model.Add(self.u[t1, o1] >= self.u[t2, succ_b] + 1).OnlyEnforceIf([z_ba, self.y[t2, o2, succ_b]])

        # -----------------------------------------------------
        # 3. Flow Constraints (Entering & Leaving)
        # -----------------------------------------------------
        predecessors = {train.id: {op.id: [] for op in train.operations} for train in self.instance.trains}
        for train in self.instance.trains:
            for op in train.operations:
                for succ in op.successors:
                    predecessors[train.id][succ].append(op.id)

        for train in self.instance.trains:
            t_id = train.id
            
            starts_idx = [op.id for op in train.operations if len(predecessors[t_id][op.id]) == 0]
            ends_idx = [op.id for op in train.operations if len(op.successors) == 0]
            
            # Start Ops must be active (usually only 1 start)
            for o_idx in starts_idx:
                self.model.Add(self.x[t_id, o_idx] == 1)
                
            # End Ops must be active (usually only 1 end)
            for o_idx in ends_idx:
                self.model.Add(self.x[t_id, o_idx] == 1)
            
            for op in train.operations:
                o_id = op.id
                
                # Flow OUT: sum_out == x
                if o_id not in ends_idx:
                    self.model.Add(sum(self.y[t_id, o_id, succ] for succ in op.successors) == self.x[t_id, o_id])
                
                # Flow IN: sum_in == x
                if o_id not in starts_idx:
                    preds = predecessors[t_id][o_id]
                    self.model.Add(sum(self.y[t_id, p, o_id] for p in preds) == self.x[t_id, o_id])
                
                # Precedences Time Logic
                for succ in op.successors:
                    # IF y[op->succ] is true => start(succ) == end(op)
                    # This is critical: the train occupies the resource until it physically starts the next operation!
                    self.model.Add(self.starts[t_id, succ] == self.ends[t_id, o_id]).OnlyEnforceIf(self.y[t_id, o_id, succ])
                    
                    # Strict topological rank progression
                    self.model.Add(self.u[t_id, succ] >= self.u[t_id, o_id] + 1).OnlyEnforceIf(self.y[t_id, o_id, succ])

        # -----------------------------------------------------
        # 4. Objective Costs Calculation (Penalty)
        # -----------------------------------------------------
        for c_idx, comp in enumerate(self.instance.objective):
            if comp.train == -1 or comp.operation == -1: 
                continue
            
            t_id = comp.train
            o_id = comp.operation
            th = int(comp.threshold)
            cf = comp.coeff
            scaled_cf = int(cf * self.COEFF_SCALE)
            
            x_a = self.x.get((t_id, o_id))
            if x_a is None: 
                continue
            
            over_time = self.model.NewIntVar(0, self.horizon * 2, f"ov_{c_idx}")
            self.model.Add(over_time >= self.starts[t_id, o_id] - th).OnlyEnforceIf(x_a)
            
            cost_var = self.model.NewIntVar(0, int(self.horizon * 2 * max(1, scaled_cf)), f"cost_{c_idx}")
            self.model.Add(cost_var == over_time * scaled_cf).OnlyEnforceIf(x_a)
            self.model.Add(cost_var == 0).OnlyEnforceIf(x_a.Not())
            
            obj_costs.append(cost_var)

        # -----------------------------------------------------
        # 5. Set Objective
        # -----------------------------------------------------
        if len(obj_costs) > 0:
            self.model.Minimize(sum(obj_costs))

    def optimize(self, time_limit=180, num_workers=16):
        self.solver.parameters.max_time_in_seconds = float(time_limit)
        # CP-SAT utilizes multi-threading natively!
        self.solver.parameters.num_search_workers = num_workers
        self.solver.parameters.log_search_progress = True
        
        status_num = self.solver.Solve(self.model)
        
        if status_num == cp_model.OPTIMAL or status_num == cp_model.FEASIBLE:
            self.status = "OPTIMAL" if status_num == cp_model.OPTIMAL else "FEASIBLE"
            # Reverse the scale to get float value back
            self.obj_val = self.solver.ObjectiveValue() / self.COEFF_SCALE
        elif status_num == cp_model.INFEASIBLE:
            self.status = "INFEASIBLE"
        else:
            self.status = "UNKNOWN"
            
        return self.status

    def export_solution(self, filename: str):
        if self.status not in ["OPTIMAL", "FEASIBLE"]:
            print("Cannot export: No feasible solution available.")
            return

        events = []
        for train in self.instance.trains:
            t_id = train.id
            for op in train.operations:
                o_id = op.id
                if self.solver.BooleanValue(self.x[t_id, o_id]):
                    st = self.solver.Value(self.starts[t_id, o_id])
                    events.append({
                        "operation": o_id,
                        "time": int(st),
                        "train": t_id
                    })

        # ---------------------------------------------------------
        # ROBUST TOPOLOGICAL SORT FOR VERIFIER
        # ---------------------------------------------------------
        # We can directly use the topological rank `u` calculated by the CP-SAT solver!
        # This completely guarantees no cyclic dependencies and matches the physical causality.
        events.sort(key=lambda x: (x["time"], self.solver.Value(self.u[x["train"], x["operation"]])))
        
        final_events = events
                
        events = final_events
        # ---------------------------------------------------------
        
        output = {
            "events": events,
            "objective_value": int(round(self.obj_val))
        }

        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(output, f, indent=4)
