from ml.services.topic_clustering import TopicClusterIndex

_cluster_index = None

def get_cluster_index() -> TopicClusterIndex:
    global _cluster_index
    if _cluster_index is None:
        _cluster_index = TopicClusterIndex()
    return _cluster_index