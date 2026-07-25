"""
Persistent Foma subprocess management and notebook-cell parsing.

This module contains no Jupyter-specific code. It is responsible for:

- starting and closing the Foma subprocess;
- parsing notebook cells into ordinary programs or apply operations;
- executing ordinary Foma commands sequentially;
- preserving command output in execution order;
- applying the top network upward or downward;
- interrupting a running Foma operation;
- restarting Foma when recovery is impossible.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Literal

import pexpect


CellKind = Literal["program", "apply_up", "apply_down", "empty"]

FOMA_PROMPT = re.compile(r"foma\[\d+\]:\s*")
APPLY_PROMPT = re.compile(r"apply (?:up|down)>\s*")


@dataclass(frozen=True)
class Directives:
    """Notebook display directives found in a cell."""

    net: bool = False
    dot: bool = False
    source: bool = False


@dataclass(frozen=True)
class ParsedCell:
    """The session-level interpretation of a notebook cell."""

    kind: CellKind
    source: str
    directives: Directives = Directives()


@dataclass(frozen=True)
class CommandResult:
    """Output produced by one ordinary Foma command."""

    command: str
    output: str


class FomaError(RuntimeError):
    """Base class for errors involving a Foma session."""


class CellSyntaxError(FomaError):
    """A notebook cell does not have an accepted form."""


class FomaProcessError(FomaError):
    """The Foma subprocess exited or could not be recovered."""


class FomaTimeoutError(FomaProcessError):
    """Foma did not return an expected prompt in time."""


class FomaCommandError(FomaError):
    """Foma reported an error while executing a command."""

    def __init__(self, command: str, output: str) -> None:
        self.command = command
        self.output = output

        message = f"Foma reported an error while executing: {command}"
        if output:
            message = f"{message}\n{output}"

        super().__init__(message)


def parse_cell(code: str) -> ParsedCell:
    """Parse a notebook cell."""

    if not isinstance(code, str):
        raise TypeError("cell source must be a string")

    program_lines: list[str] = []
    net = False
    dot = False
    show_source = False

    for line in code.splitlines():
        stripped = line.strip()

        if stripped == "%net":
            net = True
        elif stripped == "%dot":
            dot = True
        elif stripped == "%source":
            show_source = True
        else:
            program_lines.append(line)

    directives = Directives(net=net, dot=dot, source=show_source)

    nonblank_lines = [line.strip() for line in program_lines if line.strip()]

    if not nonblank_lines:
        return ParsedCell(kind="empty", source="", directives=directives)

    first_line = nonblank_lines[0]

    if first_line in {"apply up", "apply down"}:
        if len(nonblank_lines) == 1:
            raise CellSyntaxError(
                f"{first_line!r} must be followed by one input string"
            )

        if len(nonblank_lines) > 2:
            raise CellSyntaxError(
                "An apply cell accepts exactly one input line in version 0.1"
            )

        input_text = nonblank_lines[1]
        if not input_text:
            raise CellSyntaxError(
                "The input string for an apply cell may not be empty"
            )

        kind: CellKind = "apply_up" if first_line == "apply up" else "apply_down"
        return ParsedCell(kind=kind, source=input_text, directives=directives)

    source = "\n".join(program_lines).strip()
    return ParsedCell(kind="program", source=source, directives=directives)


def split_foma_commands(source: str) -> list[str]:
    """Split ordinary Foma source into commands at semicolons."""

    commands: list[str] = []
    buffer: list[str] = []

    for character in source:
        buffer.append(character)
        if character == ";":
            command = "".join(buffer).strip()
            buffer.clear()
            if command:
                commands.append(command)

    final_command = "".join(buffer).strip()
    if final_command:
        commands.append(final_command)

    return commands


class FomaSession:
    """A persistent interactive Foma subprocess."""

    def __init__(
        self,
        executable: str = "foma",
        *,
        startup_timeout: float = 10.0,
        recovery_timeout: float = 2.0,
        execution_timeout: float | None = None,
        encoding: str = "utf-8",
    ) -> None:
        self.executable = executable
        self.startup_timeout = startup_timeout
        self.recovery_timeout = recovery_timeout
        self.execution_timeout = execution_timeout
        self.encoding = encoding

        self.child: pexpect.spawn | None = None
        self._start_process()

    @property
    def is_alive(self) -> bool:
        return self.child is not None and self.child.isalive()

    def _start_process(self) -> None:
        try:
            child = pexpect.spawn(
                self.executable,
                encoding=self.encoding,
                timeout=self.startup_timeout,
                echo=False,
            )
        except Exception as error:
            raise FomaProcessError(
                f"Could not start Foma executable {self.executable!r}"
            ) from error

        self.child = child

        try:
            child.expect(FOMA_PROMPT)
        except pexpect.TIMEOUT as error:
            self._close_child()
            raise FomaTimeoutError(
                "Foma started but did not display its initial prompt"
            ) from error
        except pexpect.EOF as error:
            startup_output = _clean_output(child.before)
            self._close_child()
            message = "Foma exited before displaying its initial prompt"
            if startup_output:
                message = f"{message}\n{startup_output}"
            raise FomaProcessError(message) from error

    def _require_child(self) -> pexpect.spawn:
        if self.child is None or not self.child.isalive():
            raise FomaProcessError("The Foma subprocess is not running")
        return self.child

    def execute(self, source: str) -> str:
        results = self.execute_commands(source)
        return "\n".join(result.output for result in results if result.output)

    def run(self, source: str) -> None:
        """
        Execute a command and print its output.
        """
        output = self.execute(source)
        if output:
            print(output)

    def execute_commands(self, source: str) -> list[CommandResult]:
        commands = split_foma_commands(source)
        results: list[CommandResult] = []

        for command in commands:
            output = self._execute_command(command)
            results.append(CommandResult(command=command, output=output))

            if _looks_like_foma_error(output):
                raise FomaCommandError(command=command, output=output)

        return results

    def _execute_command(self, command: str) -> str:
        child = self._require_child()
        child.sendline(command)

        try:
            child.expect(FOMA_PROMPT, timeout=self.execution_timeout)
        except KeyboardInterrupt:
            self.interrupt()
            raise
        except pexpect.TIMEOUT as error:
            raise FomaTimeoutError(
                f"Foma did not finish executing: {command}"
            ) from error
        except pexpect.EOF as error:
            output = _clean_output(child.before, command=command)
            raise FomaProcessError(_process_exit_message(command, output)) from error

        return _clean_output(child.before, command=command)

    def print_net(self) -> str:
        return self._execute_command("print net")

    def print_dot(self) -> str:
        return self._execute_command("print dot")

    def apply_down(self, text: str) -> str:
        return self._apply("down", text)

    def apply_up(self, text: str) -> str:
        return self._apply("up", text)

    def _apply(self, direction: Literal["up", "down"], text: str) -> str:
        if direction not in {"up", "down"}:
            raise ValueError(f"direction must be 'up' or 'down', not {direction!r}")

        if "\n" in text or "\r" in text:
            raise ValueError("apply input must contain exactly one line")

        if not text:
            raise ValueError("apply input may not be empty")

        child = self._require_child()
        child.sendline(f"apply {direction}")

        try:
            child.expect(APPLY_PROMPT, timeout=self.execution_timeout)
            child.sendline(text)
            child.expect(APPLY_PROMPT, timeout=self.execution_timeout)

            output = _clean_output(child.before, command=text)

            child.sendeof()
            child.expect(FOMA_PROMPT, timeout=self.recovery_timeout)

            return output

        except KeyboardInterrupt:
            self.interrupt()
            raise
        except pexpect.TIMEOUT as error:
            recovered = self._recover_from_apply_mode()
            if not recovered:
                self.restart()
            raise FomaTimeoutError(
                f"Foma did not finish apply {direction}"
            ) from error
        except pexpect.EOF as error:
            output = _clean_output(child.before)
            raise FomaProcessError(
                _process_exit_message(f"apply {direction}", output)
            ) from error

    def _recover_from_apply_mode(self) -> bool:
        if not self.is_alive:
            return False

        child = self._require_child()
        child.sendeof()

        try:
            child.expect(FOMA_PROMPT, timeout=self.recovery_timeout)
            return True
        except (pexpect.TIMEOUT, pexpect.EOF):
            return False

    def interrupt(self) -> bool:
        if not self.is_alive:
            self.restart()
            return False

        child = self._require_child()
        child.sendintr()

        try:
            matched = child.expect(
                [FOMA_PROMPT, APPLY_PROMPT, pexpect.EOF],
                timeout=self.recovery_timeout,
            )
        except pexpect.TIMEOUT:
            self.restart()
            return False

        if matched == 0:
            return True

        if matched == 1:
            child.sendeof()
            try:
                child.expect(FOMA_PROMPT, timeout=self.recovery_timeout)
                return True
            except (pexpect.TIMEOUT, pexpect.EOF):
                self.restart()
                return False

        self.restart()
        return False

    def reset(self) -> None:
        self.restart()

    def restart(self) -> None:
        self._close_child()
        self._start_process()

    def close(self) -> None:
        self._close_child()

    def _close_child(self) -> None:
        child = self.child
        self.child = None

        if child is None:
            return

        if not child.isalive():
            child.close()
            return

        try:
            child.sendline("quit")
            child.expect(pexpect.EOF, timeout=self.recovery_timeout)
        except (pexpect.TIMEOUT, pexpect.EOF):
            pass
        finally:
            if child.isalive():
                child.close(force=True)
            else:
                child.close()

    def __enter__(self) -> "FomaSession":
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()


def _clean_output(output: str | None, *, command: str | None = None) -> str:
    """Normalize output and remove an exact leading command echo."""

    if not output:
        return ""

    normalized = output.replace("\r\n", "\n").replace("\r", "\n")
    lines = normalized.splitlines()

    while lines and not lines[0]:
        lines.pop(0)

    if command is not None and lines and lines[0].strip() == command.strip():
        lines.pop(0)

    while lines and not lines[-1]:
        lines.pop()

    return "\n".join(lines)


_FOMA_ERROR_PATTERN = re.compile(
    r"""
    ^\s*
    (?:
        error\b
        |
        syntax\s+error\b
        |
        unknown\s+command\b
        |
        invalid\s+command\b
    )
    """,
    re.IGNORECASE | re.MULTILINE | re.VERBOSE,
)


def _looks_like_foma_error(output: str) -> bool:
    return bool(_FOMA_ERROR_PATTERN.search(output))


def _process_exit_message(command: str, output: str) -> str:
    message = f"Foma exited while executing: {command}"
    if output:
        message = f"{message}\n{output}"
    return message

