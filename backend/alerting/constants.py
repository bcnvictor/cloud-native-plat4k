class EventType:
    APP_CREATED           = "app.created"
    APP_UPDATED           = "app.updated"
    APP_DELETED           = "app.deleted"
    APP_DEPLOYED          = "app.deployed"
    APP_ROLLBACK          = "app.rollback"
    APP_HEALTH_DEGRADED   = "app.health.degraded"
    APP_HEALTH_RECOVERED  = "app.health.recovered"
    APP_EXPOSE_CHANGED    = "app.expose.changed"
    CLUSTER_OFFLINE       = "cluster.offline"
    CLUSTER_ONLINE        = "cluster.online"
    GROUP_RENAMED         = "group.renamed"
    GROUP_MEMBER_ADDED    = "group.member.added"
    GROUP_MEMBER_REMOVED  = "group.member.removed"


CATEGORY_MAP: dict[str, list[str]] = {
    "app": [
        EventType.APP_CREATED,
        EventType.APP_UPDATED,
        EventType.APP_DELETED,
        EventType.APP_DEPLOYED,
        EventType.APP_ROLLBACK,
        EventType.APP_HEALTH_DEGRADED,
        EventType.APP_HEALTH_RECOVERED,
        EventType.APP_EXPOSE_CHANGED,
    ],
    "cluster": [
        EventType.CLUSTER_OFFLINE,
        EventType.CLUSTER_ONLINE,
    ],
    "group": [
        EventType.GROUP_RENAMED,
        EventType.GROUP_MEMBER_ADDED,
        EventType.GROUP_MEMBER_REMOVED,
    ],
}


def category_of(event_type: str) -> str:
    for cat, types in CATEGORY_MAP.items():
        if event_type in types:
            return cat
    return "app"
