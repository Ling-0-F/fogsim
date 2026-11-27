def ready_tasks(workflow, view):
    """Pure query. Membership is activation, not just release_time <= clock."""
    if not any(w is workflow for w in view.active_workflows):
        return []
    return [t for t in workflow.tasks
            if not t.dispatched and not t.completed and all(p.completed for p in t.parents)]
