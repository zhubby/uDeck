"""Compatibility alias for callers of the former Files-owned controls."""

from ..sharing import SharingControls


class NetworkAccessControls(SharingControls):
    def _init_network_access(self):
        self._init_sharing()

    def _close_network_access(self):
        self._close_sharing()
