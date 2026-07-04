# Mathematical Model vs. Baseline MIP vs. Extended CP-SAT

This note is a report-ready comparison between the DISPLIB mathematical model and the two implementations in this repository:

- Baseline: `phase1_baseline/src/mip_model.py` using Gurobi MIP.
- Extended: `phase2_extend/src/cp_model.py` using OR-Tools CP-SAT.

The suggested slide/report layout is three columns:

1. Mathematical expression or screenshot from the paper.
2. Baseline MIP implementation.
3. Extended CP-SAT implementation.

---

## 1. Operation Graph and Data Parameters

**Mathematical expression / screenshot**

Use: `math_screenshot_1.png`

For the MILP variable definitions, use: `math_milp_variables.png`

The paper defines each train as an operation graph. Each operation has:

- minimum duration: `delta`
- earliest start: `alpha`
- latest start: `beta`
- resource requirements: `Psi`
- successor arcs: `S`

**Baseline code**

File: `phase1_baseline/src/data_parser.py`

```python
@dataclass
class Operation:
    id: int
    min_duration: int
    successors: List[int]
    start_lb: int = 0
    start_ub: Optional[float] = None
    resources: List[ResourceRequirement] = field(default_factory=list)
```

Relevant parser lines:

```python
min_duration=op_data.get('min_duration', 0),
successors=op_data.get('successors', []),
start_lb=op_data.get('start_lb', 0),
start_ub=ub,
resources=reqs
```

**Extended code**

File: `phase2_extend/src/data_parser.py`

The CP-SAT model uses the same parsed DISPLIB structure. This means both models solve the same input problem; only the optimization formulation changes.

**Report wording**

Both implementations start from the same DISPLIB JSON structure. The mathematical objects `O_i`, `S_i`, `delta`, `alpha`, `beta`, and `Psi` are first converted into Python dataclasses. This makes the baseline and extended model directly comparable.

---

## 2. Time Bounds and Minimum Duration

**Mathematical expression / screenshot**

Use: `math_precedence.png`

Formula:

```text
alpha_a^i <= t_a^i <= beta_a^i
t_a^i + delta_a^i <= t_{a+}^i
```

**Baseline MIP code**

File: `phase1_baseline/src/mip_model.py`

Start-time variable with lower and upper bounds:

```python
ub = op.start_ub if op.start_ub is not None and op.start_ub < float('inf') else GRB.INFINITY
self.t[train.id, op.id] = self.model.addVar(
    lb=op.start_lb,
    ub=ub,
    vtype=GRB.CONTINUOUS,
    name=f"t_{train.id}_{op.id}"
)
```

Minimum duration along selected successor arc:

```python
self.model.addConstr(
    self.t[train.id, succ] - self.t[train.id, op.id]
    >= op.min_duration * self.y[train.id, op.id, succ]
)
```

**Extended CP-SAT code**

File: `phase2_extend/src/cp_model.py`

Start-time domain:

```python
lb = max(0, int(op.start_lb))
ub = self.horizon if (ub_val is None or ub_val == float('inf')) else min(self.horizon, int(ub_val))
self.starts[t_id, o_id] = self.model.NewIntVar(lb, ub, f"st_{t_id}_{o_id}")
```

Duration and end-time interval:

```python
self.durations[t_id, o_id] = self.model.NewIntVar(
    int(op.min_duration), self.horizon, f"dur_{t_id}_{o_id}"
)
self.ends[t_id, o_id] = self.model.NewIntVar(
    lb + int(op.min_duration), self.horizon + self.horizon, f"end_{t_id}_{o_id}"
)
```

Successor timing:

```python
self.model.Add(
    self.starts[t_id, succ] == self.ends[t_id, o_id]
).OnlyEnforceIf(self.y[t_id, o_id, succ])
```

**Report wording**

In the baseline MIP, the start time `t` is a continuous Gurobi variable with bounds. The duration constraint is activated through the selected arc variable `y`. In the CP-SAT extension, the same logic is represented by interval variables with integer start, duration, and end values.

