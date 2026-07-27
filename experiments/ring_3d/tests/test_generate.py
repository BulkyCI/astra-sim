from __future__ import annotations

import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from experiments.ring_3d.generate import (
    REPOSITORY_ROOT,
    coordinates_for,
    generate_groups,
    load_profile,
    materialize,
    rank_for,
)
from experiments.ring_3d.topology import build_topology
from chakra.schema.protobuf.et_def_pb2 import GlobalMetadata, Node
from chakra.src.third_party.utils.protolib import decodeMessage


class Ring3DGeneratorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.profile_path = REPOSITORY_ROOT / "experiments/ring_3d/profiles/smoke_8.json"
        self.profile = load_profile(self.profile_path)

    def test_rank_mapping_is_bijective(self) -> None:
        ranks = set()
        for dp_rank in range(self.profile.dp):
            for pp_rank in range(self.profile.pp):
                for tp_rank in range(self.profile.tp):
                    rank = rank_for(tp_rank, pp_rank, dp_rank, self.profile)
                    ranks.add(rank)
                    self.assertEqual(
                        coordinates_for(rank, self.profile),
                        (tp_rank, pp_rank, dp_rank),
                    )
        self.assertEqual(ranks, set(range(self.profile.ranks)))

    def test_groups_have_expected_membership(self) -> None:
        groups, tp_groups, pp_groups, dp_groups = generate_groups(self.profile)
        self.assertEqual(len(groups), 12)
        for rank in range(self.profile.ranks):
            self.assertEqual(len(groups[str(tp_groups[str(rank)])]), self.profile.tp)
            self.assertEqual(len(groups[str(pp_groups[str(rank)])]), self.profile.pp)
            self.assertEqual(len(groups[str(dp_groups[str(rank)])]), self.profile.dp)

    def test_materialized_inputs_are_complete(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            output = Path(temporary_directory) / "experiment"
            manifest = materialize(self.profile_path, output)

            self.assertEqual(len(list((output / "workload").glob("ring_3d.*.et"))), 8)
            topology_lines = (output / "topology.txt").read_text(encoding="utf-8").splitlines()
            node_count, switch_count, edge_count = map(int, topology_lines[0].split())
            self.assertEqual((node_count, switch_count, edge_count), (16, 8, 24))
            self.assertEqual(len(topology_lines), edge_count + 2)
            self.assertEqual((output / "ns3/flow.txt").read_text(encoding="utf-8"), "0\n")
            self.assertEqual((output / "ns3/trace.txt").read_text(encoding="utf-8"), "0\n")
            self.assertEqual(
                json.loads((output / "profile.json").read_text(encoding="utf-8")),
                json.loads(self.profile_path.read_text(encoding="utf-8")),
            )

            policy = json.loads((output / "experiment.json").read_text(encoding="utf-8"))
            self.assertEqual(policy["eligibility"], "dp_all_reduce_only")
            self.assertEqual(
                policy["selection_probability_by_step"],
                {"1": 0.005, "2": 0.1, "3": 0.005},
            )
            self.assertEqual(
                policy["selection_policy"],
                {
                    "semantics": "logical_admission_selection",
                    "p_low": 0.005,
                    "p_high": 0.1,
                },
            )
            with (output / "clr_mask.csv").open(newline="", encoding="utf-8") as handle:
                self.assertEqual(
                    list(csv.DictReader(handle)),
                    [
                        {"step_id": "1", "is_clr": "1", "probability": "1"},
                        {
                            "step_id": "2",
                            "is_clr": "0",
                            "probability": "0.35846544338504249",
                        },
                        {"step_id": "3", "is_clr": "1", "probability": "1"},
                    ],
                )
            self.assertEqual(policy["provenance"]["priority_group"], 1)
            self.assertEqual(manifest["ranks"], 8)
            self.assertEqual(Path(manifest["profile_config"]), output / "profile.json")
            self.assertEqual(Path(manifest["clr_mask"]), output / "clr_mask.csv")
            self.assertEqual(manifest["clr_schedule"]["clr_step_count"], 2)
            self.assertIn(
                "ACK_HIGH_PRIO 1",
                (output / "network_config.txt").read_text(encoding="utf-8"),
            )

    def test_llama3_profile_materializes_simultaneous_many_to_one_microburst(self) -> None:
        profile_path = REPOSITORY_ROOT / "experiments/ring_3d/profiles/llama3_70b_16.json"
        with tempfile.TemporaryDirectory() as temporary_directory:
            output = Path(temporary_directory) / "experiment"
            materialize(profile_path, output)

            policy = json.loads((output / "experiment.json").read_text(encoding="utf-8"))
            flows = policy["microburst"]["flows"]
            self.assertEqual(len(flows), 7)
            self.assertEqual({flow["dst"] for flow in flows}, {8})
            self.assertEqual({flow["src"] for flow in flows}, set(range(7)))
            self.assertEqual({flow["size_bytes"] for flow in flows}, {128 * 1024 * 1024})
            self.assertEqual({flow["offset_ns"] for flow in flows}, {0})
            self.assertIn(
                "PACKET_PAYLOAD_SIZE 4096",
                (output / "network_config.txt").read_text(encoding="utf-8"),
            )
            self.assertIn(
                "QLEN_MON_START 20000000",
                (output / "network_config.txt").read_text(encoding="utf-8"),
            )

    def test_no_incast_profile_disables_synthetic_background_traffic(self) -> None:
        profile_path = REPOSITORY_ROOT / "experiments/ring_3d/profiles/no_incast_8.json"
        with tempfile.TemporaryDirectory() as temporary_directory:
            output = Path(temporary_directory) / "experiment"
            materialize(profile_path, output)

            policy = json.loads((output / "experiment.json").read_text(encoding="utf-8"))
            self.assertFalse(policy["microburst"]["enabled"])
            self.assertEqual(policy["microburst"]["flows"], [])
            self.assertEqual(
                policy["selection_probability_by_step"],
                {"1": 0.005, "2": 0.1, "3": 0.005},
            )

    def test_fixed_p_low_override_preserves_enabled_microburst(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            output = Path(temporary_directory) / "experiment"
            materialize(
                self.profile_path,
                output,
                p_low=0.005,
                p_high=0.005,
            )

            policy = json.loads((output / "experiment.json").read_text(encoding="utf-8"))
            self.assertTrue(policy["enabled"])
            self.assertTrue(policy["microburst"]["enabled"])
            self.assertEqual(
                policy["selection_probability_by_step"],
                {"1": 0.005, "2": 0.005, "3": 0.005},
            )

    def test_selection_policy_rejects_low_value_above_one_percent(self) -> None:
        document = json.loads(self.profile_path.read_text(encoding="utf-8"))
        document["selection_policy"]["p_low"] = 0.0101
        with tempfile.TemporaryDirectory() as temporary_directory:
            profile_path = Path(temporary_directory) / "invalid.json"
            profile_path.write_text(json.dumps(document), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "p_low"):
                load_profile(profile_path)

    def test_data_loss_materializes_data_only_contract(self) -> None:
        document = json.loads(self.profile_path.read_text(encoding="utf-8"))
        document["network"]["data_loss"] = {
            "probability": 0.25,
            "start_ns": 100,
            "duration_ns": 5_000,
            "scope": "host_to_switch",
            "source_host": 0,
            "destination_host": 4,
            "receiver_node": 8,
            "rng_stream": 71,
            "retransmission_timeout_ns": 500,
            "max_retransmission_retries": 3,
        }
        with tempfile.TemporaryDirectory() as temporary_directory:
            profile_path = Path(temporary_directory) / "lossy.json"
            output = Path(temporary_directory) / "experiment"
            profile_path.write_text(json.dumps(document), encoding="utf-8")
            manifest = materialize(profile_path, output)

            self.assertEqual(
                manifest["data_plane_loss"],
                {
                    "enabled": True,
                    "probability": 0.25,
                    "start_ns": 100,
                    "duration_ns": 5_000,
                    "scope": "host_to_switch",
                    "source_host": 0,
                    "destination_host": 4,
                    "receiver_node": 8,
                    "rng_stream": 71,
                    "retransmission_timeout_ns": 500,
                    "max_retransmission_retries": 3,
                },
            )
            network_config = (output / "network_config.txt").read_text(
                encoding="utf-8"
            )
            self.assertIn("DATA_LOSS_PROBABILITY 0.25", network_config)
            self.assertIn("DATA_LOSS_SCOPE host_to_switch", network_config)
            self.assertIn("DATA_LOSS_RECEIVER_NODE 8", network_config)
            self.assertIn("RETRANSMISSION_TIMEOUT_NS 500", network_config)
            self.assertIn("MAX_RETRANSMISSION_RETRIES 3", network_config)
            self.assertIn(
                f"TRANSPORT_EVENT_OUTPUT_FILE {output / 'ns3' / 'transport_events.csv'}",
                network_config,
            )
            self.assertIn("ACK_HIGH_PRIO 1", network_config)
            self.assertEqual(
                Path(manifest["transport_event_file"]),
                output / "ns3" / "transport_events.csv",
            )

    def test_retry_exhaustion_profile_is_a_data_only_failure_fixture(self) -> None:
        profile_path = (
            REPOSITORY_ROOT
            / "experiments/ring_3d/profiles/retry_exhaustion_8.json"
        )
        profile = load_profile(profile_path)

        self.assertFalse(profile.microburst_enabled)
        self.assertIsNotNone(profile.network.data_loss)
        self.assertEqual(profile.network.data_loss.probability, 1.0)
        self.assertEqual(profile.network.data_loss.max_retransmission_retries, 1)

    def test_data_loss_requires_bounded_recovery(self) -> None:
        document = json.loads(self.profile_path.read_text(encoding="utf-8"))
        document["network"]["data_loss"] = {
            "probability": 0.25,
            "start_ns": 0,
            "duration_ns": 1,
            "scope": "all",
            "rng_stream": 51,
            "retransmission_timeout_ns": 0,
            "max_retransmission_retries": 3,
        }
        with tempfile.TemporaryDirectory() as temporary_directory:
            profile_path = Path(temporary_directory) / "invalid.json"
            profile_path.write_text(json.dumps(document), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "retransmission_timeout_ns"):
                load_profile(profile_path)

    def test_data_loss_rejects_non_string_scope(self) -> None:
        document = json.loads(self.profile_path.read_text(encoding="utf-8"))
        document["network"]["data_loss"] = {
            "probability": 0.25,
            "start_ns": 0,
            "duration_ns": 1,
            "scope": ["all"],
            "rng_stream": 51,
            "retransmission_timeout_ns": 100,
            "max_retransmission_retries": 1,
        }
        with tempfile.TemporaryDirectory() as temporary_directory:
            profile_path = Path(temporary_directory) / "invalid.json"
            profile_path.write_text(json.dumps(document), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "data_loss.scope"):
                load_profile(profile_path)

    def test_materialization_covers_every_profile_training_step(self) -> None:
        document = json.loads(self.profile_path.read_text(encoding="utf-8"))
        document["steps"] = 6
        with tempfile.TemporaryDirectory() as temporary_directory:
            profile_path = Path(temporary_directory) / "six_steps.json"
            output = Path(temporary_directory) / "experiment"
            profile_path.write_text(json.dumps(document), encoding="utf-8")
            manifest = materialize(profile_path, output)

            with (output / "clr_mask.csv").open(newline="", encoding="utf-8") as handle:
                mask_rows = list(csv.DictReader(handle))
            policy = json.loads((output / "experiment.json").read_text(encoding="utf-8"))
            self.assertEqual([row["step_id"] for row in mask_rows], [str(step) for step in range(1, 7)])
            self.assertEqual(
                set(policy["selection_probability_by_step"]),
                {str(step) for step in range(1, 7)},
            )
            self.assertEqual(manifest["clr_schedule"]["steps"], 6)

    def test_llama3_profile_has_one_1gib_dp_bucket_per_step(self) -> None:
        profile_path = REPOSITORY_ROOT / "experiments/ring_3d/profiles/llama3_70b_16.json"
        profile = load_profile(profile_path)
        self.assertIsNotNone(profile.model)
        with tempfile.TemporaryDirectory() as temporary_directory:
            output = Path(temporary_directory) / "experiment"
            manifest = materialize(profile_path, output)

            self.assertEqual(manifest["ranks"], 16)
            self.assertEqual(
                manifest["model_trace"]["parameter_count"], 70_000_000_000
            )
            self.assertEqual(
                manifest["model_trace"]["gradient_bytes_per_rank"], 17_500_000_000
            )
            self.assertEqual(
                manifest["model_trace"]["nominal_model_gradient_bucket_bytes"],
                1_000_000_000,
            )
            self.assertEqual(
                manifest["model_trace"]["simulated_gradient_bucket_bytes"],
                1_073_741_824,
            )
            policy = json.loads((output / "experiment.json").read_text(encoding="utf-8"))
            self.assertEqual([flow["src"] for flow in policy["microburst"]["flows"]], list(range(7)))
            self.assertEqual({flow["dst"] for flow in policy["microburst"]["flows"]}, {8})
            self.assertEqual(
                {flow["size_bytes"] for flow in policy["microburst"]["flows"]},
                {128 * 1024 * 1024},
            )

            trace_path = output / "workload/ring_3d.8.et"
            dp_bytes_by_step: dict[int, int] = {}
            dp_buckets_by_step: dict[int, int] = {}
            with trace_path.open("rb") as trace:
                metadata = GlobalMetadata()
                self.assertTrue(decodeMessage(trace, metadata))
                while True:
                    node = Node()
                    if not decodeMessage(trace, node):
                        break
                    attributes = {attribute.name: attribute for attribute in node.attr}
                    if (
                        attributes.get("parallelism_domain")
                        and attributes["parallelism_domain"].string_val == "dp"
                    ):
                        step = attributes["training_step"].uint64_val
                        dp_bytes_by_step[step] = dp_bytes_by_step.get(step, 0) + attributes[
                            "comm_size"
                        ].uint64_val
                        dp_buckets_by_step[step] = dp_buckets_by_step.get(step, 0) + 1
            self.assertEqual(
                dp_bytes_by_step,
                {1: 1_073_741_824, 2: 1_073_741_824, 3: 1_073_741_824},
            )
            self.assertEqual(dp_buckets_by_step, {1: 1, 2: 1, 3: 1})

    def test_100b_profiles_materialize_clos_and_switch_ring(self) -> None:
        expected_topologies = {
            "model_100b_256_clos.json": {
                "kind": "clos",
                "header": (288, 32, 512),
                "description": "Two-stage leaf-spine Clos",
            },
            "model_100b_256_ring.json": {
                "kind": "ring",
                "header": (512, 256, 512),
                "description": "Host-attached bidirectional switch ring",
            },
        }
        for profile_name, expected in expected_topologies.items():
            with self.subTest(profile=profile_name):
                profile_path = (
                    REPOSITORY_ROOT / "experiments/ring_3d/profiles" / profile_name
                )
                profile = load_profile(profile_path)
                layout = build_topology(profile.network, profile.ranks)
                self.assertEqual(profile.ranks, 256)
                self.assertEqual(layout.kind, expected["kind"])
                self.assertEqual(
                    (layout.node_count, len(layout.switch_ids), len(layout.links)),
                    expected["header"],
                )
                if expected["kind"] == "ring":
                    self.assertEqual(layout.links[0].source, 0)
                    self.assertEqual(layout.links[0].destination, 256)
                    self.assertEqual(layout.links[255].source, 255)
                    self.assertEqual(layout.links[255].destination, 511)
                    self.assertEqual(layout.links[256].source, 256)
                    self.assertEqual(layout.links[256].destination, 257)
                    self.assertEqual(layout.links[-1].source, 511)
                    self.assertEqual(layout.links[-1].destination, 256)

                with tempfile.TemporaryDirectory() as temporary_directory:
                    output = Path(temporary_directory) / "experiment"
                    manifest = materialize(profile_path, output)
                    topology_lines = (output / "topology.txt").read_text(
                        encoding="utf-8"
                    ).splitlines()
                    self.assertEqual(
                        tuple(map(int, topology_lines[0].split())), expected["header"]
                    )
                    self.assertEqual(len(topology_lines), expected["header"][2] + 2)
                    self.assertEqual(
                        manifest["physical_topology"]["kind"], expected["kind"]
                    )
                    self.assertEqual(
                        manifest["physical_topology"]["description"],
                        expected["description"],
                    )
                    self.assertEqual(
                        manifest["model_trace"]["parameter_count"], 100_000_000_000
                    )
                    self.assertEqual(
                        manifest["model_trace"]["gradient_bytes_per_rank"],
                        6_250_000_000,
                    )
                    self.assertEqual(
                        manifest["model_trace"]["gradient_bucket_count"], 20
                    )
                    self.assertEqual(
                        manifest["model_trace"]["gradient_bucket_bytes"], 312_500_000
                    )
                    self.assertEqual(
                        len(list((output / "workload").glob("ring_3d.*.et"))), 256
                    )
                    dp_bucket_count: dict[int, int] = {}
                    dp_bytes: dict[int, int] = {}
                    with (output / "workload/ring_3d.0.et").open("rb") as trace:
                        metadata = GlobalMetadata()
                        self.assertTrue(decodeMessage(trace, metadata))
                        while True:
                            node = Node()
                            if not decodeMessage(trace, node):
                                break
                            attributes = {
                                attribute.name: attribute for attribute in node.attr
                            }
                            if attributes.get("parallelism_domain") and (
                                attributes["parallelism_domain"].string_val == "dp"
                            ):
                                step = attributes["training_step"].uint64_val
                                dp_bucket_count[step] = (
                                    dp_bucket_count.get(step, 0) + 1
                                )
                                dp_bytes[step] = dp_bytes.get(step, 0) + attributes[
                                    "comm_size"
                                ].uint64_val
                    self.assertEqual(dp_bucket_count, {1: 20, 2: 20, 3: 20})
                    self.assertEqual(
                        dp_bytes,
                        {1: 6_250_000_000, 2: 6_250_000_000, 3: 6_250_000_000},
                    )

    def test_ring_network_rejects_clos_only_fields(self) -> None:
        profile_path = (
            REPOSITORY_ROOT / "experiments/ring_3d/profiles/model_100b_256_ring.json"
        )
        document = json.loads(profile_path.read_text(encoding="utf-8"))
        document["network"]["spine_count"] = 16
        with tempfile.TemporaryDirectory() as temporary_directory:
            invalid_profile = Path(temporary_directory) / "invalid.json"
            invalid_profile.write_text(json.dumps(document), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "unknown network keys"):
                load_profile(invalid_profile)

    def test_trace_has_explicit_domains_and_overlap_dependency(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            output = Path(temporary_directory) / "experiment"
            materialize(self.profile_path, output)
            trace_path = output / "workload/ring_3d.0.et"
            nodes: list[Node] = []
            with trace_path.open("rb") as trace:
                metadata = GlobalMetadata()
                self.assertTrue(decodeMessage(trace, metadata))
                while True:
                    node = Node()
                    if not decodeMessage(trace, node):
                        break
                    nodes.append(node)

            attributes = {
                node.name: {attribute.name: attribute for attribute in node.attr}
                for node in nodes
            }
            self.assertEqual(
                attributes["step_1_tp_all_reduce"]["parallelism_domain"].string_val,
                "tp",
            )
            self.assertEqual(
                attributes["step_1_pp_send_to_2"]["parallelism_domain"].string_val,
                "pp",
            )
            self.assertEqual(
                attributes["step_1_dp_all_reduce_bucket_0"]["parallelism_domain"].string_val,
                "dp",
            )

            ids = {node.name: node.id for node in nodes}
            optimizer = next(node for node in nodes if node.name == "step_1_optimizer")
            bucket_one = next(node for node in nodes if node.name == "step_1_backward_bucket_1")
            self.assertIn(ids["step_1_dp_all_reduce_bucket_0"], optimizer.ctrl_deps)
            self.assertIn(ids["step_1_dp_all_reduce_bucket_1"], optimizer.ctrl_deps)
            self.assertNotIn(ids["step_1_dp_all_reduce_bucket_0"], bucket_one.ctrl_deps)


if __name__ == "__main__":
    unittest.main()