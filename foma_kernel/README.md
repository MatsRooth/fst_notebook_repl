# Foma Jupyter Kernel

A Jupyter kernel for the [Foma finite-state toolkit](https://fomafst.github.io/).

The kernel provides notebooks containing:

- Foma code cells executed by a persistent Foma process
- Standard Jupyter Markdown cells
- Inline textual and graphical representations of finite-state networks
- Notebook-style `apply up` and `apply down` operations

## Requirements

The following programs must be installed and available on `PATH`:

- Python 3.10 or newer
- Foma
- Graphviz, including the `dot` executable
- JupyterLab or Jupyter Notebook

Confirm the external programs are available with:

```bash
which foma
which dot
```

The Python dependencies are installed through `pyproject.toml`:

- `ipykernel`
- `pexpect`

## Installation from the repository

From the repository root:

```bash
cd foma_kernel
python -m pip install -e .
```

Register the kernel with Jupyter:

```bash
jupyter kernelspec install --user \
    --replace \
    foma_kernel/kernelspec \
    --name foma
```

The **Foma** kernel should then appear among the kernels offered by JupyterLab or Jupyter Notebook.

Install the package and register the kernel from the same Python environment used to run Jupyter.

## Basic use

A Foma code cell can contain one or more commands:

```foma
define Vowel [a | e | i | o | u];
define Cons [b | c | d];

define Syllable (Cons) Vowel;
define Word Syllable+;

regex Word;
```

The kernel maintains one persistent Foma process. Definitions, the network stack, and other Foma session state therefore survive across cell executions.

Restarting the Jupyter kernel starts a fresh Foma process and clears that state.

## Multiple commands and output

Commands in a cell are executed sequentially. Output produced by `echo`, `print`, and other Foma commands appears in its original order.

For example:

```foma
regex Cons Vowel;
echo Printing the current network;
print net
```

A literal Foma command such as `print net` is executed at its position in the cell. Notebook display directives, described below, are processed after the ordinary Foma commands have finished.

The initial parser uses simple semicolon-based command separation. The final command in a cell may omit its terminating semicolon.

## Notebook display directives

The kernel recognizes three notebook-specific directives:

```foma
%net
%dot
%source
```

A directive must occupy a line by itself. Directives are removed before the remaining source is sent to Foma.

### `%net`

Displays Foma’s textual representation of the network at the top of the stack. It is equivalent to running `print net` after the other commands in the cell.

```foma
regex Cons Vowel;
%net
```

### `%dot`

Runs `print dot` for the network at the top of the stack, converts the resulting DOT description to SVG with Graphviz, and displays the graph inline.

```foma
regex Cons Vowel;
%dot
```

### `%source`

Displays the Foma source represented by the parsed cell. This is useful for examining what the kernel executed after removing notebook directives.

```foma
regex Cons Vowel;
%source
```

Multiple directives may be used together:

```foma
regex Cons Vowel;

%net
%dot
%source
```

## Applying a network

Interactive Foma application is represented by a two-line cell.

Apply the top network downward:

```foma
apply down
cat
```

Apply the top network upward:

```foma
apply up
cats
```

The first nonblank line must be exactly `apply down` or `apply up`. The second nonblank line is the complete application string.

The initial version accepts one application string per cell. To try another string, edit the second line and execute the cell again.

## Interrupting execution

Use Jupyter’s **Interrupt Kernel** action to stop a Foma operation that is taking unexpectedly long.

The kernel first sends an interrupt to the persistent Foma process and attempts to restore its normal prompt. If recovery succeeds, definitions and stack state are preserved.

If Foma cannot be recovered, the kernel starts a new Foma subprocess. In that case, definitions and stack state from the previous Foma session are lost, while the Jupyter notebook itself remains open.

## Markdown cells

Markdown is handled directly by Jupyter and requires no special kernel support. A Foma notebook can freely combine Foma code with:

- Headings and explanatory text
- Mathematical notation
- Tables
- Links
- Images

## Current scope

The initial implementation emphasizes:

- Persistent Foma sessions
- Sequential command execution
- `apply up` and `apply down`
- Textual network display
- Graphviz SVG display
- Manual interruption and subprocess recovery

Possible later additions include command completion, contextual help, Foma syntax highlighting, and more sophisticated multiline parsing.

## Development process

Design and implementation were carried out by Mats Rooth with  
substantial assistance from ChatGPT (OpenAI, GPT-5.5) through an  
iterative design, implementation, and code-review process.
