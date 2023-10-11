import openstack

DEFAULT_LOAD_LIMIT = 80
cloud = openstack.connect()


def scheduler(metrics: dict, logger, **kwargs) -> list:
    """Chooses the most CPU-intensive instance away from overloaded node

    without any target for migration
    """
    logger.info("choosing subjects and targets")
    load_limit = kwargs.get("load_threshold", DEFAULT_LOAD_LIMIT)
    decisions = []
    if not metrics:
        return decisions
    node_load = metrics["nodes"]
    overloaded_nodes = node_load[node_load.value > load_limit]
    logger.info(f"nodes with load>{load_limit}: "
                f"{', '.join(overloaded_nodes.node)}")
    for node in overloaded_nodes.node:
        inst_load = metrics[node]["instance_load"]
        if len(inst_load) == 0:
            logger.warning(
                f"no load info for instances on overloaded node {node}!")
            continue
        max_load_instance_id = inst_load.iloc[
            inst_load.value.idxmax()
        ].instance_uuid
        max_load_instance = cloud.get_server(
            max_load_instance_id, all_projects=True)
        if max_load_instance.status == "ACTIVE":
            decisions.append((max_load_instance, None))
    logger.info(f"{len(decisions)} decisions to execute")
    return decisions
