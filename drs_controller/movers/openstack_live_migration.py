import datetime as dt
import time
import openstack
DEFAULT_MIGRATION_TIMEOUT = 180
DEFAULT_MIGRATION_POLLING_INTERVAL = 5

cloud = openstack.connect()


def mover(decisions: list, logger, **kwargs) -> None:
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
        logger.info(f"requesting migration for server {instance.id}")
        cloud.compute.live_migrate_server(
            instance, host=target, block_migration="auto"
        )
        start = dt.datetime.now()
        while dt.datetime.now() - start < migration_timeout:
            time.sleep(migration_polling_interval)
            logger.info(f"polling server {instance.id}")
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
                            f"to node {instance.compute_host}")
                break
            # TODO: check instance migrations, could be migration failed
            # and instance left on source, no need to wait until timeout
        else:
            failed.append(f"failed to migrate server {instance.id} within time")
            logger.error(f"failed to migrate server {instance.id} within time")
    if failed:
        logger.error("FAILED MIGRATIONS: " + "; ".join(failed))
