# System Settings Sharing and SMB — approved implementation plan

The user approved implementation, review, device testing, package verification, merge to main and push.

1. Move Web file access into Settings → Sharing and Y quick settings. Add Web and SMB submenus with independent enable, directory, networks, duration and addresses. Use single-line icon/name/status rows, preserve focus and show progress/errors with actual state. Remove the Files entry and forward legacy calls.
2. Preserve existing Web settings and APIs. Default SMB off with no directory or network selection. Use standard Samba SMB2/3, passwordless guest read/write, share name udeck, caller Unix permissions and no chmod of shared files.
3. Implement restricted system D-Bus Status/Configure/Stop with Polkit, dedicated Samba configuration/service and explicit port conflicts. Preserve unrelated Samba installations and suppress newly introduced distro service startup during Debian installation.
4. Bind exact selected NetworkManager connection addresses. Terminate established connections when disabled, expired, network authorization is revoked or the directory changes. Restore effective configuration after save/start failure.
5. Independently support permanent / 1 / 6 / 12 hours. Permanent survives restart and waits for selected networks. Timed sharing ends with the initiating session or deadline and never restores after reboot.
6. Test existing Web behavior, independence, failure/rollback, port conflicts, daemon failure, directory replacement, network revocation, expiry and permanent restore. Verify Chinese/English, classic/dark, 1280×720 and 960×600, focus and scrolling.
7. On uConsole use a temporary directory and a client on another device to list/upload/download/rename/delete using real guest SMB. Preserve the running desktop, SSH and existing sharing state. Review and fix bugs, verify the Debian package, commit, merge and push actual main, then check the live remote commit.
