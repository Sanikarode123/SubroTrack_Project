from django.contrib import admin
from .models import RecoveryCase, Activity, Document, Payment, AgentRun, AgentFinding, Profile, ThirdPartyEvent
for m in (RecoveryCase, Activity, Document, Payment, AgentRun, AgentFinding, Profile, ThirdPartyEvent):
    admin.site.register(m)
