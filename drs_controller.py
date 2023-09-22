import datetime as dt
import time
import typing

import kopf
import openstack
import prometheus_api_client as pc
import pykube as pk

DEFAULT_LOAD_LIMIT = 30
DEFAULT_NODE_METRIC = "node_load5"
DEFAULT_INSTANCE_METRIC = "libvirt_domain_info_cpu_time_seconds:rate5m"
DEFAULT_MIGRATION_TIMEOUT = 180
DEFAULT_MIGRATION_POLLING_INTERVAL = 5
PROMETHEUS_HOST = "http://prometheus-server.stacklight"

prom = pc.PrometheusConnect(url=PROMETHEUS_HOST, disable_ssl=True)
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
    # FIXME: can node_metrics be empty?
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
        # when metrics are absent
        if instance_load:
            instance_load = pc.MetricSnapshotDataFrame(instance_load)
        metrics[node]["instance_load"] = instance_load
        metrics[node]["instances"] = list(
            cloud.compute.servers(host=node, all_projects=True)
        )
        logger.info(f"collected instance list for node {node}")
    logger.info(f"got {len(metrics['nodes'])} cmp node metrics")
    return metrics


def poc_scheduler(metrics: dict, logger, **kwargs) -> typing.Any:
    """Chooses the most CPU-intensive instance away from overloaded node

    without any target for migration
    """
    logger.info("choosing subjects and targets")
    load_limit = kwargs.get("load_threshold", DEFAULT_LOAD_LIMIT)
    node_load = metrics["nodes"]
    overloaded_nodes = node_load[node_load.value > load_limit]
    logger.info(f"overloaded nodes: {list(overloaded_nodes.node)}")
    decisions = []
    for node in overloaded_nodes.node:
        inst_load = metrics[node]["instance_load"]
        if len(inst_load) == 0:
            logger.info(f"no load info for instances on {node}")
            continue
        max_load_instance_id = inst_load.iloc[
            inst_load.value.idxmax()
        ].instance_uuid
        max_load_instance = [
            i
            for i in metrics[node]["instances"]
            if i.id == max_load_instance_id
        ][0]
        if max_load_instance.status == "ACTIVE":
            decisions.append((max_load_instance, None))
    logger.info(f"{len(decisions)} decisions to execute")
    return decisions


def poc_mover(decisions, logger, **kwargs) -> None:
    """Live-migrates instances to targets"""
    migration_timeout = dt.timedelta(
        seconds=kwargs.get("migration_timeout", DEFAULT_MIGRATION_TIMEOUT)
    )
    migration_polling_interval = kwargs.get("migration_polling_interval",
                                            DEFAULT_MIGRATION_POLLING_INTERVAL)
    logger.info("execiting decisions")
    # TODO: parallelize
    failed = []
    for d in decisions:
        instance, target = d
        source_host = instance.compute_host
        cloud.compute.live_migrate_server(
            instance, host=target, block_migration="auto"
        )
        logger.info("requested migration for server", instance.id)
        start = dt.datetime.now()
        while dt.datetime.now() - start < migration_timeout:
            time.sleep(migration_polling_interval)
            logger.info("polling server", instance.id)
            instance = cloud.get_server(instance.id, all_projects=True)
            if instance.status == "ERROR":
                failed.append(f"failed to migrate server {instance.id}")
                logger.error(f"server {instance.id} went to error")
                break
            if (
                instance.status == "ACTIVE"
                and instance.compute_host != source_host
            ):
                logger.info(f"server {instance.id} successfully migrated "
                            "to node {instance.compute_host}")
                break
            # TODO: check instance migrations, could be migration failed
            # and instance left on source, no need to wait until timeout
        else:
            failed.append(f"failed to migrate server {instance.id} within time")
            logger.error(f"failed to migrate server {instance.id} within time")
    if failed:
        logger.error("FAILED MIGRATIONS: " + "; ".join(failed))


# TODO: replace with proper plugin system (like stevedore)
METHOD_REGISTRY = {
    "collectors": {"poc": poc_collector},
    "schedulers": {"poc": poc_scheduler},
    "movers": {"poc": poc_mover},
}
