# REPLs in Jupyter notebooks for FST languages
The languages in the FST family (xfst, foma, hfst-xfst, and sfst) are used with command line interfaces in the form of read-eval-print loops. Finite state machines representing regular sets of strings and regular relations between strings are defined using straight-line progams.

This repositiory provides REPL functionality in jupyter notebooks, in two forms.  Foma_kernel is a jupyter kernal that provides foma and markup cells.  Foma_notebook.py allows foma to be incorporated into python cells, using cell magic.

Currently foma is supported. Both versions allow for graphical display of machines using dot diagrams.


## Repository structure
```
├── foma_kernel
│   ├── foma_kernel
│   │   ├── __init__.py
│   │   ├── __main__.py
│   │   ├── kernel.py
│   │   ├── kernelspec
│   │   │   └── kernel.json
│   │   ├── session.py
│   └── pyproject.toml
├── foma_notebook.py
└── README.md

```

## Development process

Design and implementation were carried out by Mats Rooth with
substantial assistance from ChatGPT (OpenAI, GPT-5.5) through an
iterative design, implementation, and code-review process.