---

## 3. Route Selection and Flow Conservation

**Mathematical expression / screenshot**

Use: `math_milp_routing_eq1.png`

The selected sequence `pi_i` must be a path from the entry operation to the exit operation.

Reference MILP idea:

```text
sum outgoing arcs from entry = 1
sum incoming arcs to exit = 1
sum incoming arcs = sum outgoing arcs for intermediate operations
y_ab links selected arcs to selected operations x_a, x_b
```

**Baseline MIP code**

File: `phase1_baseline/src/mip_model.py`

Entry and exit:

```python
self.model.addConstr(
    gp.quicksum(self.y[train.id, entry, succ] for succ in op.successors) == 1
)
self.model.addConstr(self.x[train.id, entry] == 1)

self.model.addConstr(
    gp.quicksum(self.y[train.id, pred, exit] for pred in predecessors[train.id][exit]) == 1
)
self.model.addConstr(self.x[train.id, exit] == 1)
```

Flow conservation:

```python
sum_in = gp.quicksum(self.y[train.id, pred, op.id] for pred in predecessors[train.id][op.id])
sum_out = gp.quicksum(self.y[train.id, op.id, succ] for succ in op.successors)
self.model.addConstr(sum_in == sum_out)
self.model.addConstr(sum_in == self.x[train.id, op.id])
```

Arc-operation linking:

```python
self.model.addConstr(self.y[train.id, op.id, succ] <= self.x[train.id, op.id])
self.model.addConstr(self.y[train.id, op.id, succ] <= self.x[train.id, succ])
self.model.addConstr(
    self.x[train.id, op.id] + self.x[train.id, succ] - 1
    <= self.y[train.id, op.id, succ]
)
```

**Extended CP-SAT code**

File: `phase2_extend/src/cp_model.py`

Entry and exit:

```python
for o_idx in starts_idx:
    self.model.Add(self.x[t_id, o_idx] == 1)

for o_idx in ends_idx:
    self.model.Add(self.x[t_id, o_idx] == 1)
```

Flow in and out:

```python
if o_id not in ends_idx:
    self.model.Add(
        sum(self.y[t_id, o_id, succ] for succ in op.successors)
        == self.x[t_id, o_id]
    )

if o_id not in starts_idx:
    preds = predecessors[t_id][o_id]
    self.model.Add(
        sum(self.y[t_id, p, o_id] for p in preds)
        == self.x[t_id, o_id]
    )
```

**Report wording**

Both models enforce that every train chooses exactly one feasible path through its directed acyclic operation graph. The baseline expresses this with classical MIP flow constraints. The CP-SAT model keeps the same `x` and `y` logic, but uses CP-SAT Boolean constraints.

---

## 4. Resource Exclusivity and Release Time

**Mathematical expression / screenshot**

Use: `math_milp_resource_eq2.png`

If you also want to show the mathematical conflict-pair set, use: `math_milp_conflict_set_A.png`

Formula:

```text
If operation o_a^i is before o_b^j on the same resource:
eta(o_{a+}^i) < eta(o_b^j)
t_{a+}^i + lambda <= t_b^j
```

**Baseline MIP code**

File: `phase1_baseline/src/mip_model.py`

Conflict pairs are generated from shared resources:

```python
conflicts = self.instance.find_conflict_pairs()
```

For each conflict pair, the model creates precedence variables:

```python
z_ab = self.model.addVar(vtype=GRB.BINARY, name=f"z_{t1}_{o1}_{t2}_{o2}_r_{res}")
z_ba = self.model.addVar(vtype=GRB.BINARY, name=f"z_{t2}_{o2}_{t1}_{o1}_r_{res}")
```

If both operations are selected, one order must be chosen:

```python
self.model.addConstr(x_a >= z_ab + z_ba)
self.model.addConstr(x_b >= z_ab + z_ba)
self.model.addConstr(x_a + x_b - 1 <= z_ab + z_ba)
```

