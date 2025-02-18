import os
import copy
import random
import uuid
import unittest
import unittest.mock as mock

from django.contrib.auth import get_user_model
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from rest_framework.exceptions import ValidationError

from resource_types import RESOURCE_MAPPING, \
    DB_RESOURCE_STRING_TO_HUMAN_READABLE, \
    GeneralResource, \
    AnnotationTable, \
    WILDCARD, \
    DataResource
from api.models import Resource, \
    Workspace, \
    ResourceMetadata, \
    ExecutedOperation, \
    WorkspaceExecutedOperation, \
    Operation, \
    OperationResource
from api.serializers.resource_metadata import ResourceMetadataSerializer
from api.utilities.resource_utilities import move_resource_to_final_location, \
    get_resource_view, \
    validate_resource, \
    handle_valid_resource, \
    handle_invalid_resource, \
    check_extension, \
    add_metadata_to_resource, \
    get_resource_by_pk, \
    write_resource
from api.utilities.operations import read_operation_json, \
    check_for_resource_operations
from api.exceptions import NoResourceFoundException
from api.tests.base import BaseAPITestCase
from api.tests import test_settings

BASE_TESTDIR = os.path.dirname(__file__)
TESTDIR = os.path.join(BASE_TESTDIR, 'operation_test_files')
VAL_TESTDIR = os.path.join(BASE_TESTDIR, 'resource_validation_test_files')

