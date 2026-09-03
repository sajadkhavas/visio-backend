from drf_spectacular.utils import extend_schema
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from .serializers import ApiStatusSerializer


class ApiStatusView(APIView):
    authentication_classes: list[type] = []
    permission_classes = [AllowAny]

    @extend_schema(responses={200: ApiStatusSerializer})
    def get(self, request: Request) -> Response:
        del request
        return Response(
            {"service": "visio-backend", "status": "ok", "api_version": "v1"}
        )
