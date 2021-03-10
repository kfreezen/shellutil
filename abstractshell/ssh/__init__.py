import os
import sys

import paramiko
from paramiko.ssh_exception import SSHException

from paramiko_expect import SSHClientInteraction

import logging

logger = logging.getLogger("shellutil-ssh")

interact_logger = logging.getLogger("ssh-client-interaction")


def interaction_output_func(msg):
    sys.stdout.write(msg)
    sys.stdout.flush()

    interact_logger.debug(msg)


class WrappedSSHClient:
    """
    This is a wrapper that permits us to re-connect if an SSH connection becomes stale.
    """

    def __init__(self, hostname=None, username=None, password=None):
        self.client = paramiko.SSHClient()
        self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        self.hostname = hostname
        self.username = username
        self.password = password

    def close(self):
        return self.client.close()

    def connect(self, hostname=None, username=None, password=None):
        hostname = hostname or self.hostname
        username = username or self.username
        password = password or self.password

        try:
            self.client.connect(
                hostname=hostname,
                username=username,
                password=password,
            )
            return True
        except Exception:
            self.client.close()
            return False

    def interact(self):
        try:
            term_size = os.get_terminal_size()
            tty_width = term_size.columns
            tty_height = term_size.lines
        except OSError:
            # Handle the case where stdout might not be attached to a terminal.
            tty_width = 80
            tty_height = 24

        def _interact():
            interact = SSHClientInteraction(
                self.client,
                timeout=None,
                display=True,
                tty_width=tty_width,
                tty_height=tty_height,
                output_callback=interaction_output_func,
            )

            return interact

        return self._retry_ssh(_interact)

    def exec_command(self, *args, **kwargs):
        def _exec(*args, **kwargs):
            return self.client.exec_command(*args, **kwargs)

        return self._retry_ssh(_exec, *args, retries=3, **kwargs)

    def _retry_ssh(self, fn, *args, retries=3, **kwargs):
        try:
            return fn(*args, **kwargs)
        except SSHException as e:
            if retries > 0:
                try:
                    self.client.connect(
                        hostname=self.hostname,
                        username=self.username,
                        password=self.password,
                    )
                    logger.info("Successfully reconnected to SSH")

                except SSHException as e:
                    logger.error(
                        f"SSHException occurred while trying to reconnect ssh {e}"
                    )
                return self._retry_ssh(fn, *args, retries=retries - 1, **kwargs)
            else:
                raise
