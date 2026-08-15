from rest_framework.throttling import UserRateThrottle


class ConnectivityThrottle(UserRateThrottle):
    scope = "connectivity"


class JobCreateThrottle(UserRateThrottle):
    scope = "job_create"
