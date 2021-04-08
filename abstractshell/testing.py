import os

from .shells import LocalShell


class MockShell(LocalShell):
    """
    A shell which chroots to an isolated test directory against which
    to test commands
    """

    _existing_mock_shell = None

    def __init__(self, root_path, ssh_keyfile=None, requires_sudo=True):
        if self._existing_mock_shell:
            raise AttributeError(
                "_existing_mock_shell already defined. Do not instantiate more than one mock shell."
            )

        super().__init__(ssh_keyfile=ssh_keyfile, requires_sudo=requires_sudo)
        MockShell._existing_mock_shell = self

        os.chroot(root_path)
