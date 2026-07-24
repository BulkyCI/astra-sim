"""Typed physical-topology specifications for reproducible ns-3 experiments.

The bundled ns-3 topology format declares one *bidirectional* link per edge.
This module keeps construction, validation, serialization, and manifest metadata
in one place so profile parsing cannot drift from emitted topology files.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from pathlib import Path
from typing import Any


DEFAULT_PACKET_PAYLOAD_BYTES = 1_000
MAX_PACKET_PAYLOAD_BYTES = 9_000
HOST_TO_SWITCH_DELAY = "0.005ms"
SWITCH_TO_SWITCH_DELAY = "0.0125ms"
DATA_LOSS_SCOPES = {
    "all",
    "host_to_switch",
    "switch_to_host",
    "switch_to_switch",
}


@dataclass(frozen=True)
class DataPlaneLoss:
    """Data-only receive impairment and bounded go-back-N recovery policy."""

    probability: float
    start_ns: int
    duration_ns: int
    scope: str
    source_host: int | None
    destination_host: int | None
    receiver_node: int | None
    rng_stream: int
    retransmission_timeout_ns: int
    max_retransmission_retries: int

    def manifest(self) -> dict[str, int | float | str | None]:
        return {
            "enabled": True,
            "probability": self.probability,
            "start_ns": self.start_ns,
            "duration_ns": self.duration_ns,
            "scope": self.scope,
            "source_host": self.source_host,
            "destination_host": self.destination_host,
            "receiver_node": self.receiver_node,
            "rng_stream": self.rng_stream,
            "retransmission_timeout_ns": self.retransmission_timeout_ns,
            "max_retransmission_retries": self.max_retransmission_retries,
        }


@dataclass(frozen=True)
class ClosNetwork:
    """A two-stage leaf-spine fabric with host-attached leaf switches."""

    link_rate: str
    packet_payload_bytes: int
    queue_monitor_start_ns: int
    hosts_per_leaf: int
    spine_count: int
    data_loss: DataPlaneLoss | None = None

    @property
    def kind(self) -> str:
        return "clos"


@dataclass(frozen=True)
class RingNetwork:
    """A host-attached bidirectional ring of switches.

    Each modeled accelerator owns one RDMA host and one attached switch. The
    switches form the ring so ns-3 can model switch queues, PFC, and equal-cost
    paths in both directions; a direct host-only ring cannot provide those
    switch-level signals in this backend.
    """

    link_rate: str
    packet_payload_bytes: int
    queue_monitor_start_ns: int
    data_loss: DataPlaneLoss | None = None

    @property
    def kind(self) -> str:
        return "ring"


PhysicalNetwork = ClosNetwork | RingNetwork


@dataclass(frozen=True)
class TopologyLink:
    """One bidirectional ns-3 link declaration."""

    source: int
    destination: int
    delay: str


@dataclass(frozen=True)
class TopologyLayout:
    """Validated topology data independent of its text serialization."""

    kind: str
    description: str
    host_count: int
    node_count: int
    switch_ids: tuple[int, ...]
    links: tuple[TopologyLink, ...]
    link_rate: str
    details: tuple[tuple[str, int], ...] = ()

    def __post_init__(self) -> None:
        if self.host_count <= 0 or self.node_count <= 0:
            raise ValueError("topology must contain at least one host and node")
        if self.host_count + len(self.switch_ids) != self.node_count:
            raise ValueError("topology host and switch counts do not partition nodes")
        if len(set(self.switch_ids)) != len(self.switch_ids):
            raise ValueError("topology switch IDs must be unique")
        if any(node < 0 or node >= self.node_count for node in self.switch_ids):
            raise ValueError("topology switch ID is outside the node range")

        undirected_edges: set[tuple[int, int]] = set()
        for link in self.links:
            if not 0 <= link.source < self.node_count:
                raise ValueError("topology link source is outside the node range")
            if not 0 <= link.destination < self.node_count:
                raise ValueError("topology link destination is outside the node range")
            if link.source == link.destination:
                raise ValueError("topology links must not contain self-loops")
            edge = tuple(sorted((link.source, link.destination)))
            if edge in undirected_edges:
                raise ValueError("topology must not declare duplicate bidirectional links")
            undirected_edges.add(edge)

    def write(self, path: Path) -> None:
        """Write the exact topology format consumed by the bundled ns-3 parser."""
        with path.open("w", encoding="utf-8") as topology:
            topology.write(
                f"{self.node_count} {len(self.switch_ids)} {len(self.links)}\n"
            )
            topology.write(" ".join(str(node) for node in self.switch_ids) + "\n")
            for link in self.links:
                topology.write(
                    f"{link.source} {link.destination} {self.link_rate} "
                    f"{link.delay} 0\n"
                )

    def manifest(self) -> dict[str, int | str]:
        """Return auditable physical-network metadata for manifests and reports."""
        return {
            "kind": self.kind,
            "description": self.description,
            "host_count": self.host_count,
            "node_count": self.node_count,
            "switch_count": len(self.switch_ids),
            "link_count": len(self.links),
            "link_rate": self.link_rate,
            **dict(self.details),
        }


def _positive_int(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{field} must be a positive integer")
    return value


def _nonnegative_int(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field} must be a nonnegative integer")
    return value


def _link_rate(value: Any) -> str:
    if not isinstance(value, str) or not value.endswith("Gbps"):
        raise ValueError("network.link_rate must be a rate such as 200Gbps")
    return value


def _probability(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field} must be a number in [0, 1]")
    probability = float(value)
    if not isfinite(probability) or not 0.0 <= probability <= 1.0:
        raise ValueError(f"{field} must be a number in [0, 1]")
    return probability


def _optional_host(value: Any, field: str, host_count: int) -> int | None:
    if value is None:
        return None
    host = _nonnegative_int(value, field)
    if host >= host_count:
        raise ValueError(f"{field} is outside the host range")
    return host


def _load_data_loss(document: dict[str, Any], host_count: int) -> DataPlaneLoss | None:
    if "data_loss" not in document:
        return None
    loss = document["data_loss"]
    if not isinstance(loss, dict):
        raise ValueError("network.data_loss must be an object")
    required = {
        "probability",
        "start_ns",
        "duration_ns",
        "scope",
        "rng_stream",
        "retransmission_timeout_ns",
        "max_retransmission_retries",
    }
    optional = {"source_host", "destination_host", "receiver_node"}
    unknown = set(loss) - required - optional
    if unknown:
        raise ValueError(f"unknown network.data_loss keys: {sorted(unknown)}")
    missing = required - set(loss)
    if missing:
        raise ValueError(f"missing network.data_loss keys: {sorted(missing)}")
    scope = loss["scope"]
    if not isinstance(scope, str) or scope not in DATA_LOSS_SCOPES:
        raise ValueError(
            "network.data_loss.scope must be one of "
            f"{sorted(DATA_LOSS_SCOPES)}"
        )
    duration_ns = _positive_int(loss["duration_ns"], "network.data_loss.duration_ns")
    timeout_ns = _positive_int(
        loss["retransmission_timeout_ns"],
        "network.data_loss.retransmission_timeout_ns",
    )
    max_retries = _positive_int(
        loss["max_retransmission_retries"],
        "network.data_loss.max_retransmission_retries",
    )
    rng_stream = _positive_int(loss["rng_stream"], "network.data_loss.rng_stream")
    if rng_stream > 2**63 - 1:
        raise ValueError("network.data_loss.rng_stream exceeds the ns-3 range")
    source_host = _optional_host(
        loss.get("source_host"), "network.data_loss.source_host", host_count
    )
    destination_host = _optional_host(
        loss.get("destination_host"), "network.data_loss.destination_host", host_count
    )
    if source_host is not None and source_host == destination_host:
        raise ValueError("network.data_loss source_host and destination_host must differ")
    receiver_node = loss.get("receiver_node")
    if receiver_node is not None:
        receiver_node = _nonnegative_int(
            receiver_node, "network.data_loss.receiver_node"
        )
    return DataPlaneLoss(
        probability=_probability(loss["probability"], "network.data_loss.probability"),
        start_ns=_nonnegative_int(loss["start_ns"], "network.data_loss.start_ns"),
        duration_ns=duration_ns,
        scope=scope,
        source_host=source_host,
        destination_host=destination_host,
        receiver_node=receiver_node,
        rng_stream=rng_stream,
        retransmission_timeout_ns=timeout_ns,
        max_retransmission_retries=max_retries,
    )


def _common_network_fields(document: dict[str, Any]) -> tuple[str, int, int]:
    return (
        _link_rate(document.get("link_rate")),
        _positive_int(
            document.get("packet_payload_bytes", DEFAULT_PACKET_PAYLOAD_BYTES),
            "network.packet_payload_bytes",
        ),
        _nonnegative_int(
            document.get("queue_monitor_start_ns", 0),
            "network.queue_monitor_start_ns",
        ),
    )


def load_network(document: Any, host_count: int) -> PhysicalNetwork:
    """Parse a discriminated physical-network profile with strict shape checks.

    A missing ``topology`` remains a legacy spelling for ``clos``. New profiles
    should always declare the discriminator explicitly.
    """
    if not isinstance(document, dict):
        raise ValueError("network must be an object")
    topology = document.get("topology", "clos")
    if topology not in {"clos", "ring"}:
        raise ValueError("network.topology must be either clos or ring")

    common_keys = {
        "topology",
        "link_rate",
        "packet_payload_bytes",
        "queue_monitor_start_ns",
        "data_loss",
    }
    topology_keys = (
        {"hosts_per_leaf", "spine_count"} if topology == "clos" else set()
    )
    unknown_keys = set(document) - common_keys - topology_keys
    if unknown_keys:
        raise ValueError(f"unknown network keys: {sorted(unknown_keys)}")
    missing_keys = ({"link_rate"} | topology_keys) - set(document)
    if missing_keys:
        raise ValueError(f"missing network keys: {sorted(missing_keys)}")

    link_rate, packet_payload_bytes, queue_monitor_start_ns = _common_network_fields(
        document
    )
    data_loss = _load_data_loss(document, host_count)
    if packet_payload_bytes > MAX_PACKET_PAYLOAD_BYTES:
        raise ValueError(
            f"network.packet_payload_bytes must not exceed {MAX_PACKET_PAYLOAD_BYTES}"
        )

    if topology == "ring":
        if host_count < 3:
            raise ValueError("network.ring requires at least three hosts")
        return RingNetwork(
            link_rate=link_rate,
            packet_payload_bytes=packet_payload_bytes,
            queue_monitor_start_ns=queue_monitor_start_ns,
            data_loss=data_loss,
        )

    hosts_per_leaf = _positive_int(
        document["hosts_per_leaf"], "network.hosts_per_leaf"
    )
    spine_count = _positive_int(document["spine_count"], "network.spine_count")
    if host_count % hosts_per_leaf:
        raise ValueError("parallelism product must be divisible by network.hosts_per_leaf")
    if spine_count > 255:
        raise ValueError("network.spine_count must not exceed 255")
    return ClosNetwork(
        link_rate=link_rate,
        packet_payload_bytes=packet_payload_bytes,
        queue_monitor_start_ns=queue_monitor_start_ns,
        hosts_per_leaf=hosts_per_leaf,
        spine_count=spine_count,
        data_loss=data_loss,
    )


def build_topology(network: PhysicalNetwork, host_count: int) -> TopologyLayout:
    """Build a validated physical layout for the requested network variant."""
    if isinstance(network, ClosNetwork):
        layout = _build_clos_topology(network, host_count)
    elif isinstance(network, RingNetwork):
        layout = _build_ring_topology(network, host_count)
    else:
        raise TypeError(f"unsupported physical network: {type(network).__name__}")
    if (
        network.data_loss is not None
        and network.data_loss.receiver_node is not None
        and network.data_loss.receiver_node >= layout.node_count
    ):
        raise ValueError("network.data_loss.receiver_node is outside the topology")
    return layout


def _build_clos_topology(network: ClosNetwork, host_count: int) -> TopologyLayout:
    leaf_count = host_count // network.hosts_per_leaf
    leaf_start = host_count
    spine_start = leaf_start + leaf_count
    node_count = spine_start + network.spine_count
    links = [
        TopologyLink(
            source=host,
            destination=leaf_start + host // network.hosts_per_leaf,
            delay=HOST_TO_SWITCH_DELAY,
        )
        for host in range(host_count)
    ]
    links.extend(
        TopologyLink(source=leaf, destination=spine, delay=SWITCH_TO_SWITCH_DELAY)
        for leaf in range(leaf_start, spine_start)
        for spine in range(spine_start, node_count)
    )
    return TopologyLayout(
        kind=network.kind,
        description="Two-stage leaf-spine Clos",
        host_count=host_count,
        node_count=node_count,
        switch_ids=tuple(range(leaf_start, node_count)),
        links=tuple(links),
        link_rate=network.link_rate,
        details=(
            ("leaf_count", leaf_count),
            ("spine_count", network.spine_count),
            ("hosts_per_leaf", network.hosts_per_leaf),
        ),
    )


def _build_ring_topology(network: RingNetwork, host_count: int) -> TopologyLayout:
    switch_start = host_count
    switch_ids = tuple(range(switch_start, switch_start + host_count))
    links = [
        TopologyLink(
            source=host,
            destination=switch_start + host,
            delay=HOST_TO_SWITCH_DELAY,
        )
        for host in range(host_count)
    ]
    links.extend(
        TopologyLink(
            source=switch_start + index,
            destination=switch_start + (index + 1) % host_count,
            delay=SWITCH_TO_SWITCH_DELAY,
        )
        for index in range(host_count)
    )
    return TopologyLayout(
        kind=network.kind,
        description="Host-attached bidirectional switch ring",
        host_count=host_count,
        node_count=host_count * 2,
        switch_ids=switch_ids,
        links=tuple(links),
        link_rate=network.link_rate,
        details=(("switch_ring_size", host_count),),
    )
