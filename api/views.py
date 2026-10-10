from pymongo.errors import PyMongoError, ServerSelectionTimeoutError
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .domain import DomainError, perform_action, read_state
from .serializers import ActionSerializer


def _state_response():
    state = read_state()
    state.pop("_id", None)
    state.pop("_rev", None)
    return state


@api_view(["GET"])
def state_view(request):
    try:
        return Response(_state_response())
    except (ServerSelectionTimeoutError, PyMongoError) as error:
        return Response({"message": "MongoDB is unavailable. Check MONGODB_URI and network access."}, status=503)


@api_view(["GET"])
def staff_view(request):
    try:
        return Response(read_state()["staff"])
    except PyMongoError:
        return Response({"message": "MongoDB is unavailable. Check MONGODB_URI and network access."}, status=503)


@api_view(["GET"])
def shifts_view(request):
    try:
        return Response(read_state()["shifts"])
    except PyMongoError:
        return Response({"message": "MongoDB is unavailable. Check MONGODB_URI and network access."}, status=503)


@api_view(["GET", "POST"])
def listings_view(request):
    if request.method == "POST":
        return _run_action(request, {**request.data, "action": "POST"})
    try:
        return Response(read_state()["listings"])
    except PyMongoError:
        return Response({"message": "MongoDB is unavailable. Check MONGODB_URI and network access."}, status=503)


@api_view(["GET"])
def history_view(request):
    try:
        return Response(read_state()["history"])
    except PyMongoError:
        return Response({"message": "MongoDB is unavailable. Check MONGODB_URI and network access."}, status=503)


@api_view(["POST"])
def action_view(request):
    return _run_action(request, request.data)


def _run_action(request, payload):
    serializer = ActionSerializer(data=payload)
    if not serializer.is_valid():
        return Response({"message": "Invalid action request.", "errors": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)
    data = serializer.validated_data
    try:
        result, error_status = perform_action(
            data["actor_id"], data["action"], shift_id=data.get("shift_id"), listing_id=data.get("listing_id")
        )
        return Response(result, status=error_status or status.HTTP_200_OK)
    except DomainError as error:
        payload = {"message": error.message}
        if error.violations:
            payload["violations"] = error.violations
        return Response(payload, status=error.status)
    except (ServerSelectionTimeoutError, PyMongoError):
        return Response({"message": "MongoDB is unavailable. Check MONGODB_URI and network access."}, status=503)


def listing_transition(action):
    @api_view(["POST"])
    def view(request, listing_id):
        return _run_action(request, {**request.data, "action": action, "listing_id": listing_id})
    return view
