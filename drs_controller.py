import time
import typing

import kopf
import openstack
import prometheus_api_client as pc
import pykube as pk

DEFAULT_LOAD_LIMIT = 30
# PROMETHHEUS_HOST = "http://prometheus-server.stacklight"
PROMETHHEUS_HOST = "http://10.172.1.105"
prom = pc.PrometheusConnect(url=PROMETHHEUS_HOST, disable_ssl=True)
cloud = openstack.connect()
k8s = pk.HTTPClient(pk.KubeConfig.from_env())

# kopf.daemon kwargs
# ['stopped', 'logger', 'param', 'retry', 'started', 'runtime', 'memo',
#  'resource', 'patch', 'body', 'spec', 'meta', 'status', 'uid',
#  'name', 'namespace', 'labels', 'annotations']


@kopf.daemon("drsconfigs")
def drs(stopped, logger, spec, **kwargs):
    logger.info("starting daemon")
    logger.debug(f"got kwargs {kwargs}")
    timeout = spec["timeout"]
    # TODO: replace with proper plugin system (like stevedore)
    collector_opts = spec["collector"]
    collector_func = METHOD_REGISTRY["collectors"].get(
        collector_opts.pop("name")
    )
    scheduler_opts = spec["scheduler"]
    scheduler_func = METHOD_REGISTRY["schedulers"].get(
        scheduler_opts.pop("name")
    )
    mover_opts = spec["mover"]
    mover_func = METHOD_REGISTRY["movers"].get(mover_opts.pop("name"))
    if not (collector_func and scheduler_func and mover_func):
        logger.error("Some functions could not be resolved")
        raise kopf.PermanentError

    while not stopped:
        metrics = collector_func(logger=logger, **collector_opts)
        decision = scheduler_func(metrics, logger=logger, **scheduler_opts)
        mover_func(decision, logger=logger, **mover_opts)
        logger.info(f"sleeping for {timeout}")
        time.sleep(timeout)


def poc_collector(logger, **kwargs) -> dict:
    logger.info("collecting data")
    logger.info(f"got kwargs {kwargs}")
    compute_nodes = [
        n.name
        for n in pk.Node.objects(k8s).filter(
            selector={"openstack-compute-node": "enabled"}
        )
    ]
    # TODO: check what limit is there for the size of node_str
    # node_str = "|".join(compute_nodes)
    # prom.target(f"node_load5{{node=~'{node_str}'}}")
    metrics = {}
    for node in compute_nodes:
        node_load = prom.get_current_metric_value(
            "node_load5", label_config={"node": node}
        )
        # NOTE: MetricSnapshotDataFrame fails if given empty list
        # when metrics are absent
        if node_load:
            node_load = pc.MetricSnapshotDataFrame(node_load)
        metrics[node] = {"node_load": node_load}
        metrics[node]["instances"] = list(
            cloud.compute.servers(host=node, all_projects=True)
        )
        # NOTE: MetricSnapshotDataFrame fails if given empty list
        # when metrics are absent
        instance_load = prom.get_current_metric_value(
            "libvirt_domain_info_cpu_time_seconds:rate5m",
            label_config={"node": node},
        )
        if instance_load:
            instance_load = pc.MetricSnapshotDataFrame(instance_load)
        metrics[node]["instance_load"] = instance_load
    logger.info(f"got {len(metrics)} cmp node metrics")
    return metrics


def poc_scheduler(metrics: dict, logger, **kwargs) -> typing.Any:
    logger.info("choosing target")
    logger.info(f"got kwargs {kwargs}")
    logger.info(f"got metrics {metrics}")
    # load_limit = kwargs.get("load_threshold", DEFAULT_LOAD_LIMIT)
    decisions = []
    return decisions


def poc_mover(decisions, logger, **kwargs) -> None:
    logger.info(f"got kwargs {kwargs}")
    logger.info("execiting decisions")
    # TODO: parallelize
    for d in decisions:
        instance, target = d
        # TODO: wait for finish
        cloud.compute.live_migrate_server(
            instance, host=target, block_migration="auto"
        )


# TODO: replace with proper plugin system (like stevedore)
METHOD_REGISTRY = {
    "collectors": {"poc": poc_collector},
    "schedulers": {"poc": poc_scheduler},
    "movers": {"poc": poc_mover},
}