Time separation with release time:

```python
self.model.addConstr(
    (z_ab == 1) >>
    (self.t[t1, succ_a] - self.t[t2, o2] <= -l1)
)

self.model.addConstr(
    (z_ba == 1) >>
    (self.t[t2, succ_b] - self.t[t1, o1] <= -l2)
)
```

**Extended CP-SAT code**

File: `phase2_extend/src/cp_model.py`

The extended model mainly replaces pairwise Big-M-style resource constraints with interval no-overlap:

```python
iv = self.model.NewOptionalIntervalVar(
    self.starts[t_id, o_id],
    self.durations[t_id, o_id],
    self.ends[t_id, o_id],
    self.x[t_id, o_id],
    f"iv_{t_id}_{o_id}"
)
```

Release time is represented by extending the interval:

```python
ext_dur = self.model.NewIntVar(
    int(op.min_duration) + rel_time,
    self.horizon + rel_time,
    f"ext_dur_{t_id}_{o_id}_{res_name}"
)
self.model.Add(ext_dur == self.durations[t_id, o_id] + rel_time)

ext_iv = self.model.NewOptionalIntervalVar(
    self.starts[t_id, o_id],
    ext_dur,
    ext_end,
    self.x[t_id, o_id],
    f"ext_iv_{t_id}_{o_id}_{res_name}"
)
```

No two intervals on the same resource may overlap:

```python
for res_name, intervals in resource_intervals.items():
    self.model.AddNoOverlap(intervals)
```

**Report wording**

The baseline follows the paper's pairwise conflict logic: for every shared resource pair, a binary variable decides which train goes first. The CP-SAT extension models the same safety rule more directly: every resource has a list of optional occupation intervals, and `AddNoOverlap` prevents collisions. Release times are handled by extending the occupation interval beyond the physical end.

---

## 5. Global Ordering and Anti-Swapping Logic

**Mathematical expression / screenshot**

Use: `math_milp_ordering_eq3.png`

The paper requires a globally ordered event sequence `Pi`, not only sorted start times. This is necessary when durations or release times can be zero.

**Baseline MIP code**

File: `phase1_baseline/src/mip_model.py`

The baseline introduces an ordering variable:

```python
self.u[train.id, op.id] = self.model.addVar(
    lb=0,
    vtype=GRB.CONTINUOUS,
    name=f"u_{train.id}_{op.id}"
)
```

Same-train order:

```python
self.model.addConstr(
    (self.y[train.id, op.id, succ] == 1) >>
    (self.u[train.id, op.id] - self.u[train.id, succ] <= -1)
)
```

Cross-train conflict order:

```python
self.model.addConstr(
    (z_ab == 1) >>
    (self.u[t1, succ_a] - self.u[t2, o2] <= -1)
)

self.model.addConstr(
    (z_ba == 1) >>
    (self.u[t2, succ_b] - self.u[t1, o1] <= -1)
)
```

Solution export uses this rank:

```python
events.sort(key=lambda x: (x["time"], self.u[x["train"], x["operation"]].X))
```

**Extended CP-SAT code**

File: `phase2_extend/src/cp_model.py`

The extended model also uses an integer topological rank:

```python
self.u[t_id, o_id] = self.model.NewIntVar(
    0,
    sum(len(tr.operations) for tr in self.instance.trains),
    f"u_{t_id}_{o_id}"
)
```

Conflict order:

```python
self.model.Add(
    self.u[t2, o2] >= self.u[t1, succ_a] + 1
).OnlyEnforceIf([z_ab, self.y[t1, o1, succ_a]])

self.model.Add(
    self.u[t1, o1] >= self.u[t2, succ_b] + 1
).OnlyEnforceIf([z_ba, self.y[t2, o2, succ_b]])
```

Export:

```python
events.sort(
    key=lambda x: (
        x["time"],
        self.solver.Value(self.u[x["train"], x["operation"]])
    )
)
```

**Report wording**

