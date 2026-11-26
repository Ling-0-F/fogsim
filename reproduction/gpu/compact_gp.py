"""Immutable opcode trees for the fixed B04 dual-tree search (no ephemeral constants)."""

from functools import lru_cache

from .fitness import OPS

# The order of these two tables is the order used by the seeded B04 generators.
FUNCTIONS = tuple(OPS.index(x) for x in ("+", "-", "*", "/", "Max", "Min"))
FEATURES = tuple(OPS.index(x) for x in ("NIQ", "WIQ", "MRT", "UT", "DT", "PT", "TTIQ", "TIS", "TWT", "NTR"))
FIRST_BINARY = OPS.index("+")


def generate(target, full, rng):
    nodes = bytearray()

    def visit(depth):
        entry = rng.randrange(6 if full else 7) if depth < target else 6
        if entry == 6:
            nodes.append(FEATURES[rng.randrange(10)])
        else:
            nodes.append(FUNCTIONS[entry])
            visit(depth + 1)
            visit(depth + 1)

    visit(0)
    return bytes(nodes)


@lru_cache(maxsize=8192)
def structure(tree):
    ends = [0] * len(tree)
    heights = [0] * len(tree)
    functions, leaves = [], []
    for i in range(len(tree) - 1, -1, -1):
        if tree[i] < FIRST_BINARY:
            ends[i] = i + 1
            leaves.append(i)
        else:
            left = i + 1
            right = ends[left]
            ends[i] = ends[right]
            heights[i] = 1 + max(heights[left], heights[right])
            functions.append(i)
    # Node selection visits the prefix in forward order.
    return ends, heights[0], tuple(reversed(functions)), tuple(reversed(leaves))


@lru_cache(maxsize=8192)
def compiled(tree):
    """Emit the canonical source for B04 reporting and the device program in the same walk."""
    output = bytearray()

    def visit(i):
        op = tree[i]
        if op < FIRST_BINARY:
            output.append(op)
            return OPS[op], i + 1
        left, right_pos = visit(i + 1)
        right, end = visit(right_pos)
        output.append(op)
        return f"({OPS[op]} {left} {right})", end

    source, end = visit(0)
    assert end == len(tree)
    return source, bytes(output)


def legal(tree, limits):
    return len(tree) <= limits["max_nodes"] and structure(tree)[1] <= limits["max_height"]


def initialize_dual(limits, rng):
    pair = []
    for _ in range(2):
        for _ in range(limits["initialization_attempts"]):
            full = rng.random() < limits["init_full_probability"]
            target = rng.randrange(limits["init_min_height"], limits["init_max_height"] + 1)
            tree = generate(target, full, rng)
            if legal(tree, limits):
                pair.append(tree)
                break
        else:
            raise ValueError("Initialization attempt budget exhausted")
    return tuple(pair), None


def position(tree, limits, rng):
    _, _, functions, leaves = structure(tree)
    options = functions if rng.random() <= limits["node_nonterminal_probability"] else leaves
    if not options:
        options = (0,)
    return options[rng.randrange(len(options))]


def replace_role(pair, slot, tree):
    return (pair[0], tree) if slot else (tree, pair[1])


def crossover_dual(a, b, limits, outputs, rng):
    slot = rng.randrange(2)
    x, y = a[slot], b[slot]
    i, j = position(x, limits, rng), position(y, limits, rng)
    end_x, end_y = structure(x)[0][i], structure(y)[0][j]
    child = x[:i] + y[j:end_y] + x[end_x:]
    children = [replace_role(b, slot, child) if legal(child, limits) else b]
    if outputs == 2:
        child = y[:j] + x[i:end_x] + y[end_y:]
        children.append(replace_role(a, slot, child) if legal(child, limits) else a)
    return children, None


def mutate_dual(pair, limits, rng):
    slot = rng.randrange(2)
    parent = pair[slot]
    i = position(parent, limits, rng)
    child = (
        parent[:i] + generate(limits["mutation_max_height"], False, rng) + parent[structure(parent)[0][i] :]
    )
    return [replace_role(pair, slot, child) if legal(child, limits) else pair], None


def reproduce_dual(pair):
    return [pair], None
