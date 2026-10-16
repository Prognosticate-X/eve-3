"""Tests for Discovery Tree and Replay Simulator (RSI)."""

from eve3.discovery.tree import DiscoveryNode, DiscoveryTree, ReplaySimulator


def test_discovery_tree_and_replay():
    tree = DiscoveryTree(task_id="test_task_01")

    root_id = tree.add_node(
        action_type="propose",
        payload={"candidates": ["(reverse x)", "(map (lambda (a) (+ a 1)) x)"]},
        cost=1.0,
    )

    probe_id = tree.add_node(
        action_type="probe",
        payload={"probe": [1, 2], "observed": [2, 3]},
        parent_id=root_id,
        cost=0.5,
    )

    verify_id = tree.add_node(
        action_type="verify",
        payload={"code": "(map (lambda (a) (+ a 1)) x)"},
        parent_id=probe_id,
        cost=0.2,
        outcome="verified",
    )

    assert tree.total_cost() == 1.7

    # Serialize & deserialize
    json_str = tree.to_json()
    reconstructed = DiscoveryTree.from_json(json_str)
    assert len(reconstructed.nodes) == 3

    # Replay simulation: test policy priority
    simulator = ReplaySimulator(tree)
    # Policy that prioritizes verification nodes
    res = simulator.evaluate_policy_sample_efficiency(
        policy_priority_fn=lambda node: 10.0 if node.action_type == "verify" else 1.0
    )
    assert res["found_verified"] is True
    assert res["simulated_cost"] == 0.2
