# shellutil

## The goal of this project

The goal of this project was to enable local/remote agnostic shell command execution and expectation.

## Why?

I was writing a migration tool at work, and wanted an abstraction that could run migrations in the following scenarios:
* local -> remote
* remote -> remote
* local -> local

## Modules

### shells

```python
from shellutil.shells import LocalShell, RemoteShell

local_shell = LocalShell()

local_shell.exec("echo hello")

remote_shell = RemoteShell.establish_ssh_connection("example.com", "user", "password")
remote_shell.exec("echo hello remote")
```

### shell_expect
```python
from shellutil.shells import RemoteShell, LocalShell
from shellutil import shell_expect # For EOF

def interaction(interact):
  res = interact.expect([shell_expect.EOF, "regex"])
  if res == 0:
    return False
  return True

shell = RemoteShell.establish_ssh_connection("example.com", "user", "password")
local_shell = LocalShell()

remote_interact = shell.interact("echo regex")

local_interact = local_shell.interact("echo regex")

if interaction(remote_interact):
  print("got regex echoed remotely")
if interaction(local_interact):
  print("got regex echoed locally")
```

### pty_screen
This module is used internally by shellutil. Feel free to dig around in here, but there shouldn't be anything useful here for a consumer of this package.

This module uses pyte and a custom terminal screen to strip ANSI control codes from shell output for `shell_expect`

### ssh
This wraps the paramiko SSH client and stores client credentials in a `WrappedSSHClient`

