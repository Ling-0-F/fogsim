#pragma once
#include <cstddef>
#include <cstdint>

#ifdef FOG_GPU
#define FOG_HD __host__ __device__ inline
#else
#define FOG_HD inline
#endif

#include "binary64_divide.hpp"

namespace fitness {
struct Shape {
    int tasks, resources, workflows, mobiles, edges, warmup, policies, words;
};
struct Input {
    const int *workflow, *owner, *first, *parents, *child_offsets, *children, *numeric, *programs, *code;
    const double *release, *upload, *processing, *download, *literals;
};
struct State {
    int *remaining, *degree, *route, *next, *heap, *stage, *list, *head, *tail, *queued, *pending;
    double *sent, *arrival, *start, *computed, *finish, *available, *waiting_work, *waiting_total;
};
struct Scratch {
    int heap_size, stage_size, event, count, chosen, events, error;
    double now;
    int picks[64];
    double scores[64];
};

FOG_HD int lane() {
#if defined(__MUSA_ARCH__) || defined(__CUDA_ARCH__)
    return threadIdx.x;
#else
    return 0;
#endif
}
FOG_HD int lanes() {
#if defined(__MUSA_ARCH__) || defined(__CUDA_ARCH__)
    return blockDim.x;
#else
    return 1;
#endif
}
FOG_HD void barrier() {
#if defined(__MUSA_ARCH__) || defined(__CUDA_ARCH__)
    __syncthreads();
#endif
}
FOG_HD int ints_in(Shape d) {
    return 3 * d.tasks + 2 * d.workflows + 2 + d.edges + d.resources + 2 * d.policies + 1 + d.words;
}
FOG_HD size_t doubles_in(Shape d) {
    return d.workflows + static_cast<size_t>(3) * d.resources * d.tasks + d.words;
}
FOG_HD int ints_per_policy(Shape d) {
    return d.workflows + 4 * d.tasks + 2 * (d.tasks + d.workflows + 2) + 4 * d.resources;
}
FOG_HD int doubles_per_policy(Shape d) { return 5 * d.tasks + 3 * d.resources; }
FOG_HD Input input(Shape d, const int *i, const double *x) {
    Input a;
    a.workflow = i;
    i += d.tasks;
    a.owner = i;
    i += d.workflows;
    a.first = i;
    i += d.workflows + 1;
    a.parents = i;
    i += d.tasks;
    a.child_offsets = i;
    i += d.tasks + 1;
    a.children = i;
    i += d.edges;
    a.numeric = i;
    i += d.resources;
    a.programs = i;
    i += 2 * d.policies + 1;
    a.code = i;
    const size_t cells = static_cast<size_t>(d.tasks) * d.resources;
    a.release = x;
    x += d.workflows;
    a.upload = x;
    x += cells;
    a.processing = x;
    x += cells;
    a.download = x;
    x += cells;
    a.literals = x;
    return a;
}
FOG_HD State state(Shape d, int p, int *ints, double *values) {
    int *i = ints + static_cast<size_t>(p) * ints_per_policy(d);
    double *x = values + static_cast<size_t>(p) * doubles_per_policy(d);
    const int heap_capacity = d.tasks + d.workflows + 2;
    State s;
    s.remaining = i;
    i += d.workflows;
    s.degree = i;
    i += d.tasks;
    s.route = i;
    i += d.tasks;
    s.next = i;
    i += d.tasks;
    s.heap = i;
    i += heap_capacity;
    s.stage = i;
    i += heap_capacity;
    s.list = i;
    i += d.tasks;
    s.head = i;
    i += d.resources;
    s.tail = i;
    i += d.resources;
    s.queued = i;
    i += d.resources;
    s.pending = i;
    s.sent = x;
    x += d.tasks;
    s.arrival = x;
    x += d.tasks;
    s.start = x;
    x += d.tasks;
    s.computed = x;
    x += d.tasks;
    s.finish = x;
    x += d.tasks;
    s.available = x;
    x += d.resources;
    s.waiting_work = x;
    x += d.resources;
    s.waiting_total = x;
    return s;
}
FOG_HD double maximum(double a, double b) { return a > b ? a : b; }
FOG_HD int compare_double(double a, double b) {
    if (a < b)
        return -1;
    if (a > b)
        return 1;
    if (__builtin_isnan(a))
        return __builtin_isnan(b) ? 0 : 1;
    if (__builtin_isnan(b))
        return -1;
    if (a == 0. && b == 0.) {
        union Bits {
            double value;
            std::int64_t bits;
        } x, y;
        x.value = a;
        y.value = b;
        return x.bits < y.bits ? -1 : (x.bits > y.bits ? 1 : 0);
    }
    return 0;
}

enum EventKind { Release, Start, Arrival, Finish };
FOG_HD int event(int index, EventKind kind) { return (index << 2) | kind; }
FOG_HD double event_time(int ev, Input a, State s) {
    const int i = ev >> 2;
    switch (ev & 3) {
    case Release:
        return a.release[i];
    case Start:
        return s.start[i];
    case Arrival:
        return s.arrival[i];
    default:
        return s.finish[i];
    }
}
FOG_HD int compare_event(int aev, int bev, Shape d, Input a, State s) {
    const double x = event_time(aev, a, s), y = event_time(bev, a, s);
    if (x != y)
        return x < y ? -1 : 1;
    const int ka = aev & 3, kb = bev & 3, ia = aev >> 2, ib = bev >> 2;
    if (ka != kb)
        return ka < kb ? -1 : 1;
    if (ka == Release)
        return ia <= ib ? -1 : 1;
    if (ka == Finish) {
        const int ra = s.route[ia], rb = s.route[ib];
        if ((ra < d.mobiles) != (rb < d.mobiles))
            return ra < d.mobiles ? -1 : 1;
        return a.numeric[ra] < a.numeric[rb] ? -1 : 1;
    }
    return 0;
}
FOG_HD void push(int ev, int *heap, int &size, Shape d, Input a, State s) {
    int k = size++;
    while (k > 0) {
        const int parent = (k - 1) >> 1;
        if (compare_event(ev, heap[parent], d, a, s) >= 0)
            break;
        heap[k] = heap[parent];
        k = parent;
    }
    heap[k] = ev;
}
FOG_HD int pop(int *heap, int &size, Shape d, Input a, State s) {
    const int result = heap[0], last = heap[--size];
    if (size) {
        int k = 0;
        while (k < (size >> 1)) {
            int child = 2 * k + 1;
            if (child + 1 < size && compare_event(heap[child], heap[child + 1], d, a, s) > 0)
                ++child;
            if (compare_event(last, heap[child], d, a, s) <= 0)
                break;
            heap[k] = heap[child];
            k = child;
        }
        heap[k] = last;
    }
    return result;
}
FOG_HD void merge(Shape d, Input a, State s, Scratch &c) {
    while (c.stage_size)
        push(pop(s.stage, c.stage_size, d, a, s), s.heap, c.heap_size, d, a, s);
}

enum Op {
    PT,
    UT,
    DT,
    NIQ,
    WIQ,
    TTIQ,
    MRT,
    TIS,
    TWT,
    NTR,
    Literal,
    Add,
    Subtract,
    Multiply,
    Divide,
    Min,
    Max
};
FOG_HD double score(int t, int r, bool routing, int p, Shape d, Input a, State s, double now) {
    double stack[16];
    int used = 0;
    int program = 2 * p + static_cast<int>(routing), cell = t * d.resources + r, w = a.workflow[t];
    for (int i = a.programs[program]; i < a.programs[program + 1]; ++i) {
        int op = a.code[i];
        if (op <= Literal) {
            double x;
            switch (op) {
            case PT:
                x = a.processing[cell];
                break;
            case UT:
                x = a.upload[cell];
                break;
            case DT:
                x = a.download[cell];
                break;
            case NIQ:
                x = s.queued[r];
                break;
            case WIQ:
                x = s.waiting_work[r];
                break;
            case TTIQ:
                x = s.waiting_total[r];
                break;
            case MRT:
                x = s.available[r];
                break;
            case TIS:
                x = now - a.release[w];
                break;
            case TWT:
                x = now - (routing ? (a.parents[t] ? 0. : a.release[w]) : s.arrival[t]);
                break;
            case NTR:
                x = s.remaining[w];
                break;
            default:
                x = a.literals[i];
            }
            stack[used++] = x;
        } else {
            double b = stack[--used], x = stack[used - 1];
            switch (op) {
            case Add:
                x += b;
                break;
            case Subtract:
                x -= b;
                break;
            case Multiply:
                x *= b;
                break;
            case Divide:
#ifdef __MUSA_ARCH__
                x = divide_round_nearest(x, b);
#elif defined(__CUDA_ARCH__)
                x = b == 0. ? 1. : __ddiv_rn(x, b);
#else
                x = b == 0. ? 1. : x / b;
#endif
                break;
            case Min:
                x = x < b ? x : b;
                break;
            default:
                x = b < x ? x : b;
            }
            stack[used - 1] = x;
        }
    }
    return stack[0];
}
FOG_HD bool better(int j, double x, int other, double y, bool routing, Input a, State s) {
    if (other < 0)
        return true;
    int cmp = compare_double(x, y);
    if (cmp)
        return cmp < 0;
    if (!routing) {
        int wi = a.workflow[s.list[j]], wo = a.workflow[s.list[other]];
        if (a.release[wi] != a.release[wo])
            return a.release[wi] < a.release[wo];
        if (a.owner[wi] != a.owner[wo])
            return a.owner[wi] < a.owner[wo];
        if (wi != wo)
            return wi < wo;
    }
    return j < other;
}
FOG_HD int choose(int item, int count, bool routing, int p, Shape d, Input a, State s, Scratch &c) {
    int best = -1;
    double value = 0.;
    for (int j = lane(); j < count; j += lanes()) {
        const int t = routing ? item : s.list[j], r = routing ? j : item;
        if (routing && a.processing[t * d.resources + r] <= 0.)
            continue;
        double x = score(t, r, routing, p, d, a, s, c.now);
        if (better(j, x, best, value, routing, a, s)) {
            best = j;
            value = x;
        }
    }
    c.picks[lane()] = best;
    c.scores[lane()] = value;
    barrier();
    if (!lane()) {
        for (int j = 1; j < lanes(); ++j) {
            int candidate = c.picks[j];
            if (candidate >= 0 && better(candidate, c.scores[j], best, value, routing, a, s)) {
                best = candidate;
                value = c.scores[j];
            }
        }
        c.chosen = best;
    }
    barrier();
    return c.chosen;
}
FOG_HD void reserve(int t, int r, Shape d, Input a, State s, Scratch &c) {
    const int cell = t * d.resources + r;
    double at = maximum(c.now, maximum(s.arrival[t], s.available[r]));
    s.start[t] = at;
    s.computed[t] = at + a.processing[cell];
    s.finish[t] = s.computed[t] + a.download[cell];
    if (!__builtin_isfinite(s.finish[t]) || s.finish[t] <= at)
        c.error = 1;
    s.pending[r] = 1;
    push(event(t, Start), s.stage, c.stage_size, d, a, s);
}
FOG_HD void queue_sums(int t, int r, bool add, Shape d, Input a, State s) {
    if (r >= d.mobiles && s.queued[r] == 0) {
        s.waiting_work[r] = 0.;
        s.waiting_total[r] = 0.;
        return;
    }
    int cell = t * d.resources + r;
    double work = a.processing[cell], total = (work + a.upload[cell]) + a.download[cell];
    if (add) {
        s.waiting_work[r] += work;
        s.waiting_total[r] += total;
    } else {
        s.waiting_work[r] -= work;
        s.waiting_total[r] -= total;
    }
}
FOG_HD void simulate(int p, Shape d, Input a, State s, Scratch &c, int *status, double *fitness) {
    for (int t = lane(); t < d.tasks; t += lanes()) {
        s.degree[t] = a.parents[t];
        s.route[t] = -1;
        s.next[t] = -1;
    }
    for (int r = lane(); r < d.resources; r += lanes()) {
        s.head[r] = s.tail[r] = -1;
        s.queued[r] = s.pending[r] = 0;
        s.available[r] = s.waiting_work[r] = s.waiting_total[r] = 0.;
    }
    for (int w = lane(); w < d.workflows; w += lanes())
        s.remaining[w] = a.first[w + 1] - a.first[w];
    barrier();
    if (!lane()) {
        c.heap_size = c.stage_size = c.events = c.error = 0;
        for (int owner = 0; owner < d.mobiles; ++owner) {
            for (int w = 0; w < d.workflows; ++w)
                if (a.owner[w] == owner)
                    push(event(w, Release), s.stage, c.stage_size, d, a, s);
            merge(d, a, s, c);
        }
    }
    barrier();
    while (true) {
        if (!lane()) {
            merge(d, a, s, c);
            c.event = c.heap_size && !c.error ? pop(s.heap, c.heap_size, d, a, s) : -1;
            if (c.event >= 0) {
                c.now = event_time(c.event, a, s);
                ++c.events;
            }
            c.count = 0;
        }
        barrier();
        const int ev = c.event;
        if (ev < 0)
            break;
        const int kind = ev & 3, t = ev >> 2;
        if (kind == Arrival && !lane()) {
            int r = s.route[t];
            if (s.available[r] > c.now || s.pending[r]) {
                if (s.head[r] < 0)
                    s.head[r] = t;
                else
                    s.next[s.tail[r]] = t;
                s.tail[r] = t;
                ++s.queued[r];
                queue_sums(t, r, true, d, a, s);
            } else
                reserve(t, r, d, a, s, c);
        }
        if (kind == Start && !lane()) {
            int r = s.route[t];
            s.pending[r] = 0;
            s.available[r] = s.finish[t];
            push(event(t, Finish), s.stage, c.stage_size, d, a, s);
        }
        if (kind == Finish) {
            int r = s.route[t];
            if (!lane()) {
                --s.remaining[a.workflow[t]];
                if (!s.pending[r])
                    for (int j = s.head[r]; j >= 0; j = s.next[j])
                        s.list[c.count++] = j;
            }
            barrier();
            if (c.count) {
                int pos = choose(r, c.count, false, p, d, a, s, c);
                if (!lane()) {
                    int chosen = s.list[pos], prev = pos ? s.list[pos - 1] : -1;
                    if (prev < 0)
                        s.head[r] = s.next[chosen];
                    else
                        s.next[prev] = s.next[chosen];
                    if (s.tail[r] == chosen)
                        s.tail[r] = prev;
                    --s.queued[r];
                    queue_sums(chosen, r, false, d, a, s);
                    reserve(chosen, r, d, a, s, c);
                }
            }
            barrier();
            if (!lane()) {
                c.count = 0;
                for (int j = a.child_offsets[t]; j < a.child_offsets[t + 1]; ++j) {
                    int child = a.children[j];
                    if (--s.degree[child] == 0)
                        s.list[c.count++] = child;
                }
            }
        }
        if (kind == Release && !lane())
            for (int root = a.first[t]; root < a.first[t + 1]; ++root)
                if (!a.parents[root])
                    s.list[c.count++] = root;
        barrier();
        if (kind == Finish || kind == Release) {
            for (int j = 0; j < c.count; ++j) {
                int ready = s.list[j];
                int r = choose(ready, d.resources, true, p, d, a, s, c);
                if (!lane()) {
                    s.route[ready] = r;
                    s.sent[ready] = c.now;
                    s.arrival[ready] = c.now + a.upload[ready * d.resources + r];
                    push(event(ready, Arrival), s.stage, c.stage_size, d, a, s);
                }
                barrier();
            }
        }
        barrier();
    }
    if (!lane()) {
        double last = 0.;
        for (int w = 0; w < d.workflows; ++w)
            if (s.remaining[w])
                c.error = 2;
        for (int t = a.first[d.warmup]; t < d.tasks; ++t)
            last = maximum(last, s.finish[t]);
        status[p] = c.error ? -c.error : c.events;
        fitness[p] = last - a.release[d.warmup];
    }
}
} // namespace fitness
