import re
import io
import sys

from typing import Union, Tuple, Iterable

from enum import Enum
from collections.abc import Iterable
import ptyprocess
import os
import select
import time
import socket

import pyte
from abstractshell.pty_screen import TextBufferScreen


class SpecialConstants(Enum):
    EOF = "eof"
    NO_LINE = "no_line"


EOF = SpecialConstants.EOF
PROMPT = r"(\(.*\)\s+)?\[.*\][\$\#]\s+"


class ShellExpectEOF(Exception):
    def __init__(self):
        super().__init__("ShellExpectEOF")


class LineIterator:
    def __init__(self, expect, stream, screen):
        self.interaction = expect
        self.screen = screen
        self.stream = stream
        self.buffer = ""

    def __iter__(self):
        return self

    def __next__(self):
        return self.next_line()

    def exhaust_buffer(self):
        buf = self.interaction._read_pty()
        if buf is SpecialConstants.EOF:
            buf = self.buffer
            self.buffer = ""
            return buf or SpecialConstants.EOF
        buf = self.buffer + buf
        self.buffer = ""

        return buf

    def next_line(self, match_re=None):
        while not self.buffer:
            buf = self.interaction._read_pty()
            if buf is SpecialConstants.EOF and not self.buffer:
                return SpecialConstants.EOF

            if not isinstance(buf, SpecialConstants):
                self.buffer += buf
            if not self.buffer:
                return SpecialConstants.NO_LINE
        found_match = None

        i = 0
        while i < len(self.buffer):
            if match_re:
                to_match = self.buffer[0 : i + 1]
                for (j, r_ex) in enumerate(match_re):
                    if isinstance(r_ex, SpecialConstants):
                        continue

                    match = r_ex.match(to_match)
                    if match:
                        found_match = (r_ex, j, to_match, match)
                        break

            if (
                i + 1 < len(self.buffer)
                and self.buffer[i] == "\r"
                and self.buffer[i + 1] == "\n"
            ):
                i += 2
                break
            if self.buffer[i] == "\n":
                i += 1
                break

            i += 1
            if found_match and i >= len(self.buffer):
                break

        line = self.buffer[0:i]

        if i == len(self.buffer):
            self.buffer = ""
        else:
            self.buffer = self.buffer[i:]

        if found_match:
            return found_match
        else:
            return (None, None, line, None)

    # def _read_pty_raw(self, timeout=0):
    #    """
    #    Returns whatever is in the proc fd buffer.
    #    """
    #    buf = b""
    #    while not self.ptyproc.eof():
    #        (rlist, wlist, xlist) = select.select([self.ptyproc.fd], [], [], timeout)
    #        if rlist:
    #            try:
    #                buf += os.read(self.ptyproc.fd, 1024)
    #            except OSError:
    #                if len(buf) > 0:
    #                    return buf
    #                else:
    #                    return None
    #        else:
    #            break

    #    return buf

    # def _read_pty(self):
    #    buf = self._read_pty_raw()
    #    if buf is None:
    #        return None
    #    if len(buf) == 0:
    #        return ""

    #    self.stream.feed(buf.decode())
    #    text = self.screen.readbuffer()
    #    return text


