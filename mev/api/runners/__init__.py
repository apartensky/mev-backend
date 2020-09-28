import logging

from .local_docker import LocalDockerRunner
from .remote_cromwell import RemoteCromwellRunner
from api.utilities.operations import get_operation_instance_data

logger = logging.getLogger(__name__)

AVAILABLE_RUN_MODES = [
    LocalDockerRunner.MODE,
    RemoteCromwellRunner.MODE
]

RUNNER_MAPPING = {
    LocalDockerRunner.MODE: LocalDockerRunner,
    RemoteCromwellRunner.MODE: RemoteCromwellRunner
}

def get_runner(mode):
    try:
        return RUNNER_MAPPING[mode]
    except KeyError as ex:
        logger.error('Requested an unknown run mode: {mode}'.format(
            mode=mode
        ))
        raise ex

def submit_job(executed_op, op_data, validated_inputs):
    '''
    Submits the job to the proper runner.

    `executed_op` is an instance of ExecutedOperation (database model)
    `op_data` is a dict parsed from an `Operation` spec (data structure, NOT db model)
    `validated_inputs` is a dict of inputs. Each key matches a key 
      from the `op_data` and the value is an instance of `UserOperationInput`
    '''
    runner_class = get_runner(op_data['mode'])
    runner = runner_class()
    runner.run(executed_op, op_data, validated_inputs)

def finalize_job(executed_op):
    '''
    Finalizes the job using the proper runner.

    `executed_op` is an instance of ExecutedOperation (database model)
    '''
    runner_class = get_runner(executed_op.mode)
    runner = runner_class()
    runner.finalize(executed_op)