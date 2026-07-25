"""Launch the Foma Jupyter kernel."""

from ipykernel.kernelapp import IPKernelApp

from .kernel import FomaKernel


def main() -> None:
    """Launch the kernel application."""
    IPKernelApp.launch_instance(kernel_class=FomaKernel)


if __name__ == "__main__":
    main()

