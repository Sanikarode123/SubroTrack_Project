from rest_framework.decorators import api_view
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from cases.access import need
from . import engine


@api_view(["POST"])
def ask(request):
    need(request.user, "manager", "employee")
    q = (request.data.get("question") or "").strip()
    if not q:
        raise ValidationError("Question is required.")
    try:
        return Response(engine.answer(request.user, q, request.data.get("case_id") or None))
    except engine.RagUnavailable as e:
        return Response({"detail": str(e)}, status=400)


@api_view(["POST"])
def reindex(request):
    need(request.user, "manager")
    try:
        return Response({"cases_indexed": engine.reindex_all()})
    except engine.RagUnavailable as e:
        return Response({"detail": str(e)}, status=400)


@api_view(["GET"])
def status(request):
    need(request.user, "manager")
    return Response(engine.status())
