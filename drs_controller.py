import time
import typing

import kopf
import openstack
from prometheus_api_client import PrometheusConnect

# PROMETHHEUS_HOST = "http://prometheus-server.stacklight"
PROMETHHEUS_HOST = "http://10.172.1.105"
prom = PrometheusConnect(url=PROMETHHEUS_HOST, disable_ssl=True)
cloud = openstack.connect()

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
        collector_opts.pop("name"))
    scheduler_opts = spec["scheduler"]
    scheduler_func = METHOD_REGISTRY["schedulers"].get(
        scheduler_opts.pop("name"))
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
    data = prom.all_metrics()
    logger.info(f"got {len(data)} data items")
    return data


def poc_scheduler(metrics, logger, **kwargs) -> typing.Any:
    logger.info("choosing target")
    logger.info(f"got kwargs {kwargs}")
    return None, None


def poc_mover(decision, logger, **kwargs) -> None:
    logger.info("moving victim to target")
    logger.info(f"got kwargs {kwargs}")


METHOD_REGISTRY = {
    "collectors": {"poc": poc_collector},
    "schedulers": {"poc": poc_scheduler},
    "movers": {"poc": poc_mover}
}
