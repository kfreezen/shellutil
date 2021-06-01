import os
import re
import shutil
import random
import json

from tempfile import mkstemp
from abstractshell.shells import Shell, LocalShell, RemoteShell
from typing import List, Union, Optional

REMOTE_RE = re.compile(r"^([^/]+@)?([^/]+):(.*)$")


def _not_implemented(t, fn):
    n = t.__name__
    return f"Abstract class {n} does not implement {fn}. Please use a subclass"


class AbstractPath:
    def __init__(self, remote):
        self.remote = remote

    @staticmethod
    def from_string(path, shell: Shell):
        if shell.remote:
            if not REMOTE_RE.match(path):
                path = f"{shell.username}@{shell.hostname}:{path}"

            return RemotePath(path, shell)
        return LocalPath(path)

    @property
    def shell(self):
        return None

    @property
    def local_path(self):
        return None

    def dirname(self) -> "AbstractPath":
        return AbstractPath.from_string(os.path.dirname(self.local_path), self.shell)

    def join(self, rel) -> "AbstractPath":
        return AbstractPath.from_string(os.path.join(self.local_path, rel), self.shell)

    def mkdir(self):
        raise NotImplementedError(_not_implemented(AbstractPath, "mkdir"))

    def isfile(self) -> bool:
        raise NotImplementedError(_not_implemented(AbstractPath, "isfile"))

    def isdir(self) -> bool:
        raise NotImplementedError(_not_implemented(AbstractPath, "isdir"))

    def listdir(self) -> List[str]:
        raise NotImplementedError(_not_implemented(AbstractPath, "listdir"))

    def read_contents(self) -> str:
        raise NotImplementedError(_not_implemented(AbstractPath, "read_contents"))

    def write_contents(self, contents) -> str:
        raise NotImplementedError(_not_implemented(AbstractPath, "write_contents"))

    def rename(self, path: Union[str, "AbstractPath"]):
        raise NotImplementedError(_not_implemented(AbstractPath, "rename"))

    def copyto(self, path: Union[str, "AbstractPath"]) -> bool:
        raise NotImplementedError(_not_implemented(AbstractPath, "copyto"))

    def unlink(self):
        raise NotImplementedError(_not_implemented(AbstractPath, "unlink"))

    def stat(self) -> os.stat_result:
        raise NotImplementedError(_not_implemented(AbstractPath, "stat"))

    def filesize(self) -> int:
        return self.stat().st_size

    def uses_shell(self, sh) -> bool:
        raise NotImplementedError(_not_implemented(AbstractPath, "uses_shell"))


class LocalPath(AbstractPath):
    def __init__(self, path):
        super().__init__(False)
        if isinstance(path, AbstractPath):
            path = path.local_path

        self.path = path

    def __fspath__(self):
        return self.path

    def __str__(self):
        return self.path

    def __repr__(self):
        return str(self)

    @property
    def shell(self):
        return LocalShell()

    @property
    def local_path(self):
        return self.path

    def mkdir(self):
        os.makedirs(self.path, exist_ok=True)

    def isfile(self) -> bool:
        return os.path.isfile(self.path)

    def isdir(self) -> bool:
        return os.path.isdir(self.path)

    def listdir(self) -> List[str]:
        return os.listdir(self.path)

    def read_contents(self) -> str:
        with open(self.path, "r") as f:
            return f.read()

    def write_contents(self, contents) -> str:
        try:
            with open(self.path, "w") as f:
                f.write(contents)
            return True
        except:
            return False

    def rename(self, path: Union[str, AbstractPath]):
        os.rename(self.path, path)

    def copyto(self, path: Union[str, "AbstractPath"]) -> bool:
        from .transfer import RsyncBase

        if isinstance(path, str):
            if REMOTE_RE.match(path):
                raise ValueError(
                    "LocalPath.copyto() does not support casting string to RemotePath"
                )
            path = LocalPath(path)

        if isinstance(path, LocalPath):
            shutil.copyfile(self.path, path.path)
            return True
        elif isinstance(path, RemotePath):
            rsync = RsyncBase(LocalShell(), path.shell)
            if self.isdir():
                return rsync.transfer_folder(self, path)
            else:
                return rsync.transfer_file(self, path)

    def unlink(self):
        os.unlink(self.local_path)

    def stat(self) -> os.stat_result:
        return os.stat(self.local_path)

    def uses_shell(self, sh) -> bool:
        return isinstance(sh, LocalShell)


