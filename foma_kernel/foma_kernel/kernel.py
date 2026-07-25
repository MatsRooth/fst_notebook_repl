"""
Jupyter kernel for the Foma finite-state toolkit.

The kernel owns one persistent :class:`FomaSession`.  Markdown cells are
handled by the Jupyter front end; code cells are parsed and dispatched here.
"""

from __future__ import annotations

import subprocess
from typing import Any

from ipykernel.kernelbase import Kernel

from . import __version__
from .session import (
    CellSyntaxError,
    FomaCommandError,
    FomaError,
    FomaProcessError,
    FomaSession,
    FomaTimeoutError,
    ParsedCell,
    parse_cell,
)


class GraphvizError(RuntimeError):
    """DOT output could not be converted to SVG."""


def dot_to_svg(dot_source: str, executable: str = "dot") -> str:
    """Convert a DOT document to SVG using the Graphviz ``dot`` program."""

    try:
        completed = subprocess.run(
            [executable, "-Tsvg"],
            input=dot_source,
            text=True,
            capture_output=True,
            check=False,
        )
    except FileNotFoundError as error:
        raise GraphvizError(
            f"Could not find the Graphviz executable {executable!r}"
        ) from error
    except OSError as error:
        raise GraphvizError(
            f"Could not run the Graphviz executable {executable!r}"
        ) from error

    if completed.returncode != 0:
        detail = completed.stderr.strip()
        message = "Graphviz could not convert Foma's DOT output to SVG"
        if detail:
            message = f"{message}\n{detail}"
        raise GraphvizError(message)

    return completed.stdout


class FomaKernel(Kernel):
    """A minimal Jupyter wrapper kernel around a persistent Foma REPL."""

    implementation = "foma_kernel"
    implementation_version = __version__

    language = "foma"
    language_version = "0.10"
    language_info = {
        "name": "foma",
        "mimetype": "text/x-foma",
        "file_extension": ".foma",
        "codemirror_mode": "text",
        "pygments_lexer": "text",
    }

    banner = "Foma finite-state toolkit"

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.session = FomaSession()

    def do_execute(
        self,
        code: str,
        silent: bool,
        store_history: bool = True,
        user_expressions: dict[str, Any] | None = None,
        allow_stdin: bool = False,
        *,
        cell_meta: dict[str, Any] | None = None,
        cell_id: str | None = None,
    ) -> dict[str, Any]:
        """Execute one Foma notebook cell."""

        del store_history, allow_stdin, cell_meta, cell_id
        user_expressions = user_expressions or {}

        try:
            cell = parse_cell(code)
            output = self._execute_parsed_cell(cell)

            if not silent and output:
                self._publish_stream(output)

            if not silent:
                self._publish_directives(cell)

            return {
                "status": "ok",
                "execution_count": self.execution_count,
                "payload": [],
                # Foma has no equivalent of Python user expressions.
                "user_expressions": {
                    name: {
                        "status": "error",
                        "ename": "NotImplementedError",
                        "evalue": "Foma does not support user expressions",
                        "traceback": [],
                    }
                    for name in user_expressions
                },
            }

        except KeyboardInterrupt:
            return self._error_reply(
                "KeyboardInterrupt",
                "Foma execution interrupted",
                silent=silent,
            )
        except (
            CellSyntaxError,
            FomaCommandError,
            FomaTimeoutError,
            FomaProcessError,
            FomaError,
            GraphvizError,
        ) as error:
            return self._error_reply(
                type(error).__name__,
                str(error),
                silent=silent,
            )
        except Exception as error:
            # Keep an unexpected implementation error from taking down the
            # kernel, while giving the notebook a conventional error reply.
            return self._error_reply(
                type(error).__name__,
                str(error),
                silent=silent,
            )

    def _execute_parsed_cell(self, cell: ParsedCell) -> str:
        """Dispatch a parsed cell to the corresponding session operation."""

        if cell.kind == "empty":
            return ""
        if cell.kind == "program":
            return self.session.execute(cell.source)
        if cell.kind == "apply_down":
            return self.session.apply_down(cell.source)
        if cell.kind == "apply_up":
            return self.session.apply_up(cell.source)

        raise CellSyntaxError(f"Unsupported parsed cell kind: {cell.kind!r}")

    def _publish_directives(self, cell: ParsedCell) -> None:
        """Run and publish post-cell notebook display directives."""

        if cell.directives.net:
            output = self.session.print_net()
            if output:
                self._publish_stream(output)

        if cell.directives.dot:
            dot_source = self.session.print_dot()
            svg = dot_to_svg(dot_source)
            self._publish_display(
                {
                    "image/svg+xml": svg,
                    "text/plain": "Foma transducer graph",
                }
            )

        if cell.directives.source:
            source = self._source_for_display(cell)
            if source:
                self._publish_display(
                    {
                        "text/plain": source,
                        "text/x-foma": source,
                    }
                )

    @staticmethod
    def _source_for_display(cell: ParsedCell) -> str:
        """Return the Foma interaction represented by a parsed cell."""

        if cell.kind == "apply_up":
            return f"apply up\n{cell.source}"
        if cell.kind == "apply_down":
            return f"apply down\n{cell.source}"
        return cell.source

    def _publish_stream(self, text: str) -> None:
        """Publish ordinary Foma text as notebook stdout."""

        if not text.endswith("\n"):
            text += "\n"

        self.send_response(
            self.iopub_socket,
            "stream",
            {
                "name": "stdout",
                "text": text,
            },
        )

    def _publish_display(self, data: dict[str, str]) -> None:
        """Publish a Jupyter rich display value."""

        self.send_response(
            self.iopub_socket,
            "display_data",
            {
                "data": data,
                "metadata": {},
                "transient": {},
            },
        )

    def _error_reply(
        self,
        ename: str,
        evalue: str,
        *,
        silent: bool,
    ) -> dict[str, Any]:
        """Publish and return a conventional Jupyter execution error."""

        traceback = [f"{ename}: {evalue}"] if evalue else [ename]
        error = {
            "ename": ename,
            "evalue": evalue,
            "traceback": traceback,
        }

        if not silent:
            self.send_response(
                self.iopub_socket,
                "error",
                error,
            )

        return {
            "status": "error",
            "execution_count": self.execution_count,
            **error,
        }

    def do_shutdown(self, restart: bool) -> dict[str, Any]:
        """Close the child Foma process when the Jupyter kernel stops."""

        self.session.close()
        return {
            "status": "ok",
            "restart": restart,
        }

