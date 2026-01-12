"""Adapters for external side effects."""

from agent_history.adapters.inventory import InventoryProvider
from agent_history.adapters.remote import RemoteClientError, RemoteFetchResult, SSHRemoteClient

__all__ = [
    "InventoryProvider",
    "RemoteClientError",
    "RemoteFetchResult",
    "SSHRemoteClient",
]
