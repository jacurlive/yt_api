from rest_framework import serializers


class VideoRequestSerializer(serializers.Serializer):
    url = serializers.URLField()
