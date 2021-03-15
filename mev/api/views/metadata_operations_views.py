from functools import reduce

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.exceptions import ValidationError

from api.serializers.observation_set import ObservationSetSerializer
from api.serializers.feature_set import FeatureSetSerializer
from api.data_structures import ObservationSet, FeatureSet


class MetadataMixin(object):

    SETS = 'sets'
    SET_TYPE = 'set_type'

    serializer_choices = {
        'observation': ObservationSetSerializer,
        'feature': FeatureSetSerializer
    }
    elementset_choices = {
        'observation': ObservationSet,
        'feature': FeatureSet
    }

    def get_serializer(self, set_type):
        try:
            return self.serializer_choices[set_type]
        except KeyError as ex:
            raise ValidationError({
                self.SET_TYPE:'This must be one of: {s}.'.format(
                    s=','.join(self.serializer_choices.keys()))
                })

    def prep(self, request):
        required_keys = [self.SETS, self.SET_TYPE]        
        all_args_present = all([x in request.data.keys() for x in required_keys])
        if all_args_present:
            sets = request.data[self.SETS]
            if type(sets) is list:
                element_set_list = []
                serializer = self.get_serializer(request.data[self.SET_TYPE])
                for s in sets:
                    try:
                        element_set_list.append(serializer(data=s).get_instance())
                    except Exception as ex:
                        raise Response({
                            'error':'Error occurred when parsing'
                        }, status=status.HTTP_400_BAD_REQUEST
                    )
                return element_set_list
            else:
                raise ValidationError({self.SETS: 'This key should'
                    ' reference list-like data.'
                })  
        else:
            raise ValidationError({'error': 'This endpoint requires the following'
                ' keys in the payload: {k}'.format(k=','.join(required_keys))
            })

class MetadataIntersectView(APIView, MetadataMixin):
    def post(self, request, *args, **kwargs):
        element_set_list = self.prep(request)
        r = reduce(lambda x,y: x.set_intersection(y), element_set_list)
        serializer = self.get_serializer(request.data[self.SET_TYPE])
        return Response(serializer(r).data)

class MetadataUnionView(APIView, MetadataMixin):
    def post(self, request, *args, **kwargs):
        element_set_list = self.prep(request)
        r = reduce(lambda x,y: x.set_union(y), element_set_list)
        serializer = self.get_serializer(request.data[self.SET_TYPE])
        return Response(serializer(r).data)