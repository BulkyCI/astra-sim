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