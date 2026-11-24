from django.urls import path
from rest_framework.routers import DefaultRouter
from . import views
from analytics import views as analytics_views
from rag import views as rag_views

router = DefaultRouter()
router.register("cases", views.CaseViewSet, basename="case")
urlpatterns = [
    path("login/", views.login), path("me/", views.me), path("users/", views.users),
    path("alerts/", views.alerts), path("dashboard/", views.dashboard), path("third-parties/", views.third_parties),
    path("documents/<int:pk>/", views.document_detail), path("documents/<int:pk>/process/", views.document_process),
    path("analytics/run/", analytics_views.run), path("analytics/status/", analytics_views.status),
    path("analytics/results/", analytics_views.results), path("analytics/refresh/", analytics_views.refresh),
    path("analytics/cancel/", analytics_views.cancel),
    path("rag/ask/", rag_views.ask), path("rag/reindex/", rag_views.reindex), path("rag/status/", rag_views.status),
    path("agent/run/", views.agent_run), path("agent/latest/", views.agent_latest),
    path("agent/findings/<int:pk>/respond/", views.finding_respond),
] + router.urls
