import prometheus_api_client as pc

DEFAULT_NODE_METRIC = "node_load5"
DEFAULT_INSTANCE_METRIC = "libvirt_domain_info_cpu_time_seconds:rate5m"
PROMETHEUS_HOST = "http://prometheus-server.stacklight"
prom = pc.PrometheusConnect(url=PROMETHEUS_HOST, disable_ssl=True)

def collector(logger, **kwargs) -> dict:
    logger.info("collecting data")
    node_metric = kwargs.get("node_metric", DEFAULT_NODE_METRIC)
    instance_metric = kwargs.get("instance_metric", DEFAULT_INSTANCE_METRIC)
    node_metrics = prom.custom_query(
        f"{node_metric} and on(node) "
        f"label_replace("
        f'kube_node_labels{{label_openstack_compute_node="enabled"}},'
        f'"node", "$1", "node", "(.*)")'
    )
    logger.info("collected compute node load")
    metrics = {}
    if not node_metrics:
        logger.warning("No node metric for {node_metric} available")
        return []
    metrics["nodes"] = pc.MetricSnapshotDataFrame(node_metrics)
    # TODO: get all instance load grouped by node in single call
    for node in metrics["nodes"].node:
        metrics[node] = {}
        instance_load = prom.get_current_metric_value(
            instance_metric,
            label_config={"node": node},
        )
        logger.info(f"collected instance load for node {node}")
        # NOTE: MetricSnapshotDataFrame fails if given empty list
        if instance_load:
            instance_load = pc.MetricSnapshotDataFrame(instance_load)
        metrics[node]["instance_load"] = instance_load
    logger.info(f"got {len(metrics['nodes'])} cmp node metrics")
    return metrics
