from django.contrib import admin

from .models import ApprovalWorkflow, ApprovalStep, Approval

for m in (ApprovalWorkflow, ApprovalStep, Approval,):
    admin.site.register(m)
