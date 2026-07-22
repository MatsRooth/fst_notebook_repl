import subprocess
import pexpect

from IPython.display import SVG, display
from IPython.core.magic import register_cell_magic


PROMPT = r"foma\[\d+\]:"


class FomaSession:
    def __init__(self, command="foma", prompt=PROMPT, timeout=10):
        self.command = command
        self.prompt = prompt
        self.proc = pexpect.spawn(
            command,
            encoding="utf-8",
            timeout=timeout,
        )
        self.proc.expect(prompt)
        self.history = []

    def __call__(self, cmd, echo=True):
        return self.run(cmd, echo=echo)

    def run(self, cmd, echo=True):
        self.proc.sendline(cmd)
        self.proc.expect(self.prompt)

        out = self.proc.before.strip()

        # Remove echoed command line.
        lines = out.splitlines()
        if lines and lines[0].strip() == cmd.strip():
            out = "\n".join(lines[1:]).strip()

        self.history.append(cmd)

        if echo:
            print(out)

        return out

    def dot(self):
        return self.run("print dot", echo=False)

    def show_dot(self):
        dot = self.dot()
        svg = subprocess.check_output(
            ["dot", "-Tsvg"],
            input=dot.encode("utf-8"),
        )
        display(SVG(svg))

    def show_net(self):
        self.run("print net")

    def save_history(self, path):
        with open(path, "w", encoding="utf-8") as out:
            for cmd in self.history:
                out.write(cmd + "\n")

    def close(self):
        self.proc.close()


def start_foma(command="foma", timeout=10):
    return FomaSession(command=command, timeout=timeout)


def _commands_from_cell(cell):
    buf = []

    for row in cell.splitlines():
        row = row.strip()

        if not row or row.startswith("#"):
            continue

        buf.append(row)

        if ";" in row:
            yield " ".join(buf)
            buf = []

    if buf:
        yield " ".join(buf)


def register_fst_magic(session):
    @register_cell_magic
    def fst(line, cell):
        args = set(line.split())

        for cmd in _commands_from_cell(cell):
            print("----------------------------")
            session.run(cmd)

        if "--net" in args:
            print("----------------------------")
            session.show_net()

        if "--dot" in args:
            session.show_dot()

    return fst

