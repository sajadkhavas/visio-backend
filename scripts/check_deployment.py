"""Fail on unexpected Django deployment-check warnings.

Two HSTS directives are intentionally deferred until VISIO's production domain and
subdomain topology is frozen in R00/S00. Django itself warns that HSTS must be
configured carefully; enabling includeSubDomains or preload before that decision
would turn a CI checkbox into a domain-wide operational commitment.
"""

import os

import django
from django.core.checks import ERROR, WARNING, run_checks

EXPECTED_SETTINGS = "config.settings.production"
DEFERRED_WARNING_IDS = {"security.W005", "security.W021"}

if os.environ.get("DJANGO_SETTINGS_MODULE") != EXPECTED_SETTINGS:
    raise SystemExit(
        f"Deployment gate requires DJANGO_SETTINGS_MODULE={EXPECTED_SETTINGS}."
    )

django.setup()
issues = run_checks(include_deployment_checks=True)

blocking = []
deferred = []
for issue in issues:
    if issue.level >= ERROR:
        blocking.append(issue)
    elif issue.level >= WARNING:
        if issue.id in DEFERRED_WARNING_IDS:
            deferred.append(issue)
        else:
            blocking.append(issue)

for issue in deferred:
    print(f"DEFERRED {issue.id}: {issue.msg}")

if blocking:
    details = "\n".join(f"{issue.id}: {issue.msg}" for issue in blocking)
    raise SystemExit(f"Unexpected deployment check issues:\n{details}")

print(
    "Django deployment gate passed: no errors or unexpected warnings; "
    "HSTS includeSubDomains/preload remain explicitly deferred to R00/S00."
)
