"""The ten frozen Java feature semantics, read from the supplied live objects.

Low-level boundary fixtures may call this directly. Canonical identity and
phase validation belong to the real GPRule entry point in B03. No values are
cached, repaired or written here; queue properties retain resource branches.
"""
from enum import Enum


class Feature(str, Enum):
    NIQ = "NIQ"
    WIQ = "WIQ"
    MRT = "MRT"
    UT = "UT"
    DT = "DT"
    PT = "PT"
    TTIQ = "TTIQ"
    TIS = "TIS"
    TWT = "TWT"
    NTR = "NTR"


def read_feature(feature: Feature | str, option, context) -> float:
    feature = Feature(feature)
    if feature == Feature.NIQ:
        return float(len(option.resource.waiting_queue))
    if feature == Feature.WIQ:
        return option.resource.waiting_processing_time
    if feature == Feature.MRT:
        return option.resource.available_time
    if feature == Feature.UT:
        return option.upload_time
    if feature == Feature.DT:
        return option.download_time
    if feature == Feature.PT:
        return option.processing_time
    if feature == Feature.TTIQ:
        return option.resource.waiting_total_time
    if feature == Feature.TIS:
        return context.view.clock_time - option.task.workflow.release_time
    if feature == Feature.TWT:
        return context.view.clock_time - option.ready_time
    # Counts are subtracted as integers before the single binary64 conversion.
    return float(option.task.workflow.task_count - option.task.workflow.completed_task_count)
