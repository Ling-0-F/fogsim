"""DEAP storage only; execution always goes through the strict B08 front end."""
import copy
import math
import struct
from importlib.metadata import version, PackageNotFoundError
from fogsim.errors import InputError
from fogsim.gp.parser import parse_expression
from fogsim.gp.ast import structural_key
from fogsim.rules.specs import RuleSpec
from fogsim.rules.factory import prepare_rules

try:
    from deap import gp, base
except ImportError as exc:
    raise InputError('training requires DEAP 1.4.4; install the locked train dependencies') from exc
if version('deap') != '1.4.4':
    raise InputError('training requires the verified DEAP version 1.4.4')

class TreeLimitError(InputError):pass


FEATURES = ('NIQ','WIQ','MRT','UT','DT','PT','TTIQ','TIS','TWT','NTR')
FUNCTIONS = {'ADD': '+', 'SUB': '-', 'MUL': '*', 'DIV': '/', 'MAX': 'Max', 'MIN': 'Min'}
PRIMITIVES = {key: gp.Primitive(key, [object, object], object) for key in FUNCTIONS}
REVERSE = {v:k for k,v in FUNCTIONS.items()}


def clone_tree(tree):
    # PrimitiveTree.__deepcopy__ shares its nodes. These nodes are mutable.
    return gp.PrimitiveTree([copy.deepcopy(n) for n in tree])


def leaf(name):
    return gp.Terminal(name, True, object)


def from_expression(text):
    nodes=[]
    for row in structural_key(parse_expression(text).root):
        nodes.append(copy.deepcopy(PRIMITIVES[REVERSE[row[1]]]) if row[0]=='binary' else
                     leaf(row[1] if row[0]=='feature' else 'f64:'+row[1]))
    return gp.PrimitiveTree(nodes)


def to_expression(tree):
    stack=[]
    for node in reversed(tree):
        if node.arity == 2 and node.name in FUNCTIONS:
            if len(stack)<2:raise InputError('malformed DEAP tree')
            left,right=stack.pop(),stack.pop()
            stack.append(f'({FUNCTIONS[node.name]} {left} {right})')
        elif node.arity == 0 and node.value in FEATURES:
            stack.append(node.value)
        elif node.arity == 0 and isinstance(node.value,str) and node.value.startswith('f64:'):
            try:
                bits=node.value[4:]
                if len(bits)!=16 or bits.lower()!=bits:raise ValueError()
                value=struct.unpack('>d',bytes.fromhex(bits))[0]
                if math.isnan(value):raise ValueError('NaN constant has no strict source token')
                stack.append(('1e309' if value>0 else '-1e309') if math.isinf(value) else repr(value))
            except (ValueError,struct.error) as exc:raise InputError('invalid constant terminal') from exc
        else:raise InputError('invalid DEAP node')
    if len(stack)!=1:raise InputError('malformed DEAP tree')
    return stack[0]


def check_tree(tree, limits, *, allow_constants=False, role='routing'):
    # Parse before height so a malformed prefix can never enter a simulator.
    expr=to_expression(tree)
    if not allow_constants and any(n.arity==0 and n.value not in FEATURES for n in tree):
        raise InputError('numeric ERC evolution is disabled')
    if tree.height>limits['max_height']:raise TreeLimitError('height exceeds training limit')
    if len(tree)>limits['max_nodes']:raise TreeLimitError('nodes exceed training limit')
    parse_expression(expr,role=role)
    return expr


def prepare_single(tree):
    return prepare_rules(RuleSpec('routing','gp',expression=to_expression(tree)), RuleSpec('sequencing','fcfs'))


DUAL_ROLES = ('sequencing', 'routing')


def clone_dual(trees):
    if not isinstance(trees, (tuple, list)) or len(trees) != 2:
        raise InputError('dual_tree requires exactly [sequencing, routing]')
    return tuple(clone_tree(tree) for tree in trees)


def prepare_dual(trees):
    if not isinstance(trees, (tuple, list)) or len(trees) != 2:
        raise InputError('dual_tree requires exactly [sequencing, routing]')
    return prepare_rules(RuleSpec('routing','gp',expression=to_expression(trees[1])),
                         RuleSpec('sequencing','gp',expression=to_expression(trees[0])))


class TrainingFitness(base.Fitness):
    weights=(-1.0,)


class Individual:
    def __init__(self, tree, individual_id, birth_sequence, lineage):
        self.tree=clone_tree(tree)
        self.individual_id=individual_id
        self.birth_sequence=birth_sequence
        self.lineage=copy.deepcopy(lineage)
        self.fitness=TrainingFitness()
        self.evaluation=None

    @property
    def genome(self):
        return self.tree

    def prepare(self):
        return prepare_single(self.tree)

    def validate(self, limits):
        check_tree(self.tree, limits)

    def set_evaluation(self,value):
        self.evaluation=copy.deepcopy(value)
        # Domain feasibility remains authoritative, not DEAP fitness.valid.
        if value['status']=='FEASIBLE':self.fitness.values=(value['fitness'],)
        else:del self.fitness.values

    def record(self):
        prepared=prepare_single(self.tree)
        return dict(individual_id=self.individual_id,birth_sequence=self.birth_sequence,
            roles={'0':'routing'},trees={'routing':dict(expression=to_expression(self.tree),height=self.tree.height,nodes=len(self.tree))},
            rules=dict(routing=prepared.routing_spec.to_dict(),sequencing=prepared.sequencing_spec.to_dict()),
            rule_manifest=prepared.rule_manifest,rule_pair_id=prepared.rule_pair_id,lineage=copy.deepcopy(self.lineage),
            evaluated=False,fitness_valid=self.fitness.valid)


class DualIndividual(Individual):
    """One individual, two explicitly ordered roles, one shared evaluation."""
    def __init__(self, trees, individual_id, birth_sequence, lineage):
        self.trees=clone_dual(trees)
        self.individual_id=individual_id
        self.birth_sequence=birth_sequence
        self.lineage=copy.deepcopy(lineage)
        self.fitness=TrainingFitness()
        self.evaluation=None

    @property
    def genome(self):
        return self.trees

    def prepare(self):
        return prepare_dual(self.trees)

    def validate(self, limits):
        for role, tree in zip(DUAL_ROLES, self.trees):
            check_tree(tree, limits, role=role)

    def record(self):
        prepared=self.prepare()
        return dict(individual_id=self.individual_id,birth_sequence=self.birth_sequence,
            roles={str(i):role for i,role in enumerate(DUAL_ROLES)},
            trees={role:dict(expression=to_expression(tree),height=tree.height,nodes=len(tree))
                   for role,tree in zip(DUAL_ROLES,self.trees)},
            rules=dict(routing=prepared.routing_spec.to_dict(),sequencing=prepared.sequencing_spec.to_dict()),
            rule_manifest=prepared.rule_manifest,rule_pair_id=prepared.rule_pair_id,lineage=copy.deepcopy(self.lineage),
            evaluated=False,fitness_valid=self.fitness.valid)


def make_individual(genome, individual_id, birth_sequence, lineage, mode):
    if mode=='single_routing':cls=Individual
    elif mode=='dual_tree':cls=DualIndividual
    else:raise InputError('unsupported individual mode')
    return cls(genome,individual_id,birth_sequence,lineage)