class TestResourceUtilities(BaseAPITestCase):
    '''
    Tests the functions contained in the api.utilities.resource_utilities
    module.
    '''
    def setUp(self):
        self.establish_clients()
        

    def test_get_resource_by_pk_works_for_all_resources(self):
        '''
        We use the api.utilities.resource_utilities.get_resource_by_pk
        function to check for the existence of all children of the 
        AbstractResource class. Test that it all works as expected.
        '''
        with self.assertRaises(NoResourceFoundException):
            get_resource_by_pk(uuid.uuid4())

        r = Resource.objects.all()
        r = r[0]
        r2 = get_resource_by_pk(r.pk)
        self.assertEqual(r,r2)

        ops = Operation.objects.all()
        op = ops[0]
        r3 = OperationResource.objects.create(
            operation = op,
            input_field = 'foo',
            name = 'foo.txt',
            resource_type = 'MTX'
        )
        r4 = get_resource_by_pk(r3.pk)
        self.assertEqual(r3,r4)

    @mock.patch('resource_types.RESOURCE_MAPPING')
    @mock.patch('api.utilities.resource_utilities.get_storage_backend')
    def test_resource_preview_for_valid_resource_type(self, mock_get_storage_backend, mock_resource_mapping):
        '''
        Tests that a proper preview dict is returned.  Mocks out the 
        method that does the reading of the resource path.
        '''
        all_resources = Resource.objects.all()
        resource = None
        for r in all_resources:
            if r.resource_type:
                resource = r
                break
        if not resource:
            raise ImproperlyConfigured('Need at least one resource with'
                ' a specified resource_type to run this test.'
            )

        expected_dict = {'a': 1, 'b':2}

        class mock_resource_type_class(object):
            def get_contents(self, path, query_params={}):
                return expected_dict

        mock_resource_mapping.__getitem__.return_value = mock_resource_type_class
        mock_storage_backend = mock.MagicMock()
        mock_storage_backend.get_local_resource_path.return_value = '/foo'
        mock_get_storage_backend.return_value = mock_storage_backend
        preview_dict = get_resource_view(r)
        self.assertDictEqual(expected_dict, preview_dict)


    def test_resource_preview_for_null_resource_type(self):
        '''
        Tests that a proper preview dict is returned.  Mocks out the 
        method that does the reading of the resource path.
        '''
        all_resources = Resource.objects.all()
        resource = None
        for r in all_resources:
            if r.resource_type is None:
                resource = r
                break
        if not resource:
            raise ImproperlyConfigured('Need at least one resource without'
                ' a specified resource_type to run this test.'
            )

        preview_dict = get_resource_view(r)
        self.assertIsNone(preview_dict)
        
    @mock.patch('api.utilities.resource_utilities.get_contents')
    @mock.patch('api.utilities.resource_utilities.get_storage_backend')
    def test_resource_preview_for_general_type_does_not_pull_file(self, 
        mock_get_storage_backend,
        mock_get_contents):
        '''
        If the resource type is such that we cannot generate a preview (e.g.
        for a general file type), then check that we don't bother to pull
        the resource to the local cache
        '''
        all_resources = Resource.objects.all()
        resource = all_resources[0]
        resource.resource_type = WILDCARD

        mock_storage_backend = mock.MagicMock()
        mock_get_storage_backend.return_value = mock_storage_backend

        preview_dict = get_resource_view(resource)
        self.assertIsNone(preview_dict)
        mock_storage_backend.get_local_resource_path.assert_not_called()
        mock_get_contents.assert_not_called()

    @mock.patch('api.utilities.resource_utilities.get_resource_type_instance')
    @mock.patch('api.utilities.resource_utilities.handle_invalid_resource')
    @mock.patch('api.utilities.resource_utilities.get_storage_backend')
    def test_invalid_handler_called(self, mock_get_storage_backend, \
            mock_handle_invalid_resource, mock_get_resource_type_instance):
        '''
        Here we test that a failure to validate the resource calls the proper
        handler function.
        '''
        all_resources = Resource.objects.all()
        unset_resources = []
        for r in all_resources:
            if not r.resource_type:
                unset_resources.append(r)
        
        if len(unset_resources) == 0:
            raise ImproperlyConfigured('Need at least one'
                ' Resource without a type to test properly.'
            )

        unset_resource = unset_resources[0]

        mock_resource_class_instance = mock.MagicMock()
        mock_resource_class_instance.validate_type.return_value = (False, 'some string')
        mock_get_resource_type_instance.return_value = mock_resource_class_instance
        
        mock_storage_backend = mock.MagicMock()
        mock_storage_backend.get_local_resource_path.return_value = 'foo'
        mock_get_storage_backend.return_value = mock_storage_backend

        validate_resource(unset_resource, 'MTX')

        mock_handle_invalid_resource.assert_called()


    @mock.patch('api.utilities.resource_utilities.get_resource_type_instance')
    @mock.patch('api.utilities.resource_utilities.handle_valid_resource')
    @mock.patch('api.utilities.resource_utilities.get_storage_backend')
    def test_proper_invalid_handler_called(self, mock_get_storage_backend, mock_handle_valid_resource, mock_get_resource_type_instance):
        '''
        Here we test that a successful validation calls the proper
        handler function.
        '''
        all_resources = Resource.objects.all()
        unset_resources = []
        for r in all_resources:
            if not r.resource_type:
                unset_resources.append(r)
        
        if len(unset_resources) == 0:
            raise ImproperlyConfigured('Need at least one'
                ' Resource without a type to test properly.'
            )

        unset_resource = unset_resources[0]

        mock_resource_class_instance = mock.MagicMock()
        mock_resource_class_instance.validate_type.return_value = (True, 'some string')
        mock_get_resource_type_instance.return_value = mock_resource_class_instance

        validate_resource(unset_resource, 'MTX')

        mock_handle_valid_resource.assert_called()

    def test_unset_resource_type_does_not_change_if_validation_fails(self):
        '''
        If we had previously validated a resource successfully, requesting
        a change that fails validation results in NO change to the resource_type
        attribute
        '''
        all_resources = Resource.objects.all()
        unset_resources = []
        for r in all_resources:
            if not r.resource_type:
                unset_resources.append(r)
        
        if len(unset_resources) == 0:
            raise ImproperlyConfigured('Need at least one'
                ' Resource without a type to test properly.'
            )

        unset_resource = unset_resources[0]

        handle_invalid_resource(unset_resource, 'MTX')
        self.assertIsNone(unset_resource.resource_type)

    def test_resource_type_does_not_change_if_validation_fails(self):
        '''
        If we had previously validated a resource successfully, requesting
        a change that fails validation results in NO change to the resource_type
        attribute
        '''
        all_resources = Resource.objects.all()
        set_resources = []
        for r in all_resources:
            if r.resource_type:
                set_resources.append(r)
        
        if len(set_resources) == 0:
            raise ImproperlyConfigured('Need at least one'
                ' Resource with a type to test properly.'
            )

        resource = set_resources[0]
        original_type = resource.resource_type
        other_type = original_type
        while other_type == original_type:
            other_type = random.choice(list(RESOURCE_MAPPING.keys()))
        handle_invalid_resource(resource, other_type)

        self.assertTrue(resource.resource_type == original_type)
        self.assertTrue(resource.status.startswith(Resource.REVERTED.format(
            requested_resource_type=DB_RESOURCE_STRING_TO_HUMAN_READABLE[other_type],
            original_resource_type = DB_RESOURCE_STRING_TO_HUMAN_READABLE[original_type])
        ))

    @mock.patch.dict('api.utilities.resource_utilities.DB_RESOURCE_STRING_TO_HUMAN_READABLE', \
        {'foo_type': 'Table'})
    @mock.patch('api.utilities.resource_utilities.extension_is_consistent_with_type')
    @mock.patch('api.utilities.resource_utilities.get_acceptable_extensions')
    def test_inconsistent_file_extension_sets_status(self,
        mock_get_acceptable_extensions,
        mock_extension_is_consistent_with_type):
        '''
        This tests the case where a user selects a resource type but the
        file does not have a name that is consistent with that type. We need
        to enforce consistent extensions so we know how to try parsing files.
        For instance, a name like "file.txt" does not help us, and we do not want
        to try all different parsers.
        '''
        mock_extension_is_consistent_with_type.return_value = False
        mock_get_acceptable_extensions.return_value = ['tsv', 'csv', 'abc']
        requested_type = 'foo_type'
        human_readable_type = 'Table'
        resource = Resource.objects.all()[0]
        check_extension(resource, requested_type)
        expected_status = Resource.UNKNOWN_EXTENSION_ERROR.format(
            readable_resource_type = human_readable_type,
            filename = resource.name,
            extensions_csv = 'tsv,csv,abc'
        )
        self.assertEqual(resource.status, expected_status)

    @mock.patch('api.utilities.operations.get_operation_instance_data')
    def test_check_for_resource_operations_case1(self, mock_get_operation_instance_data):
        '''
        When removing a Resource from a Workspace, we need to ensure
        we are not removing a file that has been used in one or more 
        ExecutedOperations.

        Below, we check where a file HAS been used and show that the 
        function returns True
        '''
        # need to create an ExecutedOperation that is based on a known
        # Operation and part of an existing workspace. Also need to ensure
        # that there is a Resource that is being used in that Workspace

        all_workspaces = Workspace.objects.all()
        workspace_with_resource = None
        for w in all_workspaces:
            if len(w.resources.all()) > 0:
                workspace_with_resource = w
        if workspace_with_resource is None:
            raise ImproperlyConfigured('Need at least one Workspace that has'
                 ' at least a single Resource.'
            )

        ops = Operation.objects.all()
        if len(ops) > 0:
            op = ops[0]
        else:
            raise ImproperlyConfigured('Need at least one Operation'
                ' to use for this test'
            )
        
        f = os.path.join(
            TESTDIR,
            'valid_workspace_operation.json'
        )
        op_data = read_operation_json(f)
        mock_get_operation_instance_data.return_value = op_data
        executed_op_pk = uuid.uuid4()
        # the op_data we get from above has two outputs, one of which
        # is a DataResource. Just to be sure everything is consistent
        # between the spec and our mocked inputs below, we do this assert:
        input_keyset = list(op_data['inputs'].keys())
        self.assertCountEqual(input_keyset, ['count_matrix','p_val'])

        mock_used_resource = workspace_with_resource.resources.all()[0]
        mock_validated_inputs = {
            'count_matrix': str(mock_used_resource.pk), 
            'p_val': 0.01
        }
        ex_op = WorkspaceExecutedOperation.objects.create(
            id=executed_op_pk,
            owner = self.regular_user_1, 
            workspace = workspace_with_resource,
            job_name = 'abc',
            inputs = mock_validated_inputs,
            outputs = {},
            operation = op,
            mode = op_data['mode'],
            status = ExecutedOperation.SUBMITTED
        )
        was_used = check_for_resource_operations(mock_used_resource, workspace_with_resource)
        self.assertTrue(was_used)


    @mock.patch('api.utilities.operations.get_operation_instance_data')
    def test_check_for_resource_operations_case2(self, mock_get_operation_instance_data):
        '''
        When removing a Resource from a Workspace, we need to ensure
        we are not removing a file that has been used in one or more 
        ExecutedOperations.

        Below, we check where a file HAS NOT been used and show that the 
        function returns False
        '''
        # need to create an ExecutedOperation that is based on a known
        # Operation and part of an existing workspace. Also need to ensure
        # that there is a Resource that is being used in that Workspace

        all_workspaces = Workspace.objects.all()
        workspace_with_resource = None
        for w in all_workspaces:
            if len(w.resources.all()) > 0:
                workspace_with_resource = w
        if workspace_with_resource is None:
            raise ImproperlyConfigured('Need at least one Workspace that has'
                 ' at least a single Resource.'
            )

        ops = Operation.objects.all()
        if len(ops) > 0:
            op = ops[0]
        else:
            raise ImproperlyConfigured('Need at least one Operation'
                ' to use for this test'
            )
        
        f = os.path.join(
            TESTDIR,
            'simple_workspace_op_test.json'
        )
        op_data = read_operation_json(f)
        mock_get_operation_instance_data.return_value = op_data
        executed_op_pk = uuid.uuid4()
        # the op_data we get from above has two outputs, one of which
        # is a DataResource. Just to be sure everything is consistent
        # between the spec and our mocked inputs below, we do this assert:
        input_keyset = list(op_data['inputs'].keys())
        self.assertCountEqual(input_keyset, ['some_string'])

        mock_used_resource = workspace_with_resource.resources.all()[0]
        mock_validated_inputs = {
            'some_string': 'xyz'
        }
        ex_op = WorkspaceExecutedOperation.objects.create(
            id=executed_op_pk,
            owner = self.regular_user_1,
            workspace=workspace_with_resource,
            job_name = 'abc',
            inputs = mock_validated_inputs,
            outputs = {},
            operation = op,
            mode = op_data['mode'],
            status = ExecutedOperation.SUBMITTED
        )
        was_used = check_for_resource_operations(mock_used_resource, workspace_with_resource)
        self.assertFalse(was_used)


    @mock.patch('api.utilities.resource_utilities.get_resource_type_instance')
    @mock.patch('api.utilities.resource_utilities.handle_valid_resource')
    @mock.patch('api.utilities.resource_utilities.get_storage_backend')
    @mock.patch('api.utilities.resource_utilities.check_extension')
    def test_proper_steps_taken_with_wildcard_resource(self, mock_check_extension, \
        mock_get_storage_backend, \
        mock_handle_valid_resource, \
        mock_get_resource_type_instance):
        '''
        Here we test that a esource type with a "wildcard" type goes through the proper
        steps. That is, we should skip the validation, etc.
        '''
        all_resources = Resource.objects.all()
        r = all_resources[0]

        mock_check_extension.return_value = True
        g = GeneralResource()
        mock_get_resource_type_instance.return_value = g

        validate_resource(r, WILDCARD)

        mock_handle_valid_resource.assert_called()
        mock_get_storage_backend.assert_not_called()

    def test_check_extension_for_wildcard_resource(self):
        '''
        Checks that the extension checking method just returns True
        since we are trying to set to a wildcard/generic resource type
        '''
        all_resources = Resource.objects.all()
        r = all_resources[0]
        self.assertTrue(check_extension(r, WILDCARD))

    @mock.patch('api.utilities.resource_utilities.move_resource_to_final_location')
    def test_check_handle_valid_resource_for_wildcard_type(self, mock_move_resource_to_final_location):
        '''
        Check that we do the proper things when we handle the apparently 
        "valid" resource. For wildcard types, they are trivially valid, but
        we need to check that we are not calling any methods that wouldn't 
        make sense in this context.
        '''
        mock_move_resource_to_final_location.return_value = '/a/b/c.txt'

        all_resources = Resource.objects.all()
        r = all_resources[0]
        g = GeneralResource()
        handle_valid_resource(r, g, WILDCARD)

        self.assertEqual(r.path, '/a/b/c.txt')

        metadata = ResourceMetadata.objects.get(resource=r)
        self.assertIsNone(getattr(metadata, DataResource.PARENT_OP))
        self.assertIsNone(getattr(metadata, DataResource.FEATURE_SET))
        self.assertIsNone(getattr(metadata, DataResource.OBSERVATION_SET))
        self.assertEqual(getattr(metadata, DataResource.RESOURCE), r)

    @mock.patch('api.utilities.resource_utilities.move_resource_to_final_location')
    @mock.patch('api.utilities.resource_utilities.get_storage_backend')
    def test_check_handles_metadata_error(self, mock_get_storage_backend, mock_move_resource_to_final_location):
        '''
        Some resources can be properly validated but yet fail when it comes to creating metadata.
        An example of this is where an annotation table has a numeric value among other string values.
        The table validates, as it's properly formatted, but the all-numeric value is not compliant
        with our StringAttribute. Hence, an exception is raised when we are trying to attach
        metadata to the resource. We want to ensure that error is communicated to the user.
        '''
        test_resources_dir = os.path.dirname(__file__)
        test_resources_dir = os.path.join(test_resources_dir, 'resource_validation_test_files')
        p = os.path.join(test_resources_dir, 'test_annotation_with_noncompliant_str.tsv')

        mock_storage_backend = mock.MagicMock()
        mock_storage_backend.get_local_resource_path.return_value = p
        mock_get_storage_backend.return_value = mock_storage_backend

        all_resources = Resource.objects.all()
        r = all_resources[0]
        resource_class_instance = AnnotationTable()
        mock_save = mock.MagicMock()
        mock_save.return_value = (p,r.name)
        resource_class_instance.save_in_standardized_format = mock_save
        handle_valid_resource(r, resource_class_instance, 'ANN')
        self.assertTrue('123' in r.status)
        self.assertIsNone(r.resource_type)


    def test_add_metadata(self):
        '''
        Test that we gracefully handle updates
        when associating metadata with a resource.

        Have a case where we update and we create a new ResourceMetadata
        '''
        # create a new Resource
        r = Resource.objects.create(
            name='foo.txt'
        )
        rm = ResourceMetadata.objects.create(
            resource=r
        )
        rm_pk = rm.pk

        mock_obs_set = {
            'multiple': True,
            'elements': [
                {
                    'id': 'sampleA'
                },
                {
                    'id': 'sampleB'
                }
            ]
        }
        add_metadata_to_resource(
            r, 
            {DataResource.OBSERVATION_SET:mock_obs_set}
        )

        # query again, see that it was updated
        rm2 = ResourceMetadata.objects.get(pk=rm_pk)
        expected_obs_set = copy.deepcopy(mock_obs_set)
        elements = expected_obs_set['elements']
        for el in elements:
            el.update({'attributes': {}})
        self.assertEqual(rm2.observation_set['multiple'], mock_obs_set['multiple'])
        self.assertCountEqual(rm2.observation_set['elements'], elements)

        # OK, now get a Resource that does not already have metadata
        # associated with it:        
        r = Resource.objects.create(
            name='bar.txt'
        )
        with self.assertRaises(ResourceMetadata.DoesNotExist):
            ResourceMetadata.objects.get(resource=r)
        add_metadata_to_resource(
            r, 
            {DataResource.OBSERVATION_SET:mock_obs_set}
        )

        # query again, see that it was updated
        rm3 = ResourceMetadata.objects.get(pk=rm_pk)
        expected_obs_set = copy.deepcopy(mock_obs_set)
        elements = expected_obs_set['elements']
        for el in elements:
            el.update({'attributes': {}})
        self.assertEqual(rm3.observation_set['multiple'], mock_obs_set['multiple'])
        self.assertCountEqual(rm3.observation_set['elements'], elements)
        
    @mock.patch('api.utilities.resource_utilities.ResourceMetadataSerializer')
    def test_add_metadata_case2(self, mock_serializer_cls):
        '''
        Test that we gracefully handle updates and save failures
        when associating metadata with a resource.

        Inspired by a runtime failure where the FeatureSet was too
        large for the database field
        '''
        # create a new Resource
        r = Resource.objects.create(
            name='foo.txt'
        )
        # ensure it has no associated metadata
        with self.assertRaises(ResourceMetadata.DoesNotExist):
            ResourceMetadata.objects.get(resource=r)

        # create a mock object that will raise an exception
        from django.db.utils import OperationalError
        mock_serializer1 = mock.MagicMock()
        mock_serializer2 = mock.MagicMock()
        mock_serializer1.is_valid.return_value = True
        mock_serializer1.save.side_effect = OperationalError
        mock_serializer_cls.side_effect = [mock_serializer1, mock_serializer2]
        add_metadata_to_resource(
            r, 
            {}
        )
        mock_serializer2.save.assert_called()

    @mock.patch('api.utilities.resource_utilities.make_local_directory')
    @mock.patch('api.utilities.resource_utilities.os')
    def test_resource_write_dir_fails(self, mock_os, mock_make_local_directory):
        '''
        Tests the case where we fail to create a directory
        to write into. Check that this is handled appropriately.
        '''
        mock_os.path.dirname.return_value = '/some/dir'
        mock_os.path.exists.return_value = False
        mock_make_local_directory.side_effect = Exception('something bad happened!')
        with self.assertRaises(Exception):
            write_resource('some content', '')

    @mock.patch('api.utilities.resource_utilities.make_local_directory')
    def test_resource_write_works_case1(self, mock_make_local_directory):
        '''
        Tests that we do, in fact, write correctly.
        Here, we use the /tmp folder, which exists
        '''
        self.assertTrue(os.path.exists('/tmp'))
        destination = '/tmp/some_file.txt'
        content = 'some content'
        write_resource(content, destination)
        self.assertTrue(os.path.exists(destination))
        read_content = open(destination).read()
        self.assertEqual(read_content, content)
        mock_make_local_directory.assert_not_called()
        # cleanup
        os.remove(destination)

    def test_resource_write_works_case2(self):
        '''
        Tests that we do, in fact, write correctly.
        Here, we write in a folder which doesn't already exist
        '''
        self.assertFalse(os.path.exists('/tmp/foo'))
        destination = '/tmp/foo/some_file.txt'
        content = 'some content'
        write_resource(content, destination)
        self.assertTrue(os.path.exists(destination))
        read_content = open(destination).read()
        self.assertEqual(read_content, content)
        # cleanup
        os.remove(destination)
        os.removedirs('/tmp/foo')

    def test_resource_write_only_writes_string(self):
        '''
        Tests that this function only handles strings.
        Below, we try to have it write a dict and that 
        should not work
        '''
        destination = '/tmp/some_file.txt'
        content = {'some_key': 'some_val'}
        with self.assertRaises(AssertionError):
            write_resource(content, destination)


    @mock.patch('api.utilities.resource_utilities.move_resource_to_final_location')
    @mock.patch('api.utilities.resource_utilities.get_storage_backend')
    def test_metadata_when_type_changed(self, mock_get_storage_backend, mock_move_resource_to_final_location):
        '''
        Checks that the update of resource metadata is updated. Related to a bug where
        a file was initially set to a general type (and thus the metadata was effectively empty).
        After trying to validate it as an annotation type, it was raising json serializer errors.
        '''
        resource_path = os.path.join(VAL_TESTDIR, 'test_annotation_valid.tsv')
        mock_move_resource_to_final_location.return_value = resource_path

        mock_f = mock.MagicMock()
        mock_f.get_local_resource_path.return_value = resource_path
        mock_get_storage_backend.return_value = mock_f

        r = Resource.objects.create(
            name = 'test_annotation_valid.tsv',
            owner = self.regular_user_1,
            is_active=True,
            path = resource_path,
            resource_type = '*'
        )
        validate_resource(r, '*')
        rm = ResourceMetadata.objects.get(resource=r)
        self.assertTrue(rm.observation_set is None)
        validate_resource(r, 'ANN')
        rm = ResourceMetadata.objects.get(resource=r)
        self.assertFalse(rm.observation_set is None)

    @mock.patch('api.utilities.resource_utilities.move_resource_to_final_location')
    @mock.patch('api.utilities.resource_utilities.get_storage_backend')
    def test_metadata_when_type_changed_case2(self, mock_get_storage_backend, mock_move_resource_to_final_location):
        resource_path = os.path.join(VAL_TESTDIR, 'test_matrix.tsv')
        mock_move_resource_to_final_location.return_value = resource_path

        mock_f = mock.MagicMock()
        mock_f.get_local_resource_path.return_value = resource_path
        mock_get_storage_backend.return_value = mock_f
        
        r = Resource.objects.create(
            name = 'test_annotation_valid.tsv',
            owner = self.regular_user_1,
            is_active=True,
            path = resource_path,
            resource_type = '*'
        )
        validate_resource(r, '*')
        rm = ResourceMetadata.objects.get(resource=r)
        self.assertTrue(rm.observation_set is None)
        r.save()
        validate_resource(r, 'MTX')
        rm = ResourceMetadata.objects.get(resource=r)
        obs_set = rm.observation_set
        samples = [x['id'] for x in obs_set['elements']]
        expected = ['SW1_Control','SW2_Control','SW3_Control','SW4_Treated','SW5_Treated','SW6_Treated']
        self.assertCountEqual(samples, expected)