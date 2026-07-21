# ASTRA-sim
[ASTRA-sim](https://astra-sim.github.io/) is a distributed AI system simulator. It models the end-to-end software and hardware stack of modern AI systems - encompassing workload scheduling, collective communication algorithms, and hardware architectures (compute/memory/network). Through a suite of APIs, it enables plug-and-play of external open/proprietary components for modeling different parts of the AI system. This provides end-to-end multi-fidelity simulation capabilities for aiding in design and deployment of next-generation distributed AI systems. 


### Overview and Documentation
Here is a concise visual summary of ASTRA-sim, showing its layers and APIs:
![alt text](https://github.com/astra-sim/astra-sim/blob/master/docs/images/astrasim_overview_codesign.png)

For a comprehensive understanding of the tool, and to gain insights into its capabilities, please visit our [website](https://astra-sim.github.io/).

For information on how to use ASTRA-sim, please visit our [Wiki](https://astra-sim.github.io/astra-sim-docs/index.html).

ASTRA-sim accepts MLCommons Chakra Execution Traces as workload-layer inputs. For details, please visit [Chakra Github](https://github.com/mlcommons/chakra).

## Development setup

The Python tooling has one supported environment path: [uv](https://docs.astral.sh/uv/). Do not use `pip`, `pip3`, manually-created virtual environments, or Python packages installed into the system interpreter. The committed `uv.lock` is the complete, reproducible dependency graph for Chakra tooling and trace conversion.

Install the native build prerequisites for the selected backend (a C++17 compiler, CMake, Protobuf and Boost; MPI is needed by the ns-3 backend), then install [uv](https://docs.astral.sh/uv/getting-started/installation/). From the repository root, run:

```sh
./utils/setup.sh
```

The setup script initializes every pinned Git submodule and runs `uv sync --locked`. It uses the project-selected CPython 3.11 and creates `.venv`; no activation is necessary. Project-owned Python entry points run through uv; for example, use `./tests/rt_template/inputs/workload/gen.sh` to generate the regression traces. Dependency changes must update both `pyproject.toml` and `uv.lock` with `uv lock`; normal builds and CI reject an out-of-date lock.

The legacy `utils/install_chakra.sh` entry point remains as a compatibility wrapper and delegates to the same uv workflow. The Docker image also synchronizes this exact lockfile with uv; build it through `./utils/build_docker_image.sh`.


### Releases and Contributions

ASTRA-sim is currently at **version 2.0.**
The previous version, ASTRA-sim 1.0, is available in the `ASTRA-sim-1.0` [branch](https://github.com/astra-sim/astra-sim/tree/ASTRA-sim-1.0).

We encourage community contributions to ASTRA-sim via PRs.


## Contact Us
For any questions about using ASTRA-sim, you can email the ASTRA-sim User Mailing List: astrasim-users@googlegroups.com

To join the mailing list, please fill out the following form: https://forms.gle/18KVS99SG3k9CGXm6


We appreciate your interest and support in ASTRA-sim!
