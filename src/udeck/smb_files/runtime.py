"""Run only the dedicated Samba unit; never touch distro Samba configuration."""

import asyncio
import ipaddress
import json
import os
import pwd
import re
import socket
from pathlib import Path

from . import UNIT

RUNTIME = Path("/run/udeck-smb")
STATE = Path("/var/lib/udeck-smb")
DROPIN = Path("/run/systemd/system/udeck-smb.service.d/share.conf")


async def command(arguments, *, timeout=20, **kwargs):
    process = await asyncio.create_subprocess_exec(*arguments, stdout=asyncio.subprocess.PIPE,
                                                  stderr=asyncio.subprocess.PIPE, **kwargs)
    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout)
    except TimeoutError:
        process.kill()
        await process.wait()
        raise RuntimeError("Timed out: " + arguments[0]) from None
    if process.returncode:
        raise RuntimeError((stderr or stdout).decode(errors="replace").strip()[-1000:] or "Command failed: " + arguments[0])
    return stdout.decode(errors="replace").strip()


async def check_access(root, actor):
    user = pwd.getpwuid(actor.uid)
    if user.pw_name != actor.name or user.pw_gid != actor.gid or actor.uid <= 0:
        raise PermissionError("The local sharing account is no longer available")
    # Drop all root credentials for the directory access check, including supplementary groups.
    await command(["/usr/bin/python3", "-I", "-c",
                   "import os,sys; p=sys.argv[1]; fd=os.open(p,os.O_DIRECTORY|os.O_NOFOLLOW); "
                   "ok=os.access(p,os.R_OK|os.W_OK|os.X_OK); os.close(fd); sys.exit(0 if ok else 1)", str(root)],
                  user=actor.uid, group=actor.gid, extra_groups=os.getgrouplist(actor.name, actor.gid))


def samba_config(username, addresses):
    if not re.fullmatch(r"[a-zA-Z_][a-zA-Z0-9_.-]{0,63}\$?", username) or username == "root":
        raise ValueError("Invalid local sharing account")
    addresses = sorted({ipaddress.ip_address(address) for address in addresses}, key=str)
    if not addresses:
        raise ValueError("No selected network addresses are available")
    interfaces = " ".join(str(address) + ("/128" if address.version == 6 else "/32") for address in addresses)
    return f"""[global]
server role = standalone server
security = user
map to guest = Bad User
guest account = {username}
server min protocol = SMB2_02
server max protocol = SMB3
smb ports = 445
interfaces = {interfaces}
bind interfaces only = yes
disable netbios = yes
load printers = no
printing = bsd
printcap name = /dev/null
disable spoolss = yes
usershare max shares = 0
allow insecure wide links = no
wide links = no
follow symlinks = no
unix extensions = no
pid directory = /run/udeck-smb
lock directory = /run/udeck-smb/lock
state directory = /var/lib/udeck-smb/samba
cache directory = /var/lib/udeck-smb/cache
private dir = /var/lib/udeck-smb/private
ncalrpc dir = /run/udeck-smb/ncalrpc
log file = /var/lib/udeck-smb/samba.log
max log size = 256
passdb backend = tdbsam:/var/lib/udeck-smb/private/passdb.tdb
[udeck]
path = /run/udeck-smb/share
guest ok = yes
guest only = yes
force user = {username}
read only = no
browseable = yes
follow symlinks = no
wide links = no
"""


class SambaRuntime:
    async def validate(self, value, addresses):
        from .lifecycle import Actor, atomic_write
        await check_access(Path(value["root"]), Actor(uid=value["uid"], gid=value["gid"], name=value["username"], pid=0))
        if not Path("/usr/sbin/smbd").is_file():
            raise RuntimeError("Samba is not installed. Install the uDeck Debian package with its guarded installer.")
        for directory in (RUNTIME, RUNTIME / "lock", STATE / "samba", STATE / "cache", STATE / "private"):
            directory.mkdir(parents=True, exist_ok=True)
        for directory in (RUNTIME / "lock", STATE / "samba", STATE / "cache"):
            directory.chmod(0o755)
        (STATE / "private").chmod(0o700)
        if addresses:
            atomic_write(RUNTIME / "check.conf", samba_config(value["username"], addresses))
            await command(["/usr/bin/testparm", "--suppress-prompt", "--debuglevel=0", str(RUNTIME / "check.conf")])

    async def start(self, value, addresses):
        from .lifecycle import atomic_write
        await self.validate(value, addresses)
        # This check happens after our old cgroup has stopped. Do not stop other servers.
        sockets = []
        try:
            for address in sorted(addresses):
                stream = socket.socket(socket.AF_INET6 if ":" in address else socket.AF_INET, socket.SOCK_STREAM)
                sockets.append(stream)
                stream.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                if ":" in address:
                    stream.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1)
                stream.bind((address, 445))
        except OSError as error:
            raise OSError("TCP port 445 is already in use or unavailable on a selected address: " + str(error)) from error
        finally:
            for stream in sockets:
                stream.close()
        atomic_write(RUNTIME / "smb.conf", samba_config(value["username"], addresses))
        atomic_write(RUNTIME / "identity.json", json.dumps(value["identity"]))
        (RUNTIME / "share").mkdir(exist_ok=True)
        # BindPaths pins the original inode inside this unit's mount namespace.
        # Replacing the user-facing directory cannot expose a different directory.
        root = value["root"].replace("\\", "\\\\").replace('"', '\\"').replace("%", "%%")
        atomic_write(DROPIN, '[Service]\nBindPaths=\nBindPaths="' + root + '":/run/udeck-smb/share\n')
        await command(["systemctl", "daemon-reload"])
        await command(["systemctl", "start", UNIT])
        if not await self.alive():
            raise RuntimeError("Samba could not start; check the udeck-smb service journal")

    async def stop(self):
        await command(["systemctl", "stop", UNIT])

    async def alive(self):
        try:
            return await command(["systemctl", "is-active", UNIT]) == "active"
        except RuntimeError:
            return False


def launch():
    """Verify the bind mount's inode before Samba starts accepting connections."""
    stat = (RUNTIME / "share").stat()
    if [stat.st_dev, stat.st_ino] != json.loads((RUNTIME / "identity.json").read_text()):
        raise RuntimeError("Shared folder changed before Samba startup")
    os.execv("/usr/sbin/smbd", ["/usr/sbin/smbd", "--foreground", "--no-process-group", "--configfile=" + str(RUNTIME / "smb.conf")])


if __name__ == "__main__":
    launch()
