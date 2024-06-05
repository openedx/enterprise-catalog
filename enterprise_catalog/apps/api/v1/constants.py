class SegmentEvents:
    """
    api.v1 app-wide Segment event name definitions.
    """
    HIGHLIGHT_SET_CREATED = 'edx.server.enterprise-catalog.highlight-set-lifecycle.created'
    HIGHLIGHT_SET_DELETED = 'edx.server.enterprise-catalog.highlight-set-lifecycle.deleted'
    HIGHLIGHT_SET_UPDATED = 'edx.server.enterprise-catalog.highlight-set-lifecycle.updated'

    AI_CURATIONS_TASK_TRIGGERED = 'edx.server.enterprise-catalog.ai-curations.task.triggered'
    AI_CURATIONS_TASK_COMPLETED = 'edx.server.enterprise-catalog.ai-curations.task.completed'
    AI_CURATIONS_RESULTS_FOUND = 'edx.server.enterprise-catalog.ai-curations.results-found'
    AI_CURATIONS_RESULTS_NOT_FOUND = 'edx.server.enterprise-catalog.ai-curations.results-not-found'
