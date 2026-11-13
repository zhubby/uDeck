"""Translate known service errors at the sharing UI boundary.

The D-Bus services retain their existing English error contract. Only their
known diagnostics are marked here; paths, account names and unknown system
diagnostics remain literal. Marked messages can follow later language changes.
"""

from .i18n import Message, Msg, tr

_ERRORS = {
    "Expected a configuration object": Msg.SHARING_INVALID_CONFIGURATION,
    "Choose an existing shared folder and a supported duration": Msg.SHARING_CHOOSE_FOLDER_AND_DURATION,
    "Select at least one connected network": Msg.SHARING_SELECT_CONNECTED_NETWORK,
    "Temporary access needs an active uDeck session": Msg.SHARING_TEMPORARY_SESSION_REQUIRED,
    "A selected network is no longer connected": Msg.SHARING_NETWORK_DISCONNECTED,
    "This SMB share belongs to another local user": Msg.SHARING_OTHER_USER,
    "Choose a non-root local user for guest file access": Msg.SHARING_NON_ROOT_USER_REQUIRED,
    "The shared folder path contains unsupported characters": Msg.SHARING_UNSUPPORTED_PATH,
    "Shared folder changed while enabling access": Msg.SHARING_FOLDER_CHANGED,
    "Shared folder changed before Samba startup": Msg.SHARING_FOLDER_CHANGED,
    "The local sharing account is no longer available": Msg.SHARING_ACCOUNT_UNAVAILABLE,
    "Invalid local sharing account": Msg.SHARING_INVALID_ACCOUNT,
    "No selected network addresses are available": Msg.SHARING_NO_ADDRESSES,
    "Samba is not installed. Install the uDeck Debian package with its guarded installer.": Msg.SHARING_SAMBA_MISSING,
    "Samba could not start; check the udeck-smb service journal": Msg.SHARING_SAMBA_START_FAILED,
    "Not authorized to manage SMB file sharing": Msg.SHARING_NOT_AUTHORIZED,
    "Configuration is too large": Msg.SHARING_CONFIGURATION_TOO_LARGE,
    "Could not manage the file service": Msg.SHARING_SERVICE_FAILED,
    "Install the uDeck systemd user service to keep network access on after restart": Msg.SHARING_PERSISTENCE_SERVICE_REQUIRED,
    "Network access is off": Msg.NETWORK_ACCESS_IS_OFF,
    "Shared folder is no longer available. Choose the folder again.": Msg.SHARING_FOLDER_UNAVAILABLE,
    "Shared folder is no longer available. Choose the folder again to resume access.": Msg.SHARING_FOLDER_UNAVAILABLE,
    "Samba service exited unexpectedly. Enable sharing again to retry.": Msg.SHARING_SERVICE_EXITED,
}


def sharing_message(value):
    if isinstance(value, Message):
        return value
    if value in _ERRORS:
        return tr(_ERRORS[value])
    for prefix, key, argument in (
        ("TCP port 445 is already in use or unavailable on a selected address: ", Msg.SHARING_PORT_UNAVAILABLE, "error"),
        ("Timed out: ", Msg.SHARING_COMMAND_TIMED_OUT, "command"),
        ("Could not restore previous SMB access: ", Msg.SHARING_RESTORE_FAILED, "error"),
    ):
        if value.startswith(prefix):
            return tr(key, **{argument: value[len(prefix):]})
    return value
