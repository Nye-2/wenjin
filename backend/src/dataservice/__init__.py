"""DataService domain package.

DataService is the long-term owner for Wenjin persistence models, data
commands, queries, and database transactions. Gateway, worker, and agent code
should depend on DataService application APIs or ``dataservice_client`` instead
of importing domain repositories directly.
"""

__all__ = ["__version__"]

__version__ = "0.1.0"
