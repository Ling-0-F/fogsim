"""Named acceptance fixtures; integer outcomes derived independently by hand."""
LEGACY_CASES = ("single_local", "single_local_release5", "chain_remote", "chain_fcfs")
V2_CASES = {
    # name: (makespan, event count, decision count)
    "v2_diamond": (11, 13, 8),
    "v2_contention": (17, 12, 5),
    "v2_candidates": (14, 27, 10),
    "v2_collision_m0": (11, 20, 8),
    "v2_collision_e0": (11, 20, 8),
    "v2_equal_heap": (12, 39, 29),
    "v2_float_local": (1.6, 16, 7),
    "v2_float_remote": (2.2, 16, 7),
    "v2_shared_server": (8, 15, 8),
    "v2_order": (4, 12, 4),
}
DEFAULT_CASES = (*LEGACY_CASES, *V2_CASES)
