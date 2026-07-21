#!/usr/bin/env python3
"""Materialize reproducible Chakra traces and ns-3 inputs for 3D Ring runs.

Run only through the repository's locked environment:

    uv run --locked python experiments/ring_3d/generate.py --profile ... --output ...
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from chakra.schema.protobuf.et_def_pb2 import (  # noqa: E402
    ALL_REDUCE,
    COMM_COLL_NODE,
    COMM_RECV_NODE,
    COMM_SEND_NODE,
    COMP_NODE,
    AttributeProto,
    GlobalMetadata,
    Node,
)
from chakra.src.third_party.utils.protolib import (  # noqa: E402
    encodeMessage,
)


EXPECTED_PROFILE_KEYS = {
    "schema_version",
    "name",
    "parallelism",
    "steps",
    "compute_duration_us",
    "tp_all_reduce_bytes",
    "pp_bytes",
    "dp_all_reduce_bytes",
    "seed",
    "network",
    "microburst_bytes",
}
EXPECTED_NETWORK_KEYS = {"hosts_per_leaf", "spine_count", "link_rate"}


@dataclass(frozen=True)
class Profile:
    name: str
    tp: int
    pp: int
    dp: int
    steps: int
    compute_duration_us: int
    tp_all_reduce_bytes: int
    pp_bytes: int
    dp_all_reduce_bytes: int
    seed: int
    hosts_per_leaf: int
    spine_count: int
    link_rate: str
    microburst_bytes: int

    @property
    def ranks(self) -> int:
        return self.tp * self.pp * self.dp


def _require_positive_int(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{field} must be a positive integer")
    return value


def load_profile(profile_path: Path) -> Profile:
    with profile_path.open(encoding="utf-8") as handle:
        document = json.load(handle)
    if not isinstance(document, dict):
        raise ValueError("profile must be a JSON object")
    unknown_keys = set(document) - EXPECTED_PROFILE_KEYS
    if unknown_keys:
        raise ValueError(f"unknown profile keys: {sorted(unknown_keys)}")
    if document.get("schema_version") != 1:
        raise ValueError("profile schema_version must be 1")

    parallelism = document.get("parallelism")
    if not isinstance(parallelism, dict) or set(parallelism) != {"tp", "pp", "dp"}:
        raise ValueError("parallelism must contain exactly tp, pp, and dp")
    network = document.get("network")
    if not isinstance(network, dict) or set(network) != EXPECTED_NETWORK_KEYS:
        raise ValueError("network must contain hosts_per_leaf, spine_count, and link_rate")

    name = document.get("name")
    if not isinstance(name, str) or not name:
        raise ValueError("name must be a nonempty string")
    if document.get("steps") != 3:
        raise ValueError("this experiment requires exactly three training steps")
    link_rate = network.get("link_rate")
    if not isinstance(link_rate, str) or not link_rate.endswith("Gbps"):
        raise ValueError("network.link_rate must be a rate such as 200Gbps")

    profile = Profile(
        name=name,
        tp=_require_positive_int(parallelism["tp"], "parallelism.tp"),
        pp=_require_positive_int(parallelism["pp"], "parallelism.pp"),
        dp=_require_positive_int(parallelism["dp"], "parallelism.dp"),
        steps=3,
        compute_duration_us=_require_positive_int(
            document.get("compute_duration_us"), "compute_duration_us"
        ),
        tp_all_reduce_bytes=_require_positive_int(
            document.get("tp_all_reduce_bytes"), "tp_all_reduce_bytes"
        ),
        pp_bytes=_require_positive_int(document.get("pp_bytes"), "pp_bytes"),
        dp_all_reduce_bytes=_require_positive_int(
            document.get("dp_all_reduce_bytes"), "dp_all_reduce_bytes"
        ),
        seed=_require_positive_int(document.get("seed"), "seed"),
        hosts_per_leaf=_require_positive_int(
            network["hosts_per_leaf"], "network.hosts_per_leaf"
        ),
        spine_count=_require_positive_int(network["spine_count"], "network.spine_count"),
        link_rate=link_rate,
        microburst_bytes=_require_positive_int(
            document.get("microburst_bytes"), "microburst_bytes"
        ),
    )
    if profile.ranks % profile.hosts_per_leaf:
        raise ValueError("parallelism product must be divisible by network.hosts_per_leaf")
    if profile.spine_count > 255:
        raise ValueError("network.spine_count must not exceed 255")
    return profile


def rank_for(tp_rank: int, pp_rank: int, dp_rank: int, profile: Profile) -> int:
    """Return a TP-fastest global rank."""
    if not (0 <= tp_rank < profile.tp and 0 <= pp_rank < profile.pp and 0 <= dp_rank < profile.dp):
        raise ValueError("parallelism coordinate is outside the profile")
    return ((dp_rank * profile.pp) + pp_rank) * profile.tp + tp_rank


def coordinates_for(rank: int, profile: Profile) -> tuple[int, int, int]:
    """Invert the TP-fastest rank mapping as (tp_rank, pp_rank, dp_rank)."""
    if not 0 <= rank < profile.ranks:
        raise ValueError("rank is outside the profile")
    tp_rank = rank % profile.tp
    pp_rank = (rank // profile.tp) % profile.pp
    dp_rank = rank // (profile.tp * profile.pp)
    return tp_rank, pp_rank, dp_rank


def generate_groups(profile: Profile) -> tuple[dict[str, list[int]], dict[str, int], dict[str, int], dict[str, int]]:
    """Generate explicit TP, PP, and DP communicator membership and lookup IDs."""
    groups: dict[str, list[int]] = {}
    tp_group_for_rank: dict[str, int] = {}
    pp_group_for_rank: dict[str, int] = {}
    dp_group_for_rank: dict[str, int] = {}
    next_group_id = 1

    for dp_rank in range(profile.dp):
        for pp_rank in range(profile.pp):
            members = [rank_for(tp_rank, pp_rank, dp_rank, profile) for tp_rank in range(profile.tp)]
            groups[str(next_group_id)] = members
            for rank in members:
                tp_group_for_rank[str(rank)] = next_group_id
            next_group_id += 1

    for dp_rank in range(profile.dp):
        for tp_rank in range(profile.tp):
            members = [rank_for(tp_rank, pp_rank, dp_rank, profile) for pp_rank in range(profile.pp)]
            groups[str(next_group_id)] = members
            for rank in members:
                pp_group_for_rank[str(rank)] = next_group_id
            next_group_id += 1

    for pp_rank in range(profile.pp):
        for tp_rank in range(profile.tp):
            members = [rank_for(tp_rank, pp_rank, dp_rank, profile) for dp_rank in range(profile.dp)]
            groups[str(next_group_id)] = members
            for rank in members:
                dp_group_for_rank[str(rank)] = next_group_id
            next_group_id += 1

    expected_group_count = profile.dp * profile.pp + profile.dp * profile.tp + profile.pp * profile.tp
    if len(groups) != expected_group_count:
        raise AssertionError("unexpected communicator group count")
    return groups, tp_group_for_rank, pp_group_for_rank, dp_group_for_rank


def _attribute(name: str, **value: Any) -> AttributeProto:
    return AttributeProto(name=name, **value)


class TraceWriter:
    def __init__(self, path: Path, rank: int, profile: Profile, groups: tuple[dict[str, list[int]], dict[str, int], dict[str, int], dict[str, int]]) -> None:
        self.path = path
        self.rank = rank
        self.profile = profile
        self.coords = coordinates_for(rank, profile)
        self.groups = groups
        self.node_id = 1
        self.nodes: list[Node] = []

    def _new_node(self, name: str, node_type: int, dependencies: Iterable[int]) -> Node:
        node = Node(id=self.node_id, name=name, type=node_type)
        node.ctrl_deps.extend(dependencies)
        self.node_id += 1
        self.nodes.append(node)
        return node

    def compute(self, name: str, dependencies: Iterable[int]) -> int:
        node = self._new_node(name, COMP_NODE, dependencies)
        node.duration_micros = self.profile.compute_duration_us
        node.attr.append(_attribute("is_cpu_op", bool_val=False))
        return node.id

    def all_reduce(self, name: str, dependencies: Iterable[int], domain: str, group_id: int, size_bytes: int, step: int) -> int:
        node = self._new_node(name, COMM_COLL_NODE, dependencies)
        node.attr.extend(
            [
                _attribute("is_cpu_op", bool_val=False),
                _attribute("comm_type", int64_val=ALL_REDUCE),
                _attribute("comm_size", uint64_val=size_bytes),
                _attribute("pg_name", string_val=str(group_id)),
                _attribute("parallelism_domain", string_val=domain),
                _attribute("training_step", uint64_val=step),
            ]
        )
        return node.id

    def pipeline_node(self, name: str, node_type: int, dependencies: Iterable[int], src: int, dst: int, tag: int, step: int) -> int:
        node = self._new_node(name, node_type, dependencies)
        node.attr.extend(
            [
                _attribute("is_cpu_op", bool_val=False),
                _attribute("comm_src", uint32_val=src),
                _attribute("comm_dst", uint32_val=dst),
                _attribute("comm_tag", uint32_val=tag),
                _attribute("comm_size", uint64_val=self.profile.pp_bytes),
                _attribute("parallelism_domain", string_val="pp"),
                _attribute("training_step", uint64_val=step),
            ]
        )
        return node.id

    def build(self) -> None:
        _, tp_groups, _, dp_groups = self.groups
        tp_rank, pp_rank, dp_rank = self.coords
        predecessor: int | None = None

        for step in range(1, self.profile.steps + 1):
            forward = self.compute(
                f"step_{step}_forward_compute",
                [] if predecessor is None else [predecessor],
            )
            tp_reduce = self.all_reduce(
                f"step_{step}_tp_all_reduce",
                [forward],
                "tp",
                tp_groups[str(self.rank)],
                self.profile.tp_all_reduce_bytes,
                step,
            )

            pipeline_dependencies = [tp_reduce]
            pipeline_events: list[int] = []
            pipeline_tag = step * 100_000 + dp_rank * 1_000 + tp_rank
            if pp_rank > 0:
                source = rank_for(tp_rank, pp_rank - 1, dp_rank, self.profile)
                pipeline_events.append(
                    self.pipeline_node(
                        f"step_{step}_pp_recv_from_{source}",
                        COMM_RECV_NODE,
                        pipeline_dependencies,
                        source,
                        self.rank,
                        pipeline_tag,
                        step,
                    )
                )
            if pp_rank < self.profile.pp - 1:
                destination = rank_for(tp_rank, pp_rank + 1, dp_rank, self.profile)
                pipeline_events.append(
                    self.pipeline_node(
                        f"step_{step}_pp_send_to_{destination}",
                        COMM_SEND_NODE,
                        pipeline_dependencies,
                        self.rank,
                        destination,
                        pipeline_tag,
                        step,
                    )
                )

            bucket_zero = self.compute(
                f"step_{step}_backward_bucket_0",
                [tp_reduce, *pipeline_events],
            )
            dp_reduce_zero = self.all_reduce(
                f"step_{step}_dp_all_reduce_bucket_0",
                [bucket_zero],
                "dp",
                dp_groups[str(self.rank)],
                self.profile.dp_all_reduce_bytes,
                step,
            )
            bucket_one = self.compute(
                f"step_{step}_backward_bucket_1",
                [bucket_zero],
            )
            dp_reduce_one = self.all_reduce(
                f"step_{step}_dp_all_reduce_bucket_1",
                [bucket_one],
                "dp",
                dp_groups[str(self.rank)],
                self.profile.dp_all_reduce_bytes,
                step,
            )
            predecessor = self.compute(
                f"step_{step}_optimizer",
                [dp_reduce_zero, dp_reduce_one],
            )

    def write(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("wb") as trace:
            encodeMessage(trace, GlobalMetadata(version="0.0.4"))
            for node in self.nodes:
                encodeMessage(trace, node)


def write_clos_topology(path: Path, profile: Profile) -> None:
    """Write a two-stage Clos topology accepted by the bundled ns-3 parser."""
    leaf_count = profile.ranks // profile.hosts_per_leaf
    switch_count = leaf_count + profile.spine_count
    node_count = profile.ranks + switch_count
    edge_count = profile.ranks + leaf_count * profile.spine_count
    leaf_start = profile.ranks
    spine_start = leaf_start + leaf_count

    with path.open("w", encoding="utf-8") as topology:
        topology.write(f"{node_count} {switch_count} {edge_count}\n")
        topology.write(" ".join(str(switch) for switch in range(leaf_start, node_count)) + " \n")
        for host in range(profile.ranks):
            leaf = leaf_start + host // profile.hosts_per_leaf
            topology.write(f"{host} {leaf} {profile.link_rate} 0.005ms 0\n")
        for leaf in range(leaf_start, spine_start):
            for spine in range(spine_start, node_count):
                topology.write(f"{leaf} {spine} {profile.link_rate} 0.0125ms 0\n")


def write_network_config(path: Path, topology: Path, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    # The bundled ns-3 setup unconditionally opens these legacy input files,
    # even though ASTRA-sim dynamically creates the RDMA QPs after setup.
    # A zero count is therefore the correct empty static-flow/trace workload.
    (output_dir / "flow.txt").write_text("0\n", encoding="utf-8")
    (output_dir / "trace.txt").write_text("0\n", encoding="utf-8")
    entries = {
        "TOPOLOGY_FILE": topology,
        "FLOW_FILE": output_dir / "flow.txt",
        "TRACE_FILE": output_dir / "trace.txt",
        "TRACE_OUTPUT_FILE": output_dir / "mix.tr",
        "FCT_OUTPUT_FILE": output_dir / "fct.txt",
        "PFC_OUTPUT_FILE": output_dir / "pfc.txt",
        "QLEN_MON_FILE": output_dir / "qlen.txt",
    }
    with path.open("w", encoding="utf-8") as config:
        config.write("ENABLE_QCN 1\nUSE_DYNAMIC_PFC_THRESHOLD 1\n\nPACKET_PAYLOAD_SIZE 1000\n\n")
        for key, value in entries.items():
            config.write(f"{key} {value}\n")
        config.write(
            "QLEN_MON_START 0\nQLEN_MON_END 20000\n\n"
            "SIMULATOR_STOP_TIME 40000000000000.00\n\n"
            "CC_MODE 12\nALPHA_RESUME_INTERVAL 1\nRATE_DECREASE_INTERVAL 4\n"
            "CLAMP_TARGET_RATE 0\nRP_TIMER 900\nEWMA_GAIN 0.00390625\n"
            "FAST_RECOVERY_TIMES 1\nRATE_AI 50Mb/s\nRATE_HAI 100Mb/s\n"
            "MIN_RATE 100Mb/s\nDCTCP_RATE_AI 1000Mb/s\n\n"
            "ERROR_RATE_PER_LINK 0.0000\nL2_CHUNK_SIZE 4000\nL2_ACK_INTERVAL 1\n"
            "L2_BACK_TO_ZERO 0\n\nHAS_WIN 1\nGLOBAL_T 0\nVAR_WIN 1\n"
            "FAST_REACT 1\nU_TARGET 0.95\nMI_THRESH 0\nINT_MULTI 1\nMULTI_RATE 0\n"
            "SAMPLE_FEEDBACK 0\nPINT_LOG_BASE 1.05\nPINT_PROB 1.0\n"
            "NIC_TOTAL_PAUSE_TIME 0\n\nRATE_BOUND 1\nACK_HIGH_PRIO 0\n"
            "LINK_DOWN 0 0 0\nENABLE_TRACE 1\n\n"
            "KMAX_MAP 6 25000000000 400 40000000000 800 100000000000 1600 "
            "200000000000 2400 400000000000 3200 2400000000000 3200\n"
            "KMIN_MAP 6 25000000000 100 40000000000 200 100000000000 400 "
            "200000000000 600 400000000000 800 2400000000000 800\n"
            "PMAX_MAP 6 25000000000 0.2 40000000000 0.2 100000000000 0.2 "
            "200000000000 0.2 400000000000 0.2 2400000000000 0.2\n"
            "BUFFER_SIZE 32\n"
        )


def write_experiment_config(path: Path, profile: Profile) -> None:
    cross_rack_base = profile.ranks // 2
    flow_count = min(2, profile.ranks // 2)
    microburst_flows = [
        {
            "src": index,
            "dst": cross_rack_base + index,
            "size_bytes": profile.microburst_bytes,
            "offset_ns": index * 1_000,
            "priority_group": 3,
        }
        for index in range(flow_count)
    ]
    policy = {
        "schema_version": 1,
        "enabled": True,
        "seed": profile.seed,
        "run_id": profile.name,
        "eligibility": "dp_all_reduce_only",
        "drop_probability_by_step": {"1": 0.0, "2": 0.1, "3": 0.1},
        "default_priority_group": 3,
        "provenance": {"control_bytes": 64, "priority_group": 1},
        "vnet_to_priority_group": {"0": 3},
        "microburst": {
            "enabled": True,
            "trigger_step": 2,
            "flows": microburst_flows,
        },
    }
    path.write_text(json.dumps(policy, indent=2) + "\n", encoding="utf-8")


def write_system_config(path: Path) -> None:
    configuration = {
        "scheduling-policy": "LIFO",
        "endpoint-delay": 10,
        "active-chunks-per-dimension": 1,
        "preferred-dataset-splits": 4,
        "all-reduce-implementation": ["ring"],
        "all-gather-implementation": ["ring"],
        "reduce-scatter-implementation": ["ring"],
        "all-to-all-implementation": ["ring"],
        "collective-optimization": "localBWAware",
        "local-mem-bw": 1600,
        "boost-mode": 0,
        "roofline-enabled": 0,
        "peak-perf": 900,
    }
    path.write_text(json.dumps(configuration, indent=2) + "\n", encoding="utf-8")


def materialize(profile_path: Path, output_dir: Path, clean: bool = False) -> dict[str, str]:
    profile = load_profile(profile_path)
    if output_dir.exists() and clean:
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    groups, tp_groups, pp_groups, dp_groups = generate_groups(profile)
    workload_dir = output_dir / "workload"
    for rank in range(profile.ranks):
        writer = TraceWriter(
            workload_dir / f"ring_3d.{rank}.et",
            rank,
            profile,
            (groups, tp_groups, pp_groups, dp_groups),
        )
        writer.build()
        writer.write()

    topology = output_dir / "topology.txt"
    write_clos_topology(topology, profile)
    network_config = output_dir / "network_config.txt"
    write_network_config(network_config, topology.resolve(), output_dir / "ns3")
    experiment_config = output_dir / "experiment.json"
    write_experiment_config(experiment_config, profile)
    system_config = output_dir / "system.json"
    write_system_config(system_config)
    (output_dir / "communicator_groups.json").write_text(
        json.dumps(groups, indent=2) + "\n", encoding="utf-8"
    )
    (output_dir / "logical_topology.json").write_text(
        json.dumps({"logical-dims": [str(profile.ranks)]}, indent=2) + "\n",
        encoding="utf-8",
    )
    (output_dir / "remote_memory.json").write_text(
        json.dumps({"memory-type": "NO_MEMORY_EXPANSION"}, indent=2) + "\n",
        encoding="utf-8",
    )

    manifest = {
        "profile": profile.name,
        "ranks": profile.ranks,
        "parallelism": {"tp": profile.tp, "pp": profile.pp, "dp": profile.dp},
        "workload_prefix": str((workload_dir / "ring_3d").resolve()),
        "system_config": str(system_config.resolve()),
        "network_config": str(network_config.resolve()),
        "remote_memory_config": str((output_dir / "remote_memory.json").resolve()),
        "communicator_groups": str((output_dir / "communicator_groups.json").resolve()),
        "logical_topology": str((output_dir / "logical_topology.json").resolve()),
        "experiment_config": str(experiment_config.resolve()),
        "telemetry_dir": str((output_dir / "telemetry").resolve()),
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--clean", action="store_true", help="replace an existing output directory")
    arguments = parser.parse_args()
    manifest = materialize(arguments.profile.resolve(), arguments.output.resolve(), arguments.clean)
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())