from rest_framework import serializers


class ApiStatusSerializer(serializers.Serializer):
    service = serializers.CharField()
    status = serializers.CharField()
    api_version = serializers.CharField()
