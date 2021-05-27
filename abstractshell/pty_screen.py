import pyte
import io
import time
import select
import os

from enum import Enum
from functools import partial


class PtyConstants(Enum):
    NO_LINE = "--no-line--"


NO_LINE = PtyConstants.NO_LINE


class TextBufferScreen(pyte.Screen):
    def __init__(self, debug=False):
        super().__init__(80, 25)
        self.buffer = io.StringIO()
        self.title = ""
        self._debug = debug

        for fn in cursor_functions:
            setattr(self, fn, partial(generic_cursor_control, self))
        for fn in functions:
            setattr(self, fn, partial(generic_fn, self))

    def debug(self, *args, **kwargs):
        if self._debug:
            print("debug function:", args, kwargs)

        self.buffer.write("\r\n")
        pass

    def draw(self, text, *args, **kwargs):
        self.buffer.write(text)
        if self._debug:
            print(f"drawing '{text}'")

    def readbuffer(self):
        val = self.buffer.getvalue()
        self.buffer = io.StringIO()
        return val

    def erase_in_display(self, how=0, *args, **kwargs):
        if how >= 2:
            self.buffer.close()
            self.buffer = io.StringIO()

        elif how == 0:
            if self._debug:
                print("ERASE LINE", args, kwargs)
        elif how == 1:
            if self._debug:
                print("ERASE TO CURSOR", args, kwargs)
        else:
            if self._debug:
                print("HOW NOT SUPPORT", how, args, kwargs)

    def carriage_return(self):
        self.buffer.write("\r")
        if self._debug:
            print("CR")

    def linefeed(self):
        self.buffer.write("\n")
        if self._debug:
            print("LF")

    def set_title(self, title):
        self.title = title
        if self._debug:
            print("set_title", title)

    def backspace(self):
        self.buffer.write("\b")
        if self._debug:
            print("backspace char")

    def tab(self):
        self.buffer.write("\t")
        if self._debug:
            print("tab char")


def generic_cursor_control(*args, **kwargs):
    pass


def generic_fn(self, *args, **kwargs):
    pass


cursor_functions = [
    "cursor_to_column",
    "cursor_back",
    "cursor_down",
    "cursor_down1",
    "cursor_forward",
    "cursor_position",
    "cursor_to_column",
    "cursor_to_line",
    "cursor_up",
    "cursor_up1",
]

functions = [
    "alignment_display",
    "bell",
    "clear_tab_stop",
    "define_charset",
    "delete_characters",
    "delete_lines",
    "erase_characters",
    "erase_in_line",
    "index",
    "insert_characters",
    "insert_lines",
    "report_device_attributes",
    "report_device_status",
    "reset",
    "reset_mode",
    "restore_cursor",
    "reverse_index",
    "save_cursor",
    "select_graphic_rendition",
    "set_icon_name",
    "set_margins",
    "set_mode",
    "set_tab_stop",
    "shift_in",
    "shift_out",
    "set_alternate_keypad",
    "set_number_keypad",
]
