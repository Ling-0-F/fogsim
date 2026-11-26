#pragma once
#define FOG_GPU 1
#include "fitness_core.hpp"
using namespace fitness;

template <class T> struct Buffer {
    T *ptr = nullptr;
    ~Buffer() {
        if (ptr)
            FOG_RUNTIME(Free)(ptr);
    }
    FOG_RUNTIME(Error_t) allocate(size_t n) {
        return FOG_RUNTIME(Malloc)(reinterpret_cast<void **>(&ptr), n * sizeof(T));
    }
};
struct Event {
    FOG_RUNTIME(Event_t) handle = nullptr;
    ~Event() {
        if (handle)
            FOG_RUNTIME(EventDestroy)(handle);
    }
};
#define CHECK(call)                                                                                          \
    do {                                                                                                     \
        auto error = (call);                                                                                 \
        if (error != FOG_RUNTIME(Success))                                                                   \
            return FOG_RUNTIME(GetErrorString)(error);                                                       \
    } while (0)

__global__ void generation(Shape d, const int *input_i, const double *input_d, int *work_i, double *work_d,
                           int *status, double *scores) {
    int p = blockIdx.x;
    __shared__ Scratch scratch;
    simulate(p, d, input(d, input_i, input_d), state(d, p, work_i, work_d), scratch, status, scores);
}

extern "C" const char *full_fitness(Shape d, const int *input_i, const double *input_d, int *status,
                                    double *scores, int trace_count, int *routes, double *times, int workers,
                                    float *kernel_ms) {
    if (trace_count < 0 || trace_count > d.policies)
        return "invalid GPU trace dimensions";
    if (workers < 1 || workers > 64)
        return "invalid GPU block width";
    Buffer<int> ii, wi, flags;
    Buffer<double> xx, wx, values;
    CHECK(ii.allocate(ints_in(d)));
    CHECK(xx.allocate(doubles_in(d)));
    CHECK(wi.allocate(static_cast<size_t>(d.policies) * ints_per_policy(d)));
    CHECK(wx.allocate(static_cast<size_t>(d.policies) * doubles_per_policy(d)));
    CHECK(flags.allocate(d.policies));
    CHECK(values.allocate(d.policies));
    CHECK(FOG_RUNTIME(Memcpy)(ii.ptr, input_i, ints_in(d) * sizeof(int), FOG_RUNTIME(MemcpyHostToDevice)));
    CHECK(FOG_RUNTIME(Memcpy)(xx.ptr, input_d, doubles_in(d) * sizeof(double),
                              FOG_RUNTIME(MemcpyHostToDevice)));
    Event begin, end;
    CHECK(FOG_RUNTIME(EventCreate)(&begin.handle));
    CHECK(FOG_RUNTIME(EventCreate)(&end.handle));
    CHECK(FOG_RUNTIME(EventRecord)(begin.handle));
    generation<<<d.policies, workers>>>(d, ii.ptr, xx.ptr, wi.ptr, wx.ptr, flags.ptr, values.ptr);
    CHECK(FOG_RUNTIME(GetLastError)());
    CHECK(FOG_RUNTIME(EventRecord)(end.handle));
    CHECK(FOG_RUNTIME(EventSynchronize)(end.handle));
    CHECK(FOG_RUNTIME(EventElapsedTime)(kernel_ms, begin.handle, end.handle));
    CHECK(FOG_RUNTIME(Memcpy)(status, flags.ptr, d.policies * sizeof(int), FOG_RUNTIME(MemcpyDeviceToHost)));
    CHECK(FOG_RUNTIME(Memcpy)(scores, values.ptr, d.policies * sizeof(double),
                              FOG_RUNTIME(MemcpyDeviceToHost)));
    for (int p = 0; p < trace_count; ++p) {
        State memory = state(d, p, wi.ptr, wx.ptr);
        CHECK(FOG_RUNTIME(Memcpy)(routes + static_cast<size_t>(p) * d.tasks, memory.route,
                                  d.tasks * sizeof(int), FOG_RUNTIME(MemcpyDeviceToHost)));
        CHECK(FOG_RUNTIME(Memcpy)(times + static_cast<size_t>(p) * 5 * d.tasks, memory.sent,
                                  5 * d.tasks * sizeof(double), FOG_RUNTIME(MemcpyDeviceToHost)));
    }
    return nullptr;
}
