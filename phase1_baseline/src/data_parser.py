import json
from dataclasses import dataclass, field
from typing import List, Dict, Tuple, Optional, Any

@dataclass
class ResourceRequirement:
    resource: str
    release_time: int = 0

@dataclass
class Operation:
    id: int # The index of this operation for the train
    min_duration: int
    successors: List[int]
    start_lb: int = 0
    start_ub: Optional[float] = None
    resources: List[ResourceRequirement] = field(default_factory=list)

@dataclass
class Train:
    id: int
    operations: List[Operation]
    
    def get_operation(self, op_id: int) -> Operation:
        return self.operations[op_id]

@dataclass
class ObjectiveComponent:
    comp_type: str
    train: int
    operation: int
    threshold: int
    coeff: float

@dataclass
class DisplibInstance:
    trains: List[Train]
    objective: List[ObjectiveComponent]

    @classmethod
    def from_json(cls, file_path: str) -> 'DisplibInstance':
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        trains_list = []
        for t_idx, train_data in enumerate(data.get('trains', [])):
            ops_list = []
            for op_idx, op_data in enumerate(train_data):
                # parse resources
                reqs = []
                for res_dict in op_data.get('resources', []):
                    reqs.append(ResourceRequirement(
                        resource=res_dict.get('resource'),
                        release_time=res_dict.get('release_time', 0)
                    ))
                
                # Use standard big value or None for missing upper bound
                ub = op_data.get('start_ub')
                if ub is None:
                    ub = float('inf')

                op = Operation(
                    id=op_idx,
                    min_duration=op_data.get('min_duration', 0),
                    successors=op_data.get('successors', []),
                    start_lb=op_data.get('start_lb', 0),
                    start_ub=ub,
                    resources=reqs
                )
                ops_list.append(op)
            trains_list.append(Train(id=t_idx, operations=ops_list))
        
        obj_list = []
        for obj_data in data.get('objective', []):
            obj_list.append(ObjectiveComponent(
                comp_type=obj_data.get('type', ''),
                train=obj_data.get('train', -1),
                operation=obj_data.get('operation', -1),
                threshold=obj_data.get('threshold', 0),
                coeff=float(obj_data.get('coeff', 0.0))
            ))
            
        return cls(trains=trains_list, objective=obj_list)
        
    def find_conflict_pairs(self) -> List[Tuple[int, int, int, int, str, int, int]]:
        """
        Returns pairs of operations from different trains that require the same resource.
        Returns tuples of (train_i, op_a, train_j, op_b, resource, lambda_i, lambda_j)
        for i < j to avoid duplicate symmetric pairs.
        """
        # Map resource -> list of (train_idx, op_idx, release_time)
        res_map = {}
        for t in self.trains:
            for op in t.operations:
                for req in op.resources:
                    if req.resource not in res_map:
                        res_map[req.resource] = []
                    res_map[req.resource].append((t.id, op.id, req.release_time))
                    
        conflicts = []
        for res, usage_list in res_map.items():
            for idx1 in range(len(usage_list)):
                for idx2 in range(idx1 + 1, len(usage_list)):
                    t1, op1, l1 = usage_list[idx1]
                    t2, op2, l2 = usage_list[idx2]
                    if t1 != t2:
                        # ensure t1 < t2 for consistent ordering
                        if t1 > t2:
                            conflicts.append((t2, op2, t1, op1, res, l2, l1))
                        else:
                            conflicts.append((t1, op1, t2, op2, res, l1, l2))
        
        return list(set(conflicts))