This part handles a subtle DISPLIB requirement: two events with the same timestamp still need a valid order. The `u` variable represents this topological order. It prevents unrealistic swapping behavior where two trains exchange resources at the exact same time in a way that violates the event-sequence definition.

---

## 6. Objective Function

**Mathematical expression / screenshot**

Use: `math_objective.png` for the original DISPLIB objective definition.

Use: `math_milp_objective_eq4.png` for the MILP objective constraints with `v_c` and `w_c`.

Formula:

```text
Z(Pi) = sum_{c in C} z(c, Pi)
z(c, Pi) = gamma * max(0, t_a^i - threshold) + zeta * H(t_a^i - threshold)
```

**Baseline MIP code**

File: `phase1_baseline/src/mip_model.py`

Auxiliary objective variables:

```python
self.v[c_idx] = self.model.addVar(vtype=GRB.BINARY, name=f"v_{c_idx}")
self.w[c_idx] = self.model.addVar(lb=0, vtype=GRB.CONTINUOUS, name=f"w_{c_idx}")
```

Delay penalty:

```python
self.model.addConstr((x_a == 1) >> (t_a - comp.threshold <= self.M * v_c))
self.model.addConstr((x_a == 1) >> (w_c >= comp.coeff * (t_a - comp.threshold)))

obj_expr += w_c
self.model.setObjective(obj_expr, GRB.MINIMIZE)
```

**Extended CP-SAT code**

File: `phase2_extend/src/cp_model.py`

Delay variable and scaled cost:

```python
over_time = self.model.NewIntVar(0, self.horizon * 2, f"ov_{c_idx}")
self.model.Add(over_time >= self.starts[t_id, o_id] - th).OnlyEnforceIf(x_a)

cost_var = self.model.NewIntVar(
    0,
    int(self.horizon * 2 * max(1, scaled_cf)),
    f"cost_{c_idx}"
)
self.model.Add(cost_var == over_time * scaled_cf).OnlyEnforceIf(x_a)
self.model.Add(cost_var == 0).OnlyEnforceIf(x_a.Not())

obj_costs.append(cost_var)
self.model.Minimize(sum(obj_costs))
```

**Report wording**

Both models minimize the total weighted delay of selected objective operations. The baseline uses a continuous cost variable `w_c`, while the CP-SAT model uses integer cost variables and a scaling factor because CP-SAT works with integer arithmetic.

Important limitation: the current implementation covers the linear delay term `coeff * max(0, delay)`. The DISPLIB paper also allows a fixed step penalty `increment` / `zeta`, but this is not implemented in the current code.

---

## Compact Comparison Table

| Mathematical concept | Baseline MIP | Extended CP-SAT |
|---|---|---|
| Operation selected | `x[train, op]` binary variable | `x[train, op]` Boolean variable |
| Successor arc selected | `y[train, op, succ]` binary variable | `y[train, op, succ]` Boolean variable |
| Start time | `t[train, op]` continuous variable | `starts[train, op]` integer variable |
| Minimum duration | `t_succ - t_op >= duration * y` | interval duration and `start_succ == end_op` |
| Resource conflict | Pairwise `z_ab`, `z_ba` precedence variables | `AddNoOverlap` over optional intervals |
| Release time | Included in pairwise separation constraints | Interval is extended by `release_time` |
| Global event order | `u[train, op]` ordering variable | integer `u[train, op]` topological rank |
| Objective | Minimize sum of `w_c` | Minimize sum of scaled integer `cost_var` |

---

## Suggested Report Paragraph

The baseline model implements the reference DISPLIB MILP formulation. It uses binary variables for route selection and resource precedence, continuous start-time variables, and topological order variables to produce a globally valid event sequence. The extended model keeps the same DISPLIB input structure and route-selection logic, but reformulates the scheduling part as a CP-SAT interval model. In particular, resource conflicts are handled through optional interval variables and `AddNoOverlap`, which replaces many pairwise Big-M-style constraints with a more native scheduling formulation.
