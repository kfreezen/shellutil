import logging
import sys
import os
import re
from tqdm import tqdm
from enum import Enum

from typing import Union, Optional

import questionary

from abstractshell.shells import Shell, RemoteShell
from abstractshell import shell_expect
from abstractshell.paths import AbstractPath

logger = logging.getLogger("transfer")

RsyncPathTypes = Union[str, AbstractPath]


class RsyncProgress:
    class MultiProgressState(Enum):
        INITIALIZING = -1
        EOF = 0
        PROGRESS_INFO = 1
        FILE_NAME = 2
        SUMMARY = 3

    def __init__(self, interact, filesize=None, multiple=False):
        self.interact = interact
        self.filesize = filesize
        self.multiple = multiple

    def progress(self):
        if self.multiple:
            return self._multiple_progress()
        else:
            return self._single_progress()

    def _multiple_progress(self):
        interact = self.interact

        progress_bar = None

        # progress = tqdm(
        #    total=self.filesize, unit="B", unit_scale=True, unit_divisor=1024
        # )
        progress_closed = False

        state = RsyncProgress.MultiProgressState.INITIALIZING

        def _print_me(*args, **kwargs):
            with open("/tmp/rsync-out.log", "a") as f:
                kwargs["file"] = f
                print(*args, **kwargs)

        while True:
            (match, i) = interact.expect_match(
                [
                    shell_expect.EOF,
                    r"\s+(\d+)\s*(\d+)%\s+([\d\.]+.B\/s)\s+([0-9:]+)\s\(xfer#(\d+),\sto-check\=(\d+)\/(\d+)\)",
                    r"([\w\/]+)\r",
                    r"total size is (\d+)\s+speedup is ([\d\.]+)",
                ],
                echo=True,
                printfn=_print_me,
            )

            try:
                state = RsyncProgress.MultiProgressState(i)
            except ValueError:
                logger.error("State %s does not exist in MultiProgressState")
                continue

            if state == RsyncProgress.MultiProgressState.PROGRESS_INFO:
                (
                    _transferred,
                    _percentage,
                    _speed_str,
                    _time,
                    xfer,
                    check,
                    check_total,
                ) = match.groups()
                xfer = int(xfer)
                check = int(check)
                check_total = int(check_total)

                if progress_bar is None:
                    progress_bar = tqdm(
                        total=int(check_total),
                        unit="files",
                        position=0,
                        leave=True,
                    )
                else:
                    if progress_bar.total < check_total:
                        progress_bar.total = check_total

                    # deltaN = (T - Tc) - n
                    update_n = (progress_bar.total - check) - progress_bar.n
                    progress_bar.update(update_n)
            elif state == RsyncProgress.MultiProgressState.FILE_NAME:
                name = match.groups()[0]
                if progress_bar:
                    progress_bar.display(name, 1)
            elif state == RsyncProgress.MultiProgressState.SUMMARY:
                size, speedup = match.groups()
                speedup = float(speedup)

                if progress_bar:
                    progress_bar.update(progress_bar.total - progress_bar.n)
                    progress_bar.close()
                    sys.stderr.flush()
                progress_closed = True

                if speedup > 1.0:
                    print(f"rsync speedup factor was {speedup}")

            elif state == RsyncProgress.MultiProgressState.EOF:
                break

        if progress_bar and not progress_closed:
            progress_bar.close()
            sys.stderr.flush()

    def _single_progress(self):
        interact = self.interact

        progress = tqdm(
            total=self.filesize,
            unit="B",
            unit_scale=True,
            unit_divisor=1024,
            leave=True,
        )
        prev_size = 0

        progress_closed = False

        while True:
            (match, i) = interact.expect_match(
                [
                    shell_expect.EOF,
                    r"\s+(\d+)\s*(\d+)%\s+([\d\.]+.B\/s)\s+([0-9:]+)",
                    r"total size is (\d+)\s+speedup is ([\d\.]+)",
                ],
                echo=False,
            )

            if i == 0:
                return

            if i == 1:
                size, _percent, _speed, _elapsed = match.groups()
                size = int(size)
                progress.update(size - prev_size)
                prev_size = size
            if i == 2:
                size, speedup = match.groups()

                size = int(size)
                speedup = float(speedup)

                progress.update(size - prev_size)
                progress_closed = True
                progress.close()
                sys.stderr.flush()

                if speedup > 1.0:
                    print(f"rsync speedup factor was {speedup}")

        if not progress_closed:
            progress.close()
            sys.stderr.flush()


