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
from dataclasses import dataclass, replace
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


REQUIRED_PROFILE_KEYS = {
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
OPTIONAL_PROFILE_KEYS = {
    "microburst_flow_count",
    "microburst_destination_rank",
    "microburst_offset_spacing_ns",
    "microburst_source_ranks",
    "microburst_enabled",
    "model",
}
EXPECTED_PROFILE_KEYS = REQUIRED_PROFILE_KEYS | OPTIONAL_PROFILE_KEYS
REQUIRED_NETWORK_KEYS = {"hosts_per_leaf", "spine_count", "link_rate"}
OPTIONAL_NETWORK_KEYS = {
    "packet_payload_bytes",
    "queue_monitor_start_ns",
}
EXPECTED_NETWORK_KEYS = REQUIRED_NETWORK_KEYS | OPTIONAL_NETWORK_KEYS
EXPECTED_MODEL_TRACE_KEYS = {
    "parameter_count",
    "parameter_dtype_bytes",
    "transformer_layers",
    "gradient_bucket_count",
    "hidden_size",
    "sequence_length",
    "microbatch_size",
    "activation_dtype_bytes",
    "tensor_parallel_all_reduces_per_layer",
    "pipeline_microbatches",
}
GRADIENT_BUCKET_SAMPLE_MODEL_KEYS = {
    "parameter_count",
    "parameter_dtype_bytes",
    "gradient_bucket_count",
}
DEFAULT_DROP_PROBABILITY_BY_STEP = {"1": 0.0, "2": 0.1, "3": 0.1}


@dataclass(frozen=True)
class ModelTrace:
    """Structural transformer workload quantities used to derive ET nodes."""

    parameter_count: int
    parameter_dtype_bytes: int
    transformer_layers: int
    gradient_bucket_count: int
    hidden_size: int
    sequence_length: int
    microbatch_size: int
    activation_dtype_bytes: int
    tensor_parallel_all_reduces_per_layer: int
    pipeline_microbatches: int


@dataclass(frozen=True)
class GradientBucketSample:
    """Model-scale metadata for a trace that contains one representative bucket."""

    parameter_count: int
    parameter_dtype_bytes: int
    gradient_bucket_count: int


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
    packet_payload_bytes: int
    queue_monitor_start_ns: int
    microburst_bytes: int
    microburst_flow_count: int
    microburst_destination_rank: int | None
    microburst_offset_spacing_ns: int
    microburst_source_ranks: tuple[int, ...] | None
    microburst_enabled: bool
    model: ModelTrace | GradientBucketSample | None

    @property
    def ranks(self) -> int:
        return self.tp * self.pp * self.dp


def _require_positive_int(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{field} must be a positive integer")
    return value


def _require_nonnegative_int(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field} must be a nonnegative integer")
    return value


def _load_model_workload(
    document: dict[str, Any], tp: int, pp: int
) -> ModelTrace | GradientBucketSample | None:
    value = document.get("model")
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError("model must be an object")
    if set(value) == GRADIENT_BUCKET_SAMPLE_MODEL_KEYS:
        model = GradientBucketSample(
            parameter_count=_require_positive_int(
                value["parameter_count"], "model.parameter_count"
            ),
            parameter_dtype_bytes=_require_positive_int(
                value["parameter_dtype_bytes"], "model.parameter_dtype_bytes"
            ),
            gradient_bucket_count=_require_positive_int(
                value["gradient_bucket_count"], "model.gradient_bucket_count"
            ),
        )
        total_gradient_bytes = model.parameter_count * model.parameter_dtype_bytes
        if total_gradient_bytes % model.gradient_bucket_count:
            raise ValueError(
                "model gradient bytes must divide evenly across nominal gradient buckets"
            )
        return model
    if set(value) != EXPECTED_MODEL_TRACE_KEYS:
        raise ValueError(
            "model must contain exactly one of "
            f"{sorted(GRADIENT_BUCKET_SAMPLE_MODEL_KEYS)} or "
            f"{sorted(EXPECTED_MODEL_TRACE_KEYS)}"
        )
    model = ModelTrace(
        parameter_count=_require_positive_int(value["parameter_count"], "model.parameter_count"),
        parameter_dtype_bytes=_require_positive_int(
            value["parameter_dtype_bytes"], "model.parameter_dtype_bytes"
        ),
        transformer_layers=_require_positive_int(
            value["transformer_layers"], "model.transformer_layers"
        ),
        gradient_bucket_count=_require_positive_int(
            value["gradient_bucket_count"], "model.gradient_bucket_count"
        ),
        hidden_size=_require_positive_int(value["hidden_size"], "model.hidden_size"),
        sequence_length=_require_positive_int(
            value["sequence_length"], "model.sequence_length"
        ),
        microbatch_size=_require_positive_int(
            value["microbatch_size"], "model.microbatch_size"
        ),
        activation_dtype_bytes=_require_positive_int(
            value["activation_dtype_bytes"], "model.activation_dtype_bytes"
        ),
        tensor_parallel_all_reduces_per_layer=_require_positive_int(
            value["tensor_parallel_all_reduces_per_layer"],
            "model.tensor_parallel_all_reduces_per_layer",
        ),
        pipeline_microbatches=_require_positive_int(
            value["pipeline_microbatches"], "model.pipeline_microbatches"
        ),
    )
    if model.transformer_layers % pp:
        raise ValueError("model.transformer_layers must be divisible by PP")
    if model.gradient_bucket_count > model.transformer_layers // pp:
        raise ValueError(
            "model.gradient_bucket_count must not exceed transformer layers per PP stage"
        )
    total_gradient_bytes = model.parameter_count * model.parameter_dtype_bytes
    shard_count = tp * pp
    if total_gradient_bytes % shard_count:
        raise ValueError("model gradient bytes must divide evenly across TP × PP")
    if (total_gradient_bytes // shard_count) % model.gradient_bucket_count:
        raise ValueError("per-rank gradient bytes must divide evenly across buckets")
    return model


def load_profile(profile_path: Path) -> Profile:
    with profile_path.open(encoding="utf-8") as handle:
        document = json.load(handle)
    if not isinstance(document, dict):
        raise ValueError("profile must be a JSON object")
    unknown_keys = set(document) - EXPECTED_PROFILE_KEYS
    if unknown_keys:
        raise ValueError(f"unknown profile keys: {sorted(unknown_keys)}")
    missing_keys = REQUIRED_PROFILE_KEYS - set(document)
    if missing_keys:
        raise ValueError(f"missing profile keys: {sorted(missing_keys)}")
    if document.get("schema_version") != 1:
        raise ValueError("profile schema_version must be 1")

    parallelism = document.get("parallelism")
    if not isinstance(parallelism, dict) or set(parallelism) != {"tp", "pp", "dp"}:
        raise ValueError("parallelism must contain exactly tp, pp, and dp")
    network = document.get("network")
    if not isinstance(network, dict) or not REQUIRED_NETWORK_KEYS <= set(network) or set(
        network
    ) - EXPECTED_NETWORK_KEYS:
        raise ValueError(
            "network must contain hosts_per_leaf, spine_count, and link_rate, "
            "with optional packet_payload_bytes and queue_monitor_start_ns"
        )

    name = document.get("name")
    if not isinstance(name, str) or not name:
        raise ValueError("name must be a nonempty string")
    if document.get("steps") != 3:
        raise ValueError("this experiment requires exactly three training steps")
    link_rate = network.get("link_rate")
    if not isinstance(link_rate, str) or not link_rate.endswith("Gbps"):
        raise ValueError("network.link_rate must be a rate such as 200Gbps")

    tp = _require_positive_int(parallelism["tp"], "parallelism.tp")
    pp = _require_positive_int(parallelism["pp"], "parallelism.pp")
    dp = _require_positive_int(parallelism["dp"], "parallelism.dp")
    ranks = tp * pp * dp
    microburst_flow_count = _require_positive_int(
        document.get("microburst_flow_count", min(2, ranks // 2)),
        "microburst_flow_count",
    )
    if microburst_flow_count >= ranks:
        raise ValueError("microburst_flow_count must leave at least one destination rank")
    destination_value = document.get("microburst_destination_rank")
    if destination_value is None:
        microburst_destination_rank = None
    else:
        microburst_destination_rank = _require_nonnegative_int(
            destination_value, "microburst_destination_rank"
        )
        if microburst_destination_rank >= ranks:
            raise ValueError("microburst_destination_rank is outside the profile")
    source_values = document.get("microburst_source_ranks")
    if source_values is None:
        microburst_source_ranks = None
    else:
        if not isinstance(source_values, list) or not source_values:
            raise ValueError("microburst_source_ranks must be a nonempty array")
        microburst_source_ranks = tuple(
            _require_nonnegative_int(source, "microburst_source_ranks entry")
            for source in source_values
        )
        if len(set(microburst_source_ranks)) != len(microburst_source_ranks):
            raise ValueError("microburst_source_ranks must not contain duplicates")
        if any(source >= ranks for source in microburst_source_ranks):
            raise ValueError("microburst_source_ranks contains a rank outside the profile")
        if microburst_destination_rank is None:
            raise ValueError(
                "microburst_source_ranks requires microburst_destination_rank"
            )
        if microburst_destination_rank in microburst_source_ranks:
            raise ValueError("microburst source and destination ranks must differ")
        microburst_flow_count = len(microburst_source_ranks)
    microburst_enabled = document.get("microburst_enabled", True)
    if not isinstance(microburst_enabled, bool):
        raise ValueError("microburst_enabled must be a boolean")
    model = _load_model_workload(document, tp, pp)

    profile = Profile(
        name=name,
        tp=tp,
        pp=pp,
        dp=dp,
        steps=3,
        compute_duration_us=_require_positive_int(
            document.get("compute_duration_us"), "compute_duration_us"
        ),
        tp_all_reduce_bytes=_require_positive_int(
            document.get("tp_all_reduce_bytes"), "tp_all_reduce_bytes"
        ),
        pp_bytes=_require_nonnegative_int(document.get("pp_bytes"), "pp_bytes"),
        dp_all_reduce_bytes=_require_positive_int(
            document.get("dp_all_reduce_bytes"), "dp_all_reduce_bytes"
        ),
        seed=_require_positive_int(document.get("seed"), "seed"),
        hosts_per_leaf=_require_positive_int(
            network["hosts_per_leaf"], "network.hosts_per_leaf"
        ),
        spine_count=_require_positive_int(network["spine_count"], "network.spine_count"),
        link_rate=link_rate,
        packet_payload_bytes=_require_positive_int(
            network.get("packet_payload_bytes", 1_000),
            "network.packet_payload_bytes",
        ),
        queue_monitor_start_ns=_require_nonnegative_int(
            network.get("queue_monitor_start_ns", 0),
            "network.queue_monitor_start_ns",
        ),
        microburst_bytes=_require_positive_int(
            document.get("microburst_bytes"), "microburst_bytes"
        ),
        microburst_flow_count=microburst_flow_count,
        microburst_destination_rank=microburst_destination_rank,
        microburst_offset_spacing_ns=_require_nonnegative_int(
            document.get("microburst_offset_spacing_ns", 1_000),
            "microburst_offset_spacing_ns",
        ),
        microburst_source_ranks=microburst_source_ranks,
        microburst_enabled=microburst_enabled,
        model=model,
    )
    if profile.ranks % profile.hosts_per_leaf:
        raise ValueError("parallelism product must be divisible by network.hosts_per_leaf")
    if profile.spine_count > 255:
        raise ValueError("network.spine_count must not exceed 255")
    if profile.packet_payload_bytes > 9_000:
        raise ValueError("network.packet_payload_bytes must not exceed 9000")
    if profile.pp > 1 and profile.pp_bytes == 0:
        raise ValueError("pp_bytes must be positive when PP is greater than one")
    if isinstance(profile.model, ModelTrace):
        activation_bytes = (
            profile.model.microbatch_size
            * profile.model.sequence_length
            * profile.model.hidden_size
            * profile.model.activation_dtype_bytes
        )
        if profile.tp_all_reduce_bytes != activation_bytes:
            raise ValueError(
                "tp_all_reduce_bytes must equal the model activation tensor bytes"
            )
        if profile.pp_bytes != activation_bytes:
            raise ValueError("pp_bytes must equal the model activation tensor bytes")
        gradient_bucket_bytes = (
            profile.model.parameter_count
            * profile.model.parameter_dtype_bytes
            // (profile.tp * profile.pp * profile.model.gradient_bucket_count)
        )
        if profile.dp_all_reduce_bytes != gradient_bucket_bytes:
            raise ValueError(
                "dp_all_reduce_bytes must equal the model-derived per-rank gradient bucket bytes"
            )
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

    def _build_smoke_trace(self) -> None:
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

    def _build_gradient_bucket_sample_trace(self) -> None:
        """Emit a packet-accurate representative DP bucket, not a full-model replay."""
        _, tp_groups, _, dp_groups = self.groups
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
            backward = self.compute(f"step_{step}_backward_bucket_0", [tp_reduce])
            dp_reduce = self.all_reduce(
                f"step_{step}_dp_all_reduce_bucket_0",
                [backward],
                "dp",
                dp_groups[str(self.rank)],
                self.profile.dp_all_reduce_bytes,
                step,
            )
            predecessor = self.compute(f"step_{step}_optimizer", [dp_reduce])

    def _build_model_trace(self, model: ModelTrace) -> None:
        """Emit a structural transformer step with exact model-derived DP bytes.

        The profile is a workload specification rather than a framework replay:
        it partitions parameters evenly across TP and PP, then emits one DP
        All-Reduce bucket per specified gradient bucket. The sum of bucket
        sizes on every rank is therefore the local model-gradient shard.
        """
        _, tp_groups, _, dp_groups = self.groups
        tp_rank, pp_rank, dp_rank = self.coords
        local_layers = model.transformer_layers // self.profile.pp
        gradient_bucket_bytes = self.profile.dp_all_reduce_bytes
        forward_tp_collectives = max(
            1, model.tensor_parallel_all_reduces_per_layer // 2
        )
        backward_tp_collectives = (
            model.tensor_parallel_all_reduces_per_layer - forward_tp_collectives
        )
        predecessor: int | None = None

        for step in range(1, self.profile.steps + 1):
            forward_tail = predecessor
            for layer in range(local_layers):
                forward = self.compute(
                    f"step_{step}_layer_{layer}_forward_compute",
                    [] if forward_tail is None else [forward_tail],
                )
                forward_tail = forward
                for collective in range(forward_tp_collectives):
                    forward_tail = self.all_reduce(
                        f"step_{step}_layer_{layer}_tp_forward_{collective}",
                        [forward_tail],
                        "tp",
                        tp_groups[str(self.rank)],
                        self.profile.tp_all_reduce_bytes,
                        step,
                    )

            forward_pipeline: list[int] = []
            for microbatch in range(model.pipeline_microbatches):
                pipeline_tag = (
                    step * 10_000_000
                    + microbatch * 100_000
                    + dp_rank * 1_000
                    + tp_rank
                )
                dependencies = [forward_tail] if forward_tail is not None else []
                if pp_rank > 0:
                    source = rank_for(tp_rank, pp_rank - 1, dp_rank, self.profile)
                    forward_pipeline.append(
                        self.pipeline_node(
                            f"step_{step}_microbatch_{microbatch}_pp_forward_recv",
                            COMM_RECV_NODE,
                            dependencies,
                            source,
                            self.rank,
                            pipeline_tag,
                            step,
                        )
                    )
                if pp_rank < self.profile.pp - 1:
                    destination = rank_for(
                        tp_rank, pp_rank + 1, dp_rank, self.profile
                    )
                    forward_pipeline.append(
                        self.pipeline_node(
                            f"step_{step}_microbatch_{microbatch}_pp_forward_send",
                            COMM_SEND_NODE,
                            dependencies,
                            self.rank,
                            destination,
                            pipeline_tag,
                            step,
                        )
                    )

            backward_tail = self.compute(
                f"step_{step}_backward_start",
                [forward_tail, *forward_pipeline] if forward_tail else forward_pipeline,
            )
            dp_reductions: list[int] = []
            emitted_buckets = 0
            for layer_offset, layer in enumerate(reversed(range(local_layers))):
                backward_tail = self.compute(
                    f"step_{step}_layer_{layer}_backward_compute",
                    [backward_tail],
                )
                for collective in range(backward_tp_collectives):
                    backward_tail = self.all_reduce(
                        f"step_{step}_layer_{layer}_tp_backward_{collective}",
                        [backward_tail],
                        "tp",
                        tp_groups[str(self.rank)],
                        self.profile.tp_all_reduce_bytes,
                        step,
                    )
                target_buckets = (
                    (layer_offset + 1) * model.gradient_bucket_count // local_layers
                )
                while emitted_buckets < target_buckets:
                    dp_reductions.append(
                        self.all_reduce(
                            f"step_{step}_dp_all_reduce_bucket_{emitted_buckets}",
                            [backward_tail],
                            "dp",
                            dp_groups[str(self.rank)],
                            gradient_bucket_bytes,
                            step,
                        )
                    )
                    emitted_buckets += 1

            backward_pipeline: list[int] = []
            for microbatch in range(model.pipeline_microbatches):
                pipeline_tag = (
                    50_000_000
                    + step * 10_000_000
                    + microbatch * 100_000
                    + dp_rank * 1_000
                    + tp_rank
                )
                if pp_rank < self.profile.pp - 1:
                    source = rank_for(tp_rank, pp_rank + 1, dp_rank, self.profile)
                    backward_pipeline.append(
                        self.pipeline_node(
                            f"step_{step}_microbatch_{microbatch}_pp_backward_recv",
                            COMM_RECV_NODE,
                            [backward_tail],
                            source,
                            self.rank,
                            pipeline_tag,
                            step,
                        )
                    )
                if pp_rank > 0:
                    destination = rank_for(
                        tp_rank, pp_rank - 1, dp_rank, self.profile
                    )
                    backward_pipeline.append(
                        self.pipeline_node(
                            f"step_{step}_microbatch_{microbatch}_pp_backward_send",
                            COMM_SEND_NODE,
                            [backward_tail],
                            self.rank,
                            destination,
                            pipeline_tag,
                            step,
                        )
                    )
            predecessor = self.compute(
                f"step_{step}_optimizer",
                [*dp_reductions, *backward_pipeline],
            )

    def build(self) -> None:
        if self.profile.model is None:
            self._build_smoke_trace()
        elif isinstance(self.profile.model, GradientBucketSample):
            self._build_gradient_bucket_sample_trace()
        else:
            self._build_model_trace(self.profile.model)

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


def write_network_config(
    path: Path,
    topology: Path,
    output_dir: Path,
    packet_payload_bytes: int,
    queue_monitor_start_ns: int,
) -> None:
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
        config.write(
            "ENABLE_QCN 1\nUSE_DYNAMIC_PFC_THRESHOLD 1\n\n"
            f"PACKET_PAYLOAD_SIZE {packet_payload_bytes}\n\n"
        )
        for key, value in entries.items():
            config.write(f"{key} {value}\n")
        config.write(
            f"QLEN_MON_START {queue_monitor_start_ns}\n"
            "QLEN_MON_END 20000\n\n"
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


def _microburst_flows(profile: Profile) -> list[dict[str, int]]:
    if not profile.microburst_enabled:
        return []
    if profile.microburst_destination_rank is None:
        cross_rack_base = profile.ranks // 2
        destinations = [cross_rack_base + index for index in range(profile.microburst_flow_count)]
        if any(destination >= profile.ranks for destination in destinations):
            raise ValueError(
                "microburst_flow_count requires microburst_destination_rank "
                "when one-to-one cross-rack destinations exceed the profile"
            )
        endpoints = list(zip(range(profile.microburst_flow_count), destinations))
    else:
        destination = profile.microburst_destination_rank
        sources = (
            list(profile.microburst_source_ranks)
            if profile.microburst_source_ranks is not None
            else [rank for rank in range(profile.ranks) if rank != destination]
        )
        endpoints = [(source, destination) for source in sources[: profile.microburst_flow_count]]
    return [
        {
            "src": source,
            "dst": destination,
            "size_bytes": profile.microburst_bytes,
            "offset_ns": index * profile.microburst_offset_spacing_ns,
            "priority_group": 3,
        }
        for index, (source, destination) in enumerate(endpoints)
    ]


def _validated_drop_probabilities(
    probabilities: dict[str, float] | None,
) -> dict[str, float]:
    result = dict(DEFAULT_DROP_PROBABILITY_BY_STEP if probabilities is None else probabilities)
    if set(result) != set(DEFAULT_DROP_PROBABILITY_BY_STEP):
        raise ValueError("drop probabilities must define exactly training steps 1, 2, and 3")
    for step, probability in result.items():
        if isinstance(probability, bool) or not isinstance(probability, (int, float)):
            raise ValueError(f"drop probability for step {step} must be numeric")
        if not 0.0 <= probability <= 1.0:
            raise ValueError(f"drop probability for step {step} must be in [0, 1]")
    return {step: float(probability) for step, probability in result.items()}


def write_experiment_config(
    path: Path,
    profile: Profile,
    drop_probabilities: dict[str, float] | None = None,
) -> None:
    microburst_flows = _microburst_flows(profile)
    policy = {
        "schema_version": 1,
        "enabled": True,
        "seed": profile.seed,
        "run_id": profile.name,
        "eligibility": "dp_all_reduce_only",
        "drop_probability_by_step": _validated_drop_probabilities(drop_probabilities),
        "default_priority_group": 3,
        "provenance": {"control_bytes": 64, "priority_group": 1},
        "vnet_to_priority_group": {"0": 3},
        "microburst": {
            "enabled": profile.microburst_enabled,
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


def model_trace_metadata(profile: Profile) -> dict[str, int | float | str] | None:
    if profile.model is None:
        return None
    model = profile.model
    total_gradient_bytes = model.parameter_count * model.parameter_dtype_bytes
    if isinstance(model, GradientBucketSample):
        return {
            "workload_kind": "representative_gradient_bucket",
            "parameter_count": model.parameter_count,
            "parameter_dtype_bytes": model.parameter_dtype_bytes,
            "total_gradient_bytes_per_data_parallel_replica": total_gradient_bytes,
            "gradient_bucket_count": model.gradient_bucket_count,
            "nominal_model_gradient_bucket_bytes": (
                total_gradient_bytes // model.gradient_bucket_count
            ),
            "gradient_bytes_per_rank": total_gradient_bytes // (profile.tp * profile.pp),
            "simulated_gradient_bucket_bytes": profile.dp_all_reduce_bytes,
            "simulated_gradient_buckets_per_step": 1,
            "packet_payload_bytes": profile.packet_payload_bytes,
            "queue_monitor_start_ns": profile.queue_monitor_start_ns,
        }
    gradient_bytes_per_rank = total_gradient_bytes // (profile.tp * profile.pp)
    return {
        "workload_kind": "structural_transformer_trace",
        "parameter_count": model.parameter_count,
        "parameter_dtype_bytes": model.parameter_dtype_bytes,
        "total_gradient_bytes_per_data_parallel_replica": total_gradient_bytes,
        "gradient_bytes_per_rank": gradient_bytes_per_rank,
        "gradient_bucket_count": model.gradient_bucket_count,
        "gradient_bucket_bytes": profile.dp_all_reduce_bytes,
        "transformer_layers": model.transformer_layers,
        "transformer_layers_per_pipeline_stage": model.transformer_layers // profile.pp,
        "activation_bytes_per_microbatch": profile.pp_bytes,
        "pipeline_microbatches": model.pipeline_microbatches,
        "tensor_parallel_all_reduces_per_layer": model.tensor_parallel_all_reduces_per_layer,
    }


def materialize(
    profile_path: Path,
    output_dir: Path,
    clean: bool = False,
    *,
    seed_override: int | None = None,
    drop_probabilities: dict[str, float] | None = None,
) -> dict[str, str]:
    profile = load_profile(profile_path)
    if seed_override is not None:
        profile = replace(profile, seed=_require_positive_int(seed_override, "seed_override"))
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
    write_network_config(
        network_config,
        topology.resolve(),
        output_dir / "ns3",
        profile.packet_payload_bytes,
        profile.queue_monitor_start_ns,
    )
    experiment_config = output_dir / "experiment.json"
    write_experiment_config(experiment_config, profile, drop_probabilities)
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
    model_metadata = model_trace_metadata(profile)
    if model_metadata is not None:
        (output_dir / "model_trace.json").write_text(
            json.dumps(model_metadata, indent=2) + "\n", encoding="utf-8"
        )

    manifest = {
        "profile": profile.name,
        "seed": profile.seed,
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
    if model_metadata is not None:
        manifest["model_trace"] = model_metadata
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--clean", action="store_true", help="replace an existing output directory")
    parser.add_argument("--seed", type=int, help="override the profile seed")
    arguments = parser.parse_args()
    manifest = materialize(
        arguments.profile.resolve(),
        arguments.output.resolve(),
        arguments.clean,
        seed_override=arguments.seed,
    )
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())