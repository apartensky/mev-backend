import os
import logging

from api.utilities.resource_utilities import validate_and_store_resource
from api.data_structures.attributes import DataResourceAttribute
from api.models import Resource, ResourceMetadata

logger = logging.getLogger(__name__)

class BaseOutputConverter(object):

    def convert_output(self, executed_op, workspace, output_spec, output_val):
        '''
        Converts the output payload from an ExecutedOperation into something
        that WebMEV can work with.

        Note that the `workspace` arg can be None if the ExecutedOperation was
        not associated with any Workspace (As would be the case for an upload
        performed by a job runner)
        '''
        attribute_type = output_spec['attribute_type']
        if attribute_type == DataResourceAttribute.typename:
            # check if many
            # if many, deal with the list, otherwise, just a single path
            # if only a single output, place into a list so we can handle
            # both single and multiple outputs in the same loop
            if output_spec['many'] == False:
                output_paths = [output_val,]
            else:
                output_paths = output_val

            # get the type of the DataResource:
            resource_type = output_spec['resource_type']

            resource_uuids = []
            for p in output_paths:
                logger.info('Converting path at: {p} to a user-associated resource.'.format(
                    p = p
                ))
                # p is a path in the execution "sandbox" directory or bucket,
                # depending on the runner.
                # Create a new Resource and use the storage 
                # driver to send the file to its final location.

                # the "name"  of the file as the user will see it.
                if len(executed_op.job_name) > 0:
                    name = '{job_name}.{n}'.format(
                        job_name = str(executed_op.job_name),
                        n = os.path.basename(p)
                    )
                else:
                    name = os.path.basename(p)
                resource = self.create_resource(executed_op.owner, workspace, p, name)
                validate_and_store_resource(resource, resource_type)

                # add the info about the parent operation to the resource metadata
                rm = ResourceMetadata.objects.get(resource=resource)
                rm.parent_operation = executed_op
                rm.save()

                resource_uuids.append(str(resource.pk))
            # now return the resource UUID(s) consistent with the 
            # output (e.g. if multiple, return list)
            if output_spec['many'] == False:
                return resource_uuids[0]
            else:
                return resource_uuids
        else:
            return output_val
            
    def create_resource(self, owner, workspace, path, name):
        logger.info('From executed operation outputs, create'
            ' a resource at {p} with name {n}'.format(
                p = path,
                n = name
            )
        )
        resource_instance = Resource.objects.create(
            owner = owner,
            path = path,
            name = name
        )
        if workspace:
            resource_instance.workspaces.add(workspace)
        resource_instance.save()
        return resource_instance

        
class LocalOutputConverter(BaseOutputConverter):
    pass

class RemoteOutputConverter(BaseOutputConverter):
    pass

class LocalDockerOutputConverter(LocalOutputConverter):
    pass

class RemoteCromwellOutputConverter(RemoteOutputConverter):
    pass

