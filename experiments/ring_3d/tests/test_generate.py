from __future__ import annotations

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

            policy = json.loads((output / "experiment.json").read_text(encoding="utf-8"))
            self.assertEqual(policy["eligibility"], "dp_all_reduce_only")
            self.assertEqual(policy["drop_probability_by_step"], {"1": 0.0, "2": 0.1, "3": 0.1})
            self.assertEqual(policy["provenance"]["priority_group"], 1)
            self.assertEqual(manifest["ranks"], 8)

    def test_incast_profile_materializes_simultaneous_many_to_one_microburst(self) -> None:
        profile_path = REPOSITORY_ROOT / "experiments/ring_3d/profiles/incast_8.json"
        with tempfile.TemporaryDirectory() as temporary_directory:
            output = Path(temporary_directory) / "experiment"
            materialize(profile_path, output)

            policy = json.loads((output / "experiment.json").read_text(encoding="utf-8"))
            flows = policy["microburst"]["flows"]
            self.assertEqual(len(flows), 7)
            self.assertEqual({flow["dst"] for flow in flows}, {4})
            self.assertEqual({flow["src"] for flow in flows}, {0, 1, 2, 3, 5, 6, 7})
            self.assertEqual({flow["size_bytes"] for flow in flows}, {32 * 1024 * 1024})
            self.assertEqual({flow["offset_ns"] for flow in flows}, {0})

    def test_lossless_override_preserves_enabled_microburst(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            output = Path(temporary_directory) / "experiment"
            materialize(
                self.profile_path,
                output,
                drop_probabilities={"1": 0.0, "2": 0.0, "3": 0.0},
            )

            policy = json.loads((output / "experiment.json").read_text(encoding="utf-8"))
            self.assertTrue(policy["enabled"])
            self.assertTrue(policy["microburst"]["enabled"])
            self.assertEqual(policy["drop_probability_by_step"], {"1": 0.0, "2": 0.0, "3": 0.0})

    def test_100b_model_profile_has_exact_gradient_shard_and_dp_peer_incast(self) -> None:
        profile_path = REPOSITORY_ROOT / "experiments/ring_3d/profiles/model_100b_256.json"
        profile = load_profile(profile_path)
        self.assertIsNotNone(profile.model)
        with tempfile.TemporaryDirectory() as temporary_directory:
            output = Path(temporary_directory) / "experiment"
            manifest = materialize(profile_path, output)

            self.assertEqual(manifest["ranks"], 256)
            self.assertEqual(
                manifest["model_trace"]["parameter_count"], 100_000_000_000
            )
            self.assertEqual(
                manifest["model_trace"]["gradient_bytes_per_rank"], 6_250_000_000
            )
            policy = json.loads((output / "experiment.json").read_text(encoding="utf-8"))
            self.assertEqual(
                [flow["src"] for flow in policy["microburst"]["flows"]],
                [36, 68, 100, 132, 164, 196, 228],
            )
            self.assertEqual({flow["dst"] for flow in policy["microburst"]["flows"]}, {4})
            self.assertEqual({flow["size_bytes"] for flow in policy["microburst"]["flows"]}, {50_000_000})

            trace_path = output / "workload/ring_3d.4.et"
            dp_bytes_by_step: dict[int, int] = {}
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
            self.assertEqual(dp_bytes_by_step, {1: 6_250_000_000, 2: 6_250_000_000, 3: 6_250_000_000})

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