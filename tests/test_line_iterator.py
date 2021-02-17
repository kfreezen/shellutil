import pytest

from io import StringIO
from abstractshell.shell_expect import SpecialConstants, PtyShellExpect
from abstractshell import shell_expect


class MockInteraction(PtyShellExpect):
    def __init__(self, pty_input):
        super().__init__(None, echo=True)
        self.pty_input = StringIO(pty_input)

    def _read_pty(self):
        return self.pty_input.read() or SpecialConstants.EOF

    def _write(self, line, flush=False):
        pass

    def feed_pty(self, pty_input):
        l = self.pty_input.write(pty_input)
        self.pty_input.seek(self.pty_input.tell() - l)


class TestInteraction:
    def test_expect_simple_case(self):
        interact = MockInteraction("Test Output\r\n")

        res1 = interact.expect([shell_expect.EOF, "Test Output"])
        res2 = interact.expect([shell_expect.EOF, "Test Output"])
        assert res1 == 1
        assert res2 == 0

    def test_send_faked_screen(self):
        interact = MockInteraction("[test-user@malehorse ~]$ ")
        interact.send("test")

        interact.feed_pty("\r\nTest Output")
        res = interact.expect([shell_expect.PROMPT, "Test Output"])
        assert res == 1

    def test_eof_exception(self):
        interact = MockInteraction("")
        with pytest.raises(shell_expect.ShellExpectEOF) as ctx:
            interact.expect("TEST ME")

    def test_expect_lf_only(self):
        interact = MockInteraction("Test Output\n")

        res1 = interact.expect([shell_expect.EOF, "Test Output"])
        res2 = interact.expect([shell_expect.EOF, "Test Output"])
        assert res1 == 1
        assert res2 == 0

    def test_current_output(self):
        interact = MockInteraction("BEGIN\r\nHello World\r\nEND\r\n")
        res = interact.expect(["BEGIN", "END"])
        assert res == 0

        interact.expect("END")
        assert interact.current_output == "Hello World\r\n"

        interact.expect(shell_expect.EOF)


class TestLineIterator:
    def test_exhaust_buffer(self):
        interact = MockInteraction("HELLO WORLD")

        assert interact.line_itr.exhaust_buffer() == "HELLO WORLD"
        assert interact.line_itr.exhaust_buffer() == shell_expect.EOF