class RsyncCommand:
    def __init__(self):
        self.remote_rsync = None
        self.flags = "az"
        self.exclusions = None
        self.rsh = None
        self.progress = True
        self.delete = False

        self.source = None
        self.destination = None

    def set_flags(self, flags):
        self.flags = flags

    def set_remote_rsync(self, remote):
        self.remote_rsync = remote

    def set_remote_shell(self, rsh):
        self.rsh = rsh

    def set_exclusions(self, exclusions):
        self.exclusions = exclusions

    def set_source(self, source):
        self.source = source

    def set_destination(self, dest):
        self.destination = dest

    def show_progress_bar(self, progress):
        self.progress = progress

    def delete_remote_files(self, delete):
        self.delete = delete

    def _string(self):
        if not self.source or not self.destination:
            raise RuntimeError(
                "source and destination must be supplied for a valid rsync command."
            )

        cmd = RsyncCommandBuilder()

        cmd.start()
        cmd.remote_rsync(self.remote_rsync)
        cmd.remote_shell(self.rsh)
        cmd.flags(self.flags or "az")
        cmd.progress(self.progress)
        cmd.delete(self.delete)
        cmd.exclusions(self.exclusions)
        cmd.source(self.source)
        cmd.destination(self.destination)
        return cmd.command

    def __str__(self):
        return self._string()

    def __repr__(self):
        return str(self)


class RsyncCommandBuilder:
    def start(self):
        self.command = "rsync"

    def remote_rsync(self, remote):
        if remote:
            self.command += f' --rsync-path="{remote}" '

    def exclusions(self, exclusions):
        if exclusions:
            exclusion_strings = [f"--exclude={e}" for e in exclusions]
            self.command += " " + " ".join(exclusion_strings)

    def remote_shell(self, rsh):
        if rsh:
            self.command += f' -e "{rsh}"'

    def flags(self, flags):
        if flags:
            self.command += f" -{flags}"

    def progress(self, use_progress):
        if use_progress:
            self.command += f" --no-human-readable --progress"

    def delete(self, use_delete):
        if use_delete:
            self.command += f" --delete"

    def source(self, source):
        self.command += f" {source}"

    def destination(self, dest):
        self.command += f" {dest}"


