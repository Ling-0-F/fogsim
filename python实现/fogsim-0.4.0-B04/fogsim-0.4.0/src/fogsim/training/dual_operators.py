"""S9-frozen-1 J04: same-role subtree exchange plus other-role whole swap."""
import random
from fogsim.errors import InputError
from .deap_adapter import DUAL_ROLES, clone_dual, clone_tree, check_tree
from .operators import initialize, crossover, mutate


def check_dual(trees, limits):
    if not isinstance(trees,(tuple,list)) or len(trees)!=2:
        raise InputError('dual_tree requires exactly [sequencing, routing]')
    for role,tree in zip(DUAL_ROLES,trees):check_tree(tree,limits,role=role)


def initialize_dual(limits,rng=random):
    trees=[];records={}
    for role in DUAL_ROLES:
        tree,record=initialize(limits,rng)
        trees.append(tree);records[role]=record
    return tuple(trees),dict(operator='initialization',tree_initializations=records)


def crossover_dual(a,b,limits,attempts=1,outputs=2,rng=random):
    check_dual(a,limits);check_dual(b,limits)
    slot=rng.randrange(2)
    role=DUAL_ROLES[slot];other=DUAL_ROLES[1-slot]
    # Reuse point selection, independent legality and retry termination, never
    # its single-tree fallback: J04 clones the *opposite* complete rule pair.
    selected,record=crossover(a[slot],b[slot],limits,attempts,outputs,rng)
    legal=record['attempts'][-1]['legal'];parents=(a,b)
    children=[];sources=[]
    for direction,ok in enumerate(legal):
        recipient=direction;donor=1-direction
        point=record['sources'][direction]
        if ok:
            child=list(clone_dual(parents[donor]))
            child[slot]=clone_tree(selected[direction])
            origins={role:dict(kind='subtree_replacement',recipient=recipient,donor=donor,
                recipient_position=point['recipient_position'],donor_position=point['donor_position']),
                other:dict(kind='whole_tree_swap',parent=donor)}
        else:
            child=clone_dual(parents[donor])
            origins={r:dict(kind='complete_pair_fallback',parent=donor) for r in DUAL_ROLES}
        check_dual(child,limits)
        children.append(tuple(child))
        sources.append(dict(role=role,recipient=recipient,donor=donor,
            recipient_position=point['recipient_position'],donor_position=point['donor_position'],
            fallback_parent=None if ok else donor,root_replacement=ok and point['root_replacement'],trees=origins))
    record.update(role=role,tree_slot=slot,other_role=other,genome_mode='dual_tree',sources=sources,
                  whole_tree_swap_directions=[i+1 for i,ok in enumerate(legal) if ok])
    return children,record


def mutate_dual(a,limits,attempts=1,rng=random):
    check_dual(a,limits)
    slot=rng.randrange(2);role=DUAL_ROLES[slot]
    selected,record=mutate(a[slot],limits,attempts,rng)
    legal=record['attempts'][-1]['legal']
    child=list(clone_dual(a))
    if legal:child[slot]=clone_tree(selected[0])
    check_dual(child,limits)
    point=record['sources'][0]
    origins={r:dict(kind='unchanged_clone' if legal else 'complete_pair_fallback',parent=0) for r in DUAL_ROLES}
    if legal:origins[role]=dict(kind='new_subtree',recipient=0,recipient_position=point['recipient_position'])
    record.update(role=role,tree_slot=slot,genome_mode='dual_tree',sources=[dict(role=role,
        recipient=0,donor='new_subtree' if legal else None,recipient_position=point['recipient_position'],
        fallback_parent=None if legal else 0,root_replacement=point['root_replacement'],trees=origins)])
    return [tuple(child)],record


def reproduce_dual(a):
    return [clone_dual(a)],dict(operator='reproduction',role='rule_pair',genome_mode='dual_tree',
        attempts=[],accepted_children=1,fallback_children=0,sources=[dict(role='rule_pair',parent=0,
        trees={r:dict(kind='unchanged_clone',parent=0) for r in DUAL_ROLES})])
