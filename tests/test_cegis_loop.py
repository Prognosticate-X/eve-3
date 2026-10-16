"""Tests for end-to-end CEGIS active synthesis loop."""

from eve3.config import EveConfig
from eve3.system2_falsifier.cegis_loop import CEGISLoop


def test_cegis_active_synthesis_loop():
    config = EveConfig(max_falsification_rounds=5, probe_cost_penalty_lambda=0.01)
    loop = CEGISLoop(config)

    # Ground-truth function: increment list elements by 1
    def oracle_increment(lst):
        return [x + 1 for x in lst]

    initial_examples = [
        ([1, 2], [2, 3]),
    ]

    result = loop.run_synthesis(initial_examples, oracle_fn=oracle_increment)
    assert result.converged
    assert result.verified_program is not None
    # Program should evaluate correctly on unseen input
    test_out = result.verified_program.evaluate([10, 20])
    assert test_out == [11, 21]
