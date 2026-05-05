import json
import os
import gurobipy as gp
from gurobipy import GRB
from src.data_parser import DisplibInstance

class DisplibMipModel:
    def __init__(self, instance: DisplibInstance, M=1000000):
        self.instance = instance
        self.M = M
        self.model = gp.Model("TrainDispatching")
        
        # Variables
        self.x = {} # x[train.id, op.id]
        self.y = {} # y[train.id, op_a.id, op_b.id]
        self.t = {} # t[train.id, op.id]
        self.u = {} # u[train.id, op.id]
        self.z = {} # z[t1, o1, t2, o2]
        self.z_ba = {} # z_ba tracking
        self.v = {} # v[c_idx]
        self.w = {} # w[c_idx]

        self._build_model()

    def _build_model(self):
        # 1. Variables
        for train in self.instance.trains:
            for op in train.operations:
                # Variable x_i,a (1 if operation is selected)
                self.x[train.id, op.id] = self.model.addVar(vtype=GRB.BINARY, name=f"x_{train.id}_{op.id}")
                
                # Variable t_i,a (start time)
                ub = op.start_ub if op.start_ub is not None and op.start_ub < float('inf') else GRB.INFINITY
                self.t[train.id, op.id] = self.model.addVar(lb=op.start_lb, ub=ub, vtype=GRB.CONTINUOUS, name=f"t_{train.id}_{op.id}")
                
                # Variable u_i,a (ordering logic)
                self.u[train.id, op.id] = self.model.addVar(lb=0, vtype=GRB.CONTINUOUS, name=f"u_{train.id}_{op.id}")
                
                # Variable y_i,a,b (1 if operation b immediately follows a)
                for succ in op.successors:
                    self.y[train.id, op.id, succ] = self.model.addVar(vtype=GRB.BINARY, name=f"y_{train.id}_{op.id}_{succ}")

        # Resource Precedence z variables
        conflicts = self.instance.find_conflict_pairs()
        for c in conflicts:
            t1, o1, t2, o2, res, l1, l2 = c
            # z_ab (1 if t1_o1 precedes t2_o2)
            z_ab = self.model.addVar(vtype=GRB.BINARY, name=f"z_{t1}_{o1}_{t2}_{o2}_r_{res}")
            # z_ba (1 if t2_o2 precedes t1_o1)
            z_ba = self.model.addVar(vtype=GRB.BINARY, name=f"z_{t2}_{o2}_{t1}_{o1}_r_{res}")
            
            self.z[t1, o1, t2, o2, res] = z_ab
            self.z_ba[t1, o1, t2, o2, res] = z_ba

        # Objective variables
        for c_idx, comp in enumerate(self.instance.objective):
            self.v[c_idx] = self.model.addVar(vtype=GRB.BINARY, name=f"v_{c_idx}")
            self.w[c_idx] = self.model.addVar(lb=0, vtype=GRB.CONTINUOUS, name=f"w_{c_idx}")

        self.model.update()

        # Precompute predecessors
        predecessors = {train.id: {op.id: [] for op in train.operations} for train in self.instance.trains}
        for train in self.instance.trains:
            for op in train.operations:
                for succ in op.successors:
                    predecessors[train.id][succ].append(op.id)

        # 2. Constraints
        # A) Flow constraints
        for train in self.instance.trains:
            entries = [op.id for op in train.operations if len(predecessors[train.id][op.id]) == 0]
            exits = [op.id for op in train.operations if len(op.successors) == 0]
            
            # Flow leaving entry
            for entry in entries:
                op = train.get_operation(entry)
                self.model.addConstr(gp.quicksum(self.y[train.id, entry, succ] for succ in op.successors) == 1)
                self.model.addConstr(self.x[train.id, entry] == 1)
                
            # Flow entering exit
            for exit in exits:
                self.model.addConstr(gp.quicksum(self.y[train.id, pred, exit] for pred in predecessors[train.id][exit]) == 1)
                self.model.addConstr(self.x[train.id, exit] == 1)
            
            # Flow conservation for intermediate
            for op in train.operations:
                if op.id not in entries and op.id not in exits:
                    sum_in = gp.quicksum(self.y[train.id, pred, op.id] for pred in predecessors[train.id][op.id])
                    sum_out = gp.quicksum(self.y[train.id, op.id, succ] for succ in op.successors)
                    self.model.addConstr(sum_in == sum_out)
                    self.model.addConstr(sum_in == self.x[train.id, op.id])

            # Logical y relates to x
            for op in train.operations:
                for succ in op.successors:
                    self.model.addConstr(self.y[train.id, op.id, succ] <= self.x[train.id, op.id])
                    self.model.addConstr(self.y[train.id, op.id, succ] <= self.x[train.id, succ])
                    self.model.addConstr(self.x[train.id, op.id] + self.x[train.id, succ] - 1 <= self.y[train.id, op.id, succ])
                    
                    # Duration minimum
                    self.model.addConstr(self.t[train.id, succ] - self.t[train.id, op.id] >= op.min_duration * self.y[train.id, op.id, succ])

        # Big-M values
        M_t = self.M
        # B) Resource Exclusivity via Indicator Constraints
        for c in conflicts:
            # Unpack the conflict tuple (c):
            # t1, t2: Train IDs (e.g., 0 and 1)
            # o1, o2: The specific operation IDs causing the clash (e.g., 3rd step and 5th step)
            # res:    The shared resource they are fighting for (e.g., "r5")
            # l1, l2: The 'release_time' (Headway) safety gap required after o1 or o2 leaves the resource
            t1, o1, t2, o2, res, l1, l2 = c
            
            # z_ab = 1 means Train 1 (t1) strictly goes before Train 2 (t2)
            # z_ba = 1 means Train 2 (t2) strictly goes before Train 1 (t1)
            z_ab = self.z[t1, o1, t2, o2, res]
            z_ba = self.z_ba[t1, o1, t2, o2, res]
            
            # x_a = 1 means Train 1's operation (o1) is actually selected/executed in the route
            # x_b = 1 means Train 2's operation (o2) is actually selected/executed in the route
            x_a = self.x[t1, o1]
            x_b = self.x[t2, o2]
            
            self.model.addConstr(x_a >= z_ab + z_ba)
            self.model.addConstr(x_b >= z_ab + z_ba)
            self.model.addConstr(x_a + x_b - 1 <= z_ab + z_ba)
            
            op_a = self.instance.trains[t1].get_operation(o1)
            op_b = self.instance.trains[t2].get_operation(o2)
            
            for succ_a in op_a.successors:
                # 1. Physical time-blocking: If Train 1 goes before Train 2 (z_ab==1), Train 1 must fully 
                # reach its next step (succ_a) before Train 2's timeline is allowed to start.
                self.model.addConstr((z_ab == 1) >> (self.t[t1, succ_a] - self.t[t2, o2] <= -l1))
                
                # 2. Cycle-crushing sequence: If Train 1 goes before Train 2, the topological rank (u-value)
                # assigned to Train 1's next step must be strictly smaller than Train 2's start. This breaks cyclic swapping.
                # --> Corresponds to DISPLIB Paper Eq (3) lower part: u_{a_bar}^i - u_b^j <= -1 + M(1 - z_{a,b}^{i,j})
                #     (u_{a_bar}^i <==> self.u[t1, succ_a],  u_b^j <==> self.u[t2, o2], z_{a,b}^{i,j} <==> z_ab)
                self.model.addConstr((z_ab == 1) >> (self.u[t1, succ_a] - self.u[t2, o2] <= -1))
                
            for succ_b in op_b.successors:
                # Same blocking logic mirrored if Train 2 goes before Train 1 (z_ba==1).
                # --> Corresponds to DISPLIB Paper Eq (3) lower part: u_{b_bar}^j - u_a^i <= -1 + M(1 - z_{b,a}^{i,j})
                #     (u_{b_bar}^j <==> self.u[t2, succ_b], u_a^i <==> self.u[t1, o1], z_{b,a}^{i,j} <==> z_ba)
                self.model.addConstr((z_ba == 1) >> (self.t[t2, succ_b] - self.t[t1, o1] <= -l2))
                self.model.addConstr((z_ba == 1) >> (self.u[t2, succ_b] - self.u[t1, o1] <= -1))

        # C) General Anti-swapping Ordering
        # ----------------------------------------------------------------------
        # Variable Mapping for DISPLIB Paper Equation (3):
        # u_a^i           <==> self.u[train.id, op.id]          (Topological rank)
        # y_{a,b}^i       <==> self.y[train.id, op.id, succ]    (Route succession status)
        # z_{a,b}^{i,j}   <==> z_ab                             (Across-train resource precedence)
        # ----------------------------------------------------------------------
        for train in self.instance.trains:
            for op in train.operations:
                for succ in op.successors:
                    # Enforce strictly increasing topological sequence (u-values) 
                    # as the train progresses forward through its route.
                    # --> Corresponds to DISPLIB Paper Eq (3) upper part: u_a^i - u_b^i <= -1 + M(1 - y_{a,b}^i)
                    #     (u_a^i <==> self.u[..op.id], u_b^i <==> self.u[..succ])
                    self.model.addConstr((self.y[train.id, op.id, succ] == 1) >> (self.u[train.id, op.id] - self.u[train.id, succ] <= -1))

        # D) Objective Cost Component
        obj_expr = gp.LinExpr()
        for c_idx, comp in enumerate(self.instance.objective):
            if comp.train == -1 or comp.operation == -1:
                continue
                
            w_c = self.w[c_idx]
            v_c = self.v[c_idx]
            t_a = self.t[comp.train, comp.operation]
            x_a = self.x[comp.train, comp.operation]
            
            # Indicators for computing penalty exactly when x_a == 1
            self.model.addConstr((x_a == 1) >> (t_a - comp.threshold <= self.M * v_c))
            self.model.addConstr((x_a == 1) >> (w_c >= comp.coeff * (t_a - comp.threshold)))
            
            obj_expr += w_c
            
        self.model.setObjective(obj_expr, GRB.MINIMIZE)

    def optimize(self, time_limit=600):
        self.model.setParam('TimeLimit', time_limit)
        self.model.optimize()
        
    def export_solution(self, filename: str):
        if self.model.status not in (GRB.OPTIMAL, GRB.TIME_LIMIT, GRB.SUBOPTIMAL):
            print("No valid solution to export!")
            return
            
        events = []
        for train in self.instance.trains:
            for op in train.operations:
                val_x = self.x[train.id, op.id].X
                if val_x > 0.5: # Operation is selected
                    val_t = self.t[train.id, op.id].X
                    events.append({
                        "operation": op.id,
                        "time": int(round(val_t)),
                        "train": train.id
                    })
        
        # ---------------------------------------------------------
