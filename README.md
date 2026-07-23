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

## 3D Ring topology and compute-interleaving experiment

The reproducible TP/PP/DP Ring experiment lives in [experiments/ring_3d](experiments/ring_3d). It generates Chakra ET workloads with explicit `parallelism_domain` attributes, native Ring All-Reduce process groups, pipeline send/receive pairs where $PP>1$, and typed DP gradient buckets. The smoke profile is $TP=2$, $PP=2$, $DP=2$; the CI-scale Llama 3 70B-class profile is $TP=8$, $PP=1$, $DP=2$ over 16 ranks.

All Python entry points must use the committed uv environment. Generate inputs only:

```sh
uv run --locked python experiments/ring_3d/generate.py \
	--profile experiments/ring_3d/profiles/smoke_8.json \
	--output runs/ring_3d/smoke_8 --clean
```

After building the ns-3 `AstraSimNetwork` target, run and analyze the smoke experiment with `bash experiments/ring_3d/smoke.sh`. The runner writes generated inputs, ns-3 output, `flow_events.csv`, `collective_events.csv`, `rank_completion.csv`, and `summary.json` under `runs/ring_3d/smoke_8`. `collective_events.csv` records native issue-to-completion timing once per rank and logical collective, so it is the source for whole-collective latency rather than individual-QP FCT.

The optional data-parallel logical shedding policy is hard-whitelisted to Chakra operations marked `dp`, `CollectivePayload`, and `All_Reduce`. A selected flow is represented by a reliable 64-byte provenance-control QP on priority group 1; it is not a packet drop. The control completion resolves both the original logical send and receive while telemetry reports the original logical bytes separately from physically modeled control bytes. The default policy selects 0% of eligible flows in step 1 and 10% in steps 2 and 3. Deterministic host-originated RDMA microbursts are triggered by the first step-2 DP All-Reduce admission.

The CI also materializes and executes `llama3_70b_16.json`: a 70B-class FP16 gradient-bucket workload over $TP=8$, $PP=1$, and $DP=2$. It uses one representative 1 GiB typed DP All-Reduce bucket per rank and step, 4 KiB RoCE payloads, and seven simultaneous 128 MiB cross-rack RDMA microbursts toward rank 8. Five matched baseline/policy pairs run under a 160-minute guard. They fail closed unless every run records background traffic, a nonzero queue peak, and a completed PFC pause interval. This is packet-level evidence for one industry-relevant bucket spike, not a claim to replay a complete 70B-model gradient synchronization.

This is an ASTRA-sim 2.0 experiment. It models ET dependencies, native collectives, and the bundled ns-3/RDMA topology; it does not claim ASTRA-sim 3.0 InfraGraph/cache-line behavior or exact Megatron runtime fidelity.


### Releases and Contributions

ASTRA-sim is currently at **version 2.0.**
The previous version, ASTRA-sim 1.0, is available in the `ASTRA-sim-1.0` [branch](https://github.com/astra-sim/astra-sim/tree/ASTRA-sim-1.0).

We encourage community contributions to ASTRA-sim via PRs.


## Contact Us
For any questions about using ASTRA-sim, you can email the ASTRA-sim User Mailing List: astrasim-users@googlegroups.com

To join the mailing list, please fill out the following form: https://forms.gle/18KVS99SG3k9CGXm6


We appreciate your interest and support in ASTRA-sim!
