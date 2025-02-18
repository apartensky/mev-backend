import unittest
import unittest.mock as mock
import os
import json
import uuid

from django.core.exceptions import ImproperlyConfigured
from api.tests.base import BaseAPITestCase
from api.models import Workspace, \
    Resource, \
    ExecutedOperation, \
    WorkspaceExecutedOperation, \
    Operation

from api.converters.output_converters import LocalDockerOutputConverter

class ExecutedOperationOutputConverterTester(BaseAPITestCase):

    def setUp(self):
        self.establish_clients()

    @mock.patch('api.converters.output_converters.validate_and_store_resource')
    @mock.patch('api.converters.output_converters.ResourceMetadata')
    def test_dataresource_converts_properly(self, mock_resourcemetadata_model, mock_validate_and_store_resource):
        '''
        When a DataResource is created as part of an ExecutedOperation,
        the outputs give it as a path (or list of paths)

        The converter's job is to register that as a new file with the workspace
        and return the UUID of this new Resource
        '''
        mock_resource_metadata_obj = mock.MagicMock()
        mock_resourcemetadata_model.objects.get.return_value = mock_resource_metadata_obj

        # get the  initial counts on the database entities:
        all_user_resources = Resource.objects.filter(owner=self.regular_user_1)
        n0 = len(all_user_resources)
        all_user_workspaces = Workspace.objects.filter(owner=self.regular_user_1)
        if len(all_user_workspaces) < 1:
            raise ImproperlyConfigured('Need at least one Workspace for the regular user.')
        workspace = all_user_workspaces[0]
        workspace_resources = workspace.resources.all()
        w0 = len(workspace_resources)

        c = LocalDockerOutputConverter()
        job_id = str(uuid.uuid4())
        op = Operation.objects.all()[0]
        job_name = 'foo'
        executed_op = WorkspaceExecutedOperation.objects.create(
            id=job_id,
            workspace=workspace,
            owner=self.regular_user_1,
            inputs = {},
            operation = op,
            mode = '',
            job_name = job_name
        )
        output_spec = {
            'attribute_type': 'DataResource',
            'many': False,
            'resource_type': 'MTX'
        }
        c.convert_output(executed_op, workspace, output_spec, '/some/output/path.txt')

        mock_validate_and_store_resource.assert_called()
        mock_resourcemetadata_model.objects.get.assert_called()
        mock_resource_metadata_obj.save.assert_called()

        # query the Resources again:
        updated_all_user_resources = Resource.objects.filter(owner=self.regular_user_1)
        n1 = len(updated_all_user_resources)
        self.assertEqual(n1-n0, 1)
        updated_workspace_resources = workspace.resources.all()
        w1 = len(updated_workspace_resources)
        self.assertEqual(w1-w0, 1)

        expected_name = '{n}.path.txt'.format(n=job_name)
        r = Resource.objects.filter(name=expected_name )
        self.assertTrue(len(r) == 1)

        r = r[0]
        resource_workspaces = r.workspaces.all()
        self.assertTrue(workspace in resource_workspaces)



    @mock.patch('api.converters.output_converters.validate_and_store_resource')
    @mock.patch('api.converters.output_converters.ResourceMetadata')
    def test_dataresource_converts_properly_case2(self, mock_resourcemetadata_model, mock_validate_and_store_resource):
        '''
        When a DataResource is created as part of an ExecutedOperation,
        the outputs give it as a path (or list of paths)

        The converter's job is to register that as a new file with the workspace
        and return the UUID of this new Resource

        Here, we have a non-workspace Op, so we check that we only create a Resource
        but do not associate it with any Workspaces
        '''
        mock_resource_metadata_obj = mock.MagicMock()
        mock_resourcemetadata_model.objects.get.return_value = mock_resource_metadata_obj

        # get the initial counts on the database entities:
        all_user_resources = Resource.objects.filter(owner=self.regular_user_1)
        n0 = len(all_user_resources)
        all_user_workspaces = Workspace.objects.filter(owner=self.regular_user_1)
        if len(all_user_workspaces) < 1:
            raise ImproperlyConfigured('Need at least one Workspace for the regular user.')

        c = LocalDockerOutputConverter()
        job_id = str(uuid.uuid4())
        op = Operation.objects.all()[0]
        op.workspace_operation = False
        op.save()
        executed_op = ExecutedOperation.objects.create(
            id=job_id,
            owner=self.regular_user_1,
            inputs = {},
            operation = op,
            mode = ''
        )
        output_spec = {
            'attribute_type': 'DataResource',
            'many': False,
            'resource_type': 'MTX'
        }
        c.convert_output(executed_op, None, output_spec, '/some/output/path.txt')

        mock_validate_and_store_resource.assert_called()
        mock_resourcemetadata_model.objects.get.assert_called()
        mock_resource_metadata_obj.save.assert_called()

        # query the Resources again:
        updated_all_user_resources = Resource.objects.filter(owner=self.regular_user_1)
        n1 = len(updated_all_user_resources)
        self.assertEqual(n1-n0, 1)

        # since there was no job name, there is no prefix
        expected_name = 'path.txt'
        r = Resource.objects.filter(name=expected_name )
        self.assertTrue(len(r) == 1)

        r = r[0]
        resource_workspaces = r.workspaces.all()
        self.assertTrue(len(resource_workspaces) == 0)
    