# ROBUST EVENT EXPORT FOR VERIFIER
# ---------------------------------------------------------
        from collections import defaultdict

        def get_res(tr, op_id):
            op = self.instance.trains[tr].get_operation(op_id)
            return [r.resource for r in getattr(op, "resources", [])]

        # 1. Events aus tatsächlich gewähltem y-Pfad bauen
        events = []

        for train in self.instance.trains:
            selected_edges = {}

            for (tr, a, b), var in self.y.items():
                if tr == train.id and var.X > 0.5:
                    selected_edges[a] = b

            predecessors = {op.id: [] for op in train.operations}
            for op in train.operations:
                for succ in op.successors:
                    predecessors[succ].append(op.id)

            entries = [
                op.id for op in train.operations
                if len(predecessors[op.id]) == 0
            ]

            cur = entries[0]
            visited = set()
            pos = 0

            while cur not in visited:
                visited.add(cur)

                events.append({
                    "operation": cur,
                    "time": int(round(self.t[train.id, cur].X)),
                    "train": train.id,
                    "pos": pos
                })

                pos += 1

                if cur not in selected_edges:
                    break

                cur = selected_edges[cur]

        # 2. Grundsortierung: Zeit global, aber Zugpfadposition intern stabil
        events.sort(key=lambda e: (e["time"], e["train"], e["pos"]))

        # 3. frees/allocates bestimmen
        prev_op = {}

        for e in events:
            tr = e["train"]
            op = e["operation"]

            e["allocates"] = get_res(tr, op)

            if tr in prev_op:
                e["frees"] = get_res(tr, prev_op[tr])
            else:
                e["frees"] = []

            prev_op[tr] = op

        # 4. Nur innerhalb gleicher Zeit umsortieren:
        #    - gleicher Zug bleibt immer in Pfad-Reihenfolge
        #    - Resource-Freigabe vor Resource-Allokation
        groups = defaultdict(list)

        for e in events:
            groups[e["time"]].append(e)

        final_events = []

        for t in sorted(groups.keys()):
            group = groups[t]

            for _ in range(len(group)):
                changed = False

                for i in range(len(group)):
                    for j in range(i + 1, len(group)):
                        e1 = group[i]
                        e2 = group[j]

                        # Gleicher Zug: Pfad-Reihenfolge darf nie verletzt werden
                        if e1["train"] == e2["train"]:
                            if e1["pos"] > e2["pos"]:
                                group[i], group[j] = group[j], group[i]
                                changed = True
                            continue

                        # Falls e2 eine Ressource freigibt, die e1 braucht:
                        # e2 muss vor e1 stehen
                        e2_frees_for_e1 = any(
                            r in e1["allocates"] for r in e2["frees"]
                        )

                        if e2_frees_for_e1:
                            group[i], group[j] = group[j], group[i]
                            changed = True
                            continue

                if not changed:
                    break

            for e in group:
                final_events.append({
                    "operation": e["operation"],
                    "time": e["time"],
                    "train": e["train"]
                })

        events = final_events

        
        # ---------------------------------------------------------
        
        output = {
            "events": events,
            "objective_value": int(round(self.model.ObjVal))
        }
        
        os.makedirs(os.path.dirname(filename), exist_ok=True)
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(output, f, indent=4)
        print(f"Solution successfully exported to {filename}")