class PtyShellExpect:
    def __init__(self, ptyproc: ptyprocess.PtyProcess, echo=True):
        self.ptyproc = ptyproc

        self.screen = TextBufferScreen()
        self.stream = pyte.Stream(self.screen)
        self.line_itr = LineIterator(self, self.stream, self.screen)

        self.buffer_idx = 0
        self.buffer = b""

        self.current_output_lines = []
        self.line_history = []

    def __enter__(self):
        return self

    def __exit__(self, etype, evalue, etraceback):
        pass

    @property
    def current_output(self):
        return "".join(self.current_output_lines)

    def exit_status_ready(self):
        return not self.ptyproc.isalive()

    def _default_print(self, output):
        sys.stdout.write(output)
        sys.stdout.flush()

    def wait_exit_status(self, echo=True, printfn=None):
        if not printfn:
            printfn = self._default_print

        while self.ptyproc.isalive():
            buf = self._read_pty_raw(0.01)
            if buf is SpecialConstants.EOF:
                break

            if len(buf) > 0:
                self.stream.feed(buf.decode())
                printfn(self.screen.readbuffer())

        if not self.ptyproc.closed:
            self.ptyproc.close()
        return self.ptyproc.exitstatus

    def _write(self, data, flush=False):
        return self.ptyproc.write(data, flush=flush)

    def _read(self, n=1024):
        if self.ptyproc.fd < 0:
            return SpecialConstants.EOF

        (rlist, wlist, xlist) = select.select([self.ptyproc.fd], [], [], 0)
        if rlist:
            try:
                return os.read(self.ptyproc.fd, n)
            except OSError:
                return SpecialConstants.EOF
        else:
            return b""

    def _continue_read(self):
        return not self.ptyproc.eof()

    def send(self, line, lf=b"\n"):
        self.line_itr.exhaust_buffer()

        if isinstance(line, str):
            line = line.encode()
        if isinstance(lf, str):
            lf = lf.encode()

        self._write(line)
        self._write(lf, flush=True)

    def _read_pty_raw(self, timeout=0):
        """
        Returns whatever is in the proc fd buffer.
        """
        buf = b""
        while self._continue_read():
            b = self._read(1024)
            if b is SpecialConstants.EOF:
                if len(buf) == 0:
                    return SpecialConstants.EOF
                else:
                    return buf
            if len(b) == 0:
                return buf

            buf += b

        if not self._continue_read() and len(buf) == 0:
            return SpecialConstants.EOF

        return buf

    def _read_pty(self):
        buf = self._read_pty_raw()
        if buf is SpecialConstants.EOF:
            return SpecialConstants.EOF

        if len(buf) == 0:
            return ""

        self.stream.feed(buf.decode())

        text = self.screen.readbuffer()
        return text

    def expect(self, regex, echo=True, printfn=None):
        (res, i) = self.expect_match(regex, echo, printfn) or (None, None)
        return i

    def expect_match(
        self, regex, echo=True, printfn=None
    ) -> Union[Tuple[re.compile, int], SpecialConstants]:
        if not printfn:
            printfn = self._default_print

        if not isinstance(regex, Iterable) or isinstance(regex, str):
            regex = [regex]

        for (i, r) in enumerate(regex):
            if isinstance(r, str):
                regex[i] = re.compile(r)

        self.current_output_lines = []

        while True:
            itr = self.line_itr

            res = itr.next_line(match_re=regex)
            if res is not SpecialConstants.NO_LINE:
                self.line_history.append(res)

            if isinstance(res, tuple):
                r_ex, i, line, match = res
                if echo:
                    printfn(line)

                if match:
                    return match, i

                self.current_output_lines.append(line)

            if isinstance(res, SpecialConstants):
                if res == SpecialConstants.EOF:
                    if SpecialConstants.EOF not in regex:
                        raise ShellExpectEOF()
                    return SpecialConstants.EOF, regex.index(SpecialConstants.EOF)
        return None


class RemotePtyShellExpect(PtyShellExpect):
    def __init__(self, stdin, stdout, echo=True):
        super().__init__(None, echo=echo)
        self.stdin = stdin
        self.stdout = stdout

        self.chan = self.stdout.channel

        self.chan.setblocking(True)
        self.chan.settimeout(0.0)

    def _continue_read(self):
        return not self.chan.exit_status_ready()

    # ChannelFile.read() has different behavior than conventional files.
    # So we need to read one byte at a time, until socket.timeout
    def _read1byte(self):
        try:
            b = self.stdout.read(1)
            if len(b) == 0:
                return SpecialConstants.EOF
            else:
                return b
        except socket.timeout:
            return b""

    def _read(self, n=1024):
        buf = b""

        while n > 0:
            b = self._read1byte()
            if b is SpecialConstants.EOF:
                if len(buf) == 0:
                    return SpecialConstants.EOF
                return buf
            if len(b) == 0:
                return buf
            buf += b
            n -= 1

        return buf

    def _write(self, data, flush=False):
        try:
            self.stdin.write(data)
        except socket.timeout:
            pass

    def exit_status_ready(self):
        return self.chan.exit_status_ready()

    def wait_exit_status(self, echo=True, printfn=None):
        if not printfn:
            printfn = self._default_print

        while not self.chan.exit_status_ready():
            buf = self._read_pty_raw(0.01)
            if isinstance(buf, (bytes, str)) and len(buf) > 0:
                self.stream.feed(buf.decode())
                printfn(self.screen.readbuffer())
            if buf is SpecialConstants.EOF:
                break

        if not self.chan.exit_status_ready():
            return -1

        return self.chan.recv_exit_status()
