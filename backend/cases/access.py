from rest_framework.exceptions import PermissionDenied
from .models import RecoveryCase


def role_of(user):
    if user.is_superuser or user.is_staff:
        return "manager"
    profile = getattr(user, "profile", None)
    return profile.role if profile else "employee"


def visible_cases(user):
    role, qs = role_of(user), RecoveryCase.objects.all()
    if role == "manager":
        return qs
    if role == "employee":
        return qs.filter(assigned_to=user)
    return qs.filter(client=user)


def need(user, *roles):
    if role_of(user) not in roles:
        raise PermissionDenied("You do not have permission to do this.")
