"""S9-frozen-1 single routing operators. All random draws use the trial stream."""
import copy
import random
from .deap_adapter import TreeLimitError, gp, FEATURES, PRIMITIVES, leaf, clone_tree, check_tree, to_expression
from .fitness import compare
from fogsim.errors import InputError


def generate(target, method, rng=random):
    nodes=[]
    def visit(depth):
        entry=rng.randrange(6 if method=='full' else 7) if depth<target else 6
        if entry==6:nodes.append(leaf(FEATURES[rng.randrange(10)]))
        else:
            nodes.append(copy.deepcopy(tuple(PRIMITIVES.values())[entry]))
            visit(depth+1);visit(depth+1)
    if method not in ('full','grow') or not 0<=target<=7:raise InputError('invalid generation request')
    visit(0)
    return gp.PrimitiveTree(nodes)


def initialize(limits,rng=random):
    attempts=[]
    for i in range(limits['initialization_attempts']):
        method='full' if rng.random()<limits['init_full_probability'] else 'grow'
        target=rng.randrange(limits['init_min_height'],limits['init_max_height']+1)
        tree=generate(target,method,rng)
        try:check_tree(tree,limits);reason=None
        except TreeLimitError as exc:reason=str(exc)
        attempts.append(dict(attempt=i+1,method=method,target_height=target,actual_height=tree.height,nodes=len(tree),reason=reason))
        if reason is None:return tree,dict(operator='initialization',attempts=attempts)
    raise InputError('initialization attempts exhausted')


def tournament(population,size,rng=random):
    indices=[rng.randrange(len(population)) for _ in range(size)]
    winner=population[indices[0]]
    for index in indices[1:]:
        candidate=population[index]
        if compare(candidate.evaluation,winner.evaluation)<0:winner=candidate
    return winner,dict(sampled=[population[i].individual_id for i in indices],winner=winner.individual_id)


def select_node(tree,probability=.9,rng=random):
    category='function' if rng.random()<=probability else 'feature'
    positions=[i for i,n in enumerate(tree) if (n.arity==2)==(category=='function')]
    if not positions:positions=[0]  # the only feature root
    index=positions[rng.randrange(len(positions))]
    return index,dict(category=category,eligible_positions=positions,index=index,root=index==0)


def replace(tree,index,subtree):
    child=clone_tree(tree)
    child[child.searchSubtree(index)]=list(clone_tree(subtree))
    return child


def crossover(a,b,limits,attempts=1,outputs=2,rng=random):
    if outputs not in (1,2):raise InputError('crossover must output one or two children')
    history=[]
    for attempt in range(1,attempts+1):
        i,ni=select_node(a,limits['node_nonterminal_probability'],rng)
        j,nj=select_node(b,limits['node_nonterminal_probability'],rng)
        proposals=[replace(a,i,b[b.searchSubtree(j)])]
        if outputs==2:proposals.append(replace(b,j,a[a.searchSubtree(i)]))
        legal=[];reasons=[]
        for tree in proposals:
            try:check_tree(tree,limits);legal.append(True);reasons.append(None)
            except TreeLimitError as exc:legal.append(False);reasons.append(str(exc))
        history.append(dict(attempt=attempt,nodes=[ni,nj],legal=legal,reasons=reasons))
        if all(legal):break
    children=[clone_tree(tree if ok else parent) for tree,ok,parent in zip(proposals,legal,(a,b))]
    sources=[dict(role='routing',recipient=k,donor=1-k,recipient_position=(i,j)[k],donor_position=(j,i)[k],
                  fallback_parent=None if legal[k] else k,root_replacement=(i,j)[k]==0 and legal[k]) for k in range(outputs)]
    return children,dict(operator='crossover',role='routing',attempts=history,tail_single_output=outputs==1,
                         accepted_children=outputs,fallback_children=sum(not x for x in legal),sources=sources)


def mutate(a,limits,attempts=1,rng=random):
    history=[]
    for attempt in range(1,attempts+1):
        i,node=select_node(a,limits['node_nonterminal_probability'],rng)
        subtree=generate(limits['mutation_max_height'],'grow',rng)
        proposal=replace(a,i,subtree)
        try:check_tree(proposal,limits);legal=True;reason=None
        except TreeLimitError as exc:legal=False;reason=str(exc)
        history.append(dict(attempt=attempt,node=node,subtree=to_expression(subtree),subtree_height=subtree.height,
                            subtree_nodes=len(subtree),legal=legal,reason=reason))
        if legal:break
    return [clone_tree(proposal if legal else a)],dict(operator='mutation',role='routing',attempts=history,
        accepted_children=1,fallback_children=int(not legal),sources=[dict(role='routing',recipient=0,
        donor='new_subtree' if legal else None,recipient_position=i,fallback_parent=None if legal else 0,
        root_replacement=legal and i==0)])


def reproduce(a):
    return [clone_tree(a)],dict(operator='reproduction',role='routing',attempts=[],accepted_children=1,
                               fallback_children=0,sources=[dict(role='routing',parent=0)])


def choose_operator(weights,rng=random):
    draw=rng.random();boundary=0
    for name in ('crossover','mutation','reproduction'):
        boundary+=weights[name]
        if draw<boundary:return name,draw
    return 'reproduction',draw


def stable_feasible(population):
    plans={p.evaluation['plan_id'] for p in population}
    if len(plans)!=1:raise RuntimeError('cross-plan population ranking')
    return sorted((p for p in population if p.evaluation['status']=='FEASIBLE'),key=lambda p:(p.evaluation['fitness'],p.birth_sequence))