class Rsync:
    remote_re = re.compile(r"^([^/]+@)?([^/]+):(.*)$")

    def __init__(
        self,
        sudo=True,
        flags="aczq",
        delete=False,
        ssh_key=None,
        src_shell: Shell = None,
        dest_shell: Shell = None,
    ):
        self.sudo = sudo
        self.ssh_key = ssh_key
        self.flags = flags
        self.delete = delete
        self.src_shell = src_shell
        self.dest_shell = dest_shell

    def run(
        self,
        source: AbstractPath,
        dest: AbstractPath,
        exclusions=None,
        password=None,
        progress_bar=True,
    ):
        dest_folder = dest.dirname()

        if not dest_folder.isdir():
            dest_folder.mkdir()

        if source.isdir():
            multiple = True
            filesize = None
        elif source.isfile():
            multiple = False
            filesize = source.filesize()
        else:
            logger.error("source %s does not exist", str(source))
            return False

        (cmd_shell, dest_shell, cmd) = self.generate_command(source, dest, exclusions)
        expect_password = not source.uses_shell(dest.shell)
        logger.info("rsync_args %s", str(cmd))

        interact = cmd_shell.interact(str(cmd))
        if expect_password:
            res = interact.expect(
                [shell_expect.EOF, r".*@.*'s password:\s*", r".*\n"], echo=False
            )
            if res == 1:
                password = password or dest_shell.password
                if password is None:
                    logger.error("rsync expected a password and none was provided.")
                    password = questionary.password(
                        "Enter a password since none was provided"
                    ).ask()
                elif callable(password):
                    password = password()

                if password is None:
                    return False

                interact.send(password)

        print("progress_bar", progress_bar)
        if progress_bar:
            progress = RsyncProgress(interact, filesize, multiple=multiple)
            progress.progress()

        if progress_bar:
            exitstatus = interact.wait_exit_status()
        else:
            exitstatus = interact.wait_exit_status(echo=False)

        if exitstatus == 255:
            if not hasattr(dest_shell, "hostname"):
                logger.error(
                    "SSH key mismatch on rsync transfer. Please fix the error manually."
                )
                return False

            questionary.print("  Mismatched host key found in known_hosts file.")
            res = questionary.confirm(
                "Do you want to automatically remove it and retry?"
            ).unsafe_ask()
            if not res:
                return False

            interact = cmd_shell.interact(f"ssh-keygen -R {dest_shell.hostname}")
            interact.expect(shell_expect.EOF)

            return self.run(
                source,
                dest,
                exclusions=exclusions,
                password=password,
                progress_bar=progress_bar,
            )
        if exitstatus not in [0, 24]:
            logger.error("Error occurred during rsync: %s", exitstatus)
        return exitstatus in [0, 24]

    def generate_command(
        self, source: AbstractPath, dest: AbstractPath, exclusions=None
    ):
        rsync_cmd = RsyncCommand()

        same_shell = source.uses_shell(dest.shell)
        shell = source.shell
        dest_shell = dest.shell

        source_isdir = source.isdir()
        dest_isdir = dest.isdir()

        if same_shell:
            source_string = source.local_path
            dest_string = dest.local_path
        elif not dest.remote:
            source_string = source.path
            dest_string = dest.local_path
            shell = dest.shell
            dest_shell = source.shell
        else:
            source_string = source.local_path
            dest_string = dest.path

        if source_isdir and source_string[-1] != "/":
            source_string += "/"
        if dest_isdir and dest_string[-1] != "/":
            dest_string += "/"

        rsync_cmd.set_source(source_string)
        rsync_cmd.set_destination(dest_string)

        if not same_shell:
            rsh = "ssh -oStrictHostKeyChecking=no"
            if self.ssh_key is not None:
                rsh += f" -i{self.ssh_key}"
            rsync_cmd.set_remote_shell(rsh)
            rsync_cmd.set_remote_rsync("sudo rsync" if self.sudo else None)

        rsync_cmd.show_progress_bar(True)

        rsync_cmd.set_exclusions(exclusions or [])
        rsync_cmd.set_flags(self.flags)
        rsync_cmd.delete_remote_files(self.delete)

        return (shell, dest_shell, rsync_cmd)


class RsyncBase:
    def __init__(self, src_shell, dest_shell, ssh_key=None, progress_bar=True):
        self.src_shell = src_shell
        self.dest_shell = dest_shell
        self.ssh_key = ssh_key or dest_shell.ssh_keyfile
        self.progress_bar = progress_bar

    def _transfer(
        self,
        source_path: RsyncPathTypes,
        dest_path: RsyncPathTypes,
        password=None,
        flags="czvP",
        exclusions=None,
        delete=False,
    ):
        if isinstance(source_path, str):
            source_path = AbstractPath.from_string(source_path, self.src_shell)
        if isinstance(dest_path, str):
            dest_path = AbstractPath.from_string(dest_path, self.dest_shell)
        if exclusions is None:
            exclusions = []

        rsync = Rsync(
            sudo=True,
            flags=flags,
            src_shell=source_path.shell,
            dest_shell=dest_path.shell,
            delete=delete,
        )
        ret = rsync.run(
            source_path,
            dest_path,
            password=password,
            exclusions=exclusions,
            progress_bar=self.progress_bar,
        )
        return dest_path if ret else None

    def transfer_file(
        self,
        source_path: RsyncPathTypes,
        dest_path: RsyncPathTypes,
        password=None,
    ):
        return self._transfer(source_path, dest_path, password, "czvP")

    def transfer_folder(
        self,
        source_path: RsyncPathTypes,
        dest_path: RsyncPathTypes,
        delete=True,
        exclusions=None,
        password=None,
    ):
        return self._transfer(
            source_path,
            dest_path,
            password,
            "aczvP",
            exclusions=exclusions,
            delete=delete,
        )