class RemotePath(AbstractPath):
    def __init__(self, path, shell: Shell):
        super().__init__(True)
        self.path = path
        self._shell = shell

    def __str__(self):
        return self.path

    def __repr__(self):
        return str(self)

    def _host(self):
        string = ""
        if self.user:
            string += self.user

        string += self.host
        return string

    @property
    def shell(self):
        return self._shell

    @property
    def path(self):
        return f"{self._host()}:{self.local_path}"

    @path.setter
    def path(self, path):
        match = REMOTE_RE.match(path)
        if not match:
            raise ValueError("Path was not remote path")
        (user, host, local_path) = match.groups()
        self.user = user
        self.host = host
        self._local_path = local_path

    @property
    def local_path(self):
        return self._local_path

    def mkdir(self):
        self.shell.mkdir(self.local_path)

    def isfile(self) -> bool:
        return self.shell.exec_statusonly(f"test -f {self.local_path}") == 0

    def isdir(self) -> bool:
        return self.shell.exec_statusonly(f"test -d {self.local_path}") == 0

    def listdir(self) -> List[str]:
        (_i, dirlist, _e) = self.shell.exec(f"ls -1 {self.local_path}")
        return [s.strip() for s in dirlist.read().decode().split("\n")]

    def read_contents(self) -> str:
        (_i, f, _e) = self.shell.exec(f"cat {self.local_path}")
        return f.read().decode()

    def write_contents(self, contents) -> str:
        from .transfer import RsyncBase

        (fd, name) = mkstemp()
        os.write(fd, contents.encode())
        os.close(fd)

        rsync = RsyncBase(LocalShell(), self.shell, progress_bar=False)

        ret = rsync.transfer_file(AbstractPath.from_string(name, LocalShell()), self)
        os.unlink(name)
        return ret

    def rename(self, path: Union[str, AbstractPath]):
        if isinstance(path, str):
            path = RemotePath(path, self.shell)

        return (
            self.shell.exec_statusonly(f"mv {self.local_path} {path.local_path}") == 0
        )

    def copyto(self, path: Union[str, "AbstractPath"]) -> bool:
        from .transfer import RsyncBase

        if isinstance(path, str):
            raise ValueError(
                "RemotePath.copyto() does not support casting string to AbstractPath to prevent ambiguity."
            )

        src_shell = self.shell
        if isinstance(path, LocalPath):
            dest_shell = LocalShell()
        elif isinstance(path, RemotePath):
            dest_shell = path.shell

        rsync = RsyncBase(src_shell, dest_shell)
        if self.isdir():
            return rsync.transfer_folder(self, path)
        else:
            return rsync.transfer_file(self, path)

    def unlink(self):
        self.shell.exec_statusonly(f"rm -r {self.local_path}") == 0

    def stat(self) -> os.stat_result:
        (_i, o, _e) = self.shell.exec(
            f'stat -c "%f %i %d %h %u %g %s %X %Y %Z" {self.local_path}'
        )
        info = o.read().decode()
        if o.wait_exit_status() > 0:
            return None

        seq = re.split(r"\s+", info)
        seq = [s for s in seq if s]

        seq[0] = int(seq[0], 16)
        for i in range(1, len(seq)):
            seq[i] = int(seq[i])

        return os.stat_result(sequence=seq)

    def uses_shell(self, sh: Shell) -> bool:
        if isinstance(sh, LocalShell):
            return False

        if sh is self.shell:
            return True

        if sh.hostname == self.shell.hostname and sh.username == self.shell.username:
            return True

        test_file = f"/tmp/{random.getrandbits(32)}.test"
        i = sh.exec_statusonly(f"echo TEST > {test_file}")
        if i != 0:
            return None

        if self.shell.path_exists(test_file):
            sh.exec_statusonly(f"rm {test_file}")
            return True

        return False
