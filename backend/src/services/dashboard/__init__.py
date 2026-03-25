"""Dashboard status builder mixins."""

from .innovation import DashboardInnovationStatusMixin
from .proposal import DashboardProposalStatusMixin
from .sci import DashboardSciStatusMixin
from .shared import DashboardStatusSharedMixin
from .thesis import DashboardThesisStatusMixin

__all__ = [
    "DashboardInnovationStatusMixin",
    "DashboardProposalStatusMixin",
    "DashboardSciStatusMixin",
    "DashboardStatusSharedMixin",
    "DashboardThesisStatusMixin",
]
