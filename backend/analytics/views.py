from rest_framework.decorators import api_view
from rest_framework.response import Response

from cases.access import need
from . import runner


@api_view(["POST"])
def run(request):
    need(request.user, "manager")

    status, problem = runner.start(request.user, force=True)

    if problem:
        return Response({"detail": problem}, status=400)

    return Response(status)


@api_view(["POST"])
def refresh(request):
    need(request.user, "manager")

    force = bool(request.data.get("force", False))

    status, problem = runner.start(request.user, force=force)

    if problem:
        return Response({"detail": problem}, status=400)

    return Response(status)


@api_view(["GET"])
def status(request):
    need(request.user, "manager")

    current_status = runner.reconcile()
    alive = runner.worker_alive()

    return Response({
        **current_status,
        "worker": alive,
        "worker_alive": alive,
        "stale": runner.is_stale(current_status),
    })


@api_view(["GET"])
def results(request):
    need(request.user, "manager")
    return Response(runner.read_results())


@api_view(["POST"])
def cancel(request):
    need(request.user, "manager")
    return Response(runner.cancel())