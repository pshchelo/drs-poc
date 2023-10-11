import time

import kopf
import pykube as pk
from stevedore import driver

k8s = pk.HTTPClient(pk.KubeConfig.from_env())


class DRSConfig(pk.objects.NamespacedAPIObject):
    version = "lcm.mirantis.com/v1alpha1"
    kind = "DRSConfig"
    endpoint = "drsconfigs"
    kopf_on_args = *version.split("/"), endpoint


# kopf.daemon kwargs
# ['stopped', 'logger', 'param', 'retry', 'started', 'runtime', 'memo',
#  'resource', 'patch', 'body', 'spec', 'meta', 'status', 'uid',
#  'name', 'namespace', 'labels', 'annotations']
@kopf.daemon(*DRSConfig.kopf_on_args)
def drs(stopped, logger, name, namespace, spec, **kwargs):
    logger.info("starting daemon")
    logger.debug(f"got kwargs {kwargs}")
    collector_opts = spec["collector"]
    scheduler_opts = spec["scheduler"]
    mover_opts = spec["mover"]
    try:
        collector = driver.DriverManager(
            namespace="drs_controller.collector",
            name=collector_opts.get("name"),
            invoke_on_load=False)
        scheduler = driver.DriverManager(
            namespace="drs_controller.scheduler",
            name=scheduler_opts.get("name"),
            invoke_on_load=False)
        mover = driver.DriverManager(
            namespace="drs_controller.mover",
            name=mover_opts.get("name"),
            invoke_on_load=False)
    except Exception as e:
        logger.error(f"Some drivers could not be loaded: {e}")
        raise kopf.TemporaryError

    while not stopped:
        spec = DRSConfig.objects(k8s).filter(
            namespace=namespace).get(
                name=name).obj['spec']
        reconcile_interval = spec["reconcileInterval"]
        metrics = collector.driver(logger=logger, **collector_opts)
        decision = scheduler.driver(metrics, logger=logger, **scheduler_opts)
        mover.driver(decision, logger=logger, **mover_opts)
        logger.info(f"sleeping for {reconcile_interval}")
        time.sleep(reconcile_interval)
