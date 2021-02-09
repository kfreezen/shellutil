import subprocess
import os

from typing import Tuple

from abstractshell.ssh import WrappedSSHClient
from abstractshell.shell_expect import PtyShellExpect, RemotePtyShellExpect

import logging
import ptyprocess
from pexpect.utils import split_command_line

logger = logging.getLogger("shells")


class ShellIO:
    def __init__(self):
        pass


class LocalShellIO(ShellIO):
    def __init__(self, proc, io_attr):
        super().__init__()
        self.process = proc
        self._io_attr = io_attr

    def wait_exit_status(self):
        self.process.wait()
        return self.process.returncode

    def exit_status_ready(self):
        return self.poll() is not None

    def __getattr__(self, item):
        io = getattr(self.process, self._io_attr)
        return getattr(io, item)

    def __iter__(self):
        io = getattr(self.process, self._io_attr)
        return iter(io)


class RemoteShellIO(ShellIO):
    def __init__(self, io):
        super().__init__()
        self._io = io

    def wait_exit_status(self):
        return self._io.channel.recv_exit_status()

    def exit_status_ready(self):
        return self._io.channel.exit_status_ready()

    def __getattr__(self, item):
        return getattr(self._io, item)

    def __iter__(self):
        return iter(self._io)


class Shell:
    # FIXME: requires_sudo may not be necessary.
    # FIXME: ssh_keyfile may be redundant, or not a good plan.
    def __init__(self, remote=False, ssh_keyfile=None, requires_sudo=False):
        """
        ssh_keyfile: The private key file that this shell should use for authentication.
        """

        self.remote = remote
        self.ssh_keyfile = ssh_keyfile
        self.requires_sudo = requires_sudo

    def chmod(self, perms: int, path):
        if isinstance(perms, int):
            perms = oct(perms)[2:]

        (_stdin, stdout, _stderr) = self.exec("chmod {perms} {path}")
        return stdout.wait_exit_status() == 0

    def interact(self, command: str) -> PtyShellExpect:
        raise NotImplementedError("Each shell should implement its own shell expect.")

    def exec_statusonly(self, command: str) -> int:
        (_stdin, stdout, _stderr) = self.exec(command)
        return stdout.wait_exit_status()

    def exec(self, command: str) -> Tuple[ShellIO, ShellIO, ShellIO]:
        raise NotImplementedError(
            "exec not implemented in abstract Shell class, should have instantiated LocalShell or RemoteShell"
        )

    def mkdir(self, path):
        (_stdin, stdout, stderr) = self.exec(f"sudo mkdir -p {path}")
        logger.info(
            f"mkdir -p {path}: <%s> <%s>",
            stdout.read().decode(),
            stderr.read().decode(),
        )

        return stdout.wait_exit_status()

    def dirsize(self, path):
        (_i, out, err) = self.exec(f"du -sk {path}")

        for line in out.readlines():
            match = self._du_line.match(line.decode())
            groups = match.groups()
            return int(groups[0]) * 1024
        return None

    def filesize(self, path):
        cmd = f'stat "{path}" -c "%s"'
        (_i, stdout, _e) = self.exec(cmd)
        size_str = stdout.read().decode()
        try:
            return int(size_str)
        except ValueError as e:
            return None

    def path_exists(self, path):
        exists_status = self.exec_statusonly(f"ls -1 {path}")
        return exists_status == 0


class LocalShell(Shell):
    def __init__(self, ssh_keyfile=None, requires_sudo=False):
        super().__init__(
            remote=False, ssh_keyfile=ssh_keyfile, requires_sudo=requires_sudo
        )

    def exec(self, command: str) -> Tuple[ShellIO, ShellIO, ShellIO]:
        proc = subprocess.Popen(
            command,
            shell=True,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        return (
            LocalShellIO(proc, "stdin"),
            LocalShellIO(proc, "stdout"),
            LocalShellIO(proc, "stderr"),
        )

    def interact(self, command: str) -> PtyShellExpect:
        ptyproc = self._exec_pty(command)
        return PtyShellExpect(ptyproc)

    def _exec_pty(
        self, command: str, cwd=None, env=None, echo=None
    ) -> ptyprocess.PtyProcess:
        cwd = cwd or os.getcwd()
        env = os.environ if env is None else env
        echo = True if env is None else env

        argv = split_command_line(command)

        ptyproc = ptyprocess.PtyProcess.spawn(
            argv, os.getcwd(), env=os.environ, echo=True
        )
        return ptyproc


class RemoteShell(Shell):
    def __init__(self, client: WrappedSSHClient, ssh_keyfile=None, requires_sudo=False):
        super().__init__(
            remote=True, ssh_keyfile=ssh_keyfile, requires_sudo=requires_sudo
        )
        self.client = client

    def exec(self, command: str) -> Tuple[ShellIO, ShellIO, ShellIO]:
        stdin, stdout, stderr = self.client.exec_command(command)
        return (RemoteShellIO(stdin), RemoteShellIO(stdout), RemoteShellIO(stderr))

    def interact(self, command: str) -> PtyShellExpect:
        (_stdin, stdout, stderr) = self.client.exec_command(command, get_pty=True)
        return RemotePtyShellExpect(_stdin, stdout)

    @property
    def hostname(self):
        return self.client.hostname

    @property
    def username(self):
        return self.client.username

    @property
    def password(self):
        return self.client.password

    @staticmethod
    def establish_connection(remote_server, username, password, ssh_keyfile=None):
        is_ssh_valid = False
        r_client = None

        while not is_ssh_valid:
            if username is None or password is None:
                return None

            r_client = WrappedSSHClient(remote_server, username, password)
            if r_client.connect(remote_server, username, password):
                is_ssh_valid = True
            else:
                logger.error("SSH INVALID")
                return None

        rsh = RemoteShell(r_client, ssh_keyfile=ssh_keyfile)
        return rsh
