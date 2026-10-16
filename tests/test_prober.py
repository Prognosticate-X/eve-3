"""Tests for System 2 Bayesian Prober and Information Gain calculations."""

import math
from eve3.system1_proposer.sandbox import CandidateProgram
from eve3.system2_falsifier.bayesian_prober import BayesianProber, entropy, renormalize


def test_entropy_and_renormalize():
    assert entropy([1.0]) == 0.0
    assert math.isclose(entropy([0.5, 0.5]), 1.0, rel_tol=1e-5)

    probs = [0.2, 0.3, 0.5]
    sub = renormalize(probs, [0, 2])
    assert math.isclose(sum(sub), 1.0)
    assert math.isclose(sub[0], 0.2 / 0.7)


def test_bayesian_information_gain():
    prober = BayesianProber(cost_penalty_lambda=0.01)

    p1 = CandidateProgram("(map (lambda (a) (+ a 1)) x)")
    p2 = CandidateProgram("(map (lambda (a) (+ a 2)) x)")
    hypotheses = [p1, p2]

    beliefs = prober.initialize_beliefs(hypotheses)
    assert len(beliefs) == 2
    assert math.isclose(sum(beliefs), 1.0)

    # Distinguishing probe: [0] -> p1 gives [1], p2 gives [2]
    ig = prober.compute_information_gain(hypotheses, beliefs, probe_input=[0])
    # Distinguishes both with 50/50 prior, IG should be ~1.0 bit
    assert ig > 0.9

    # Non-distinguishing probe for identical behaviors (if any) or dummy
    best_probe, score = prober.select_best_probe(hypotheses, beliefs, candidate_probes=[[0], [5]])
    assert best_probe in ([0], [5])


def test_posterior_update_and_collapse_prevention():
    prober = BayesianProber(smoothing_epsilon=1e-4)

    p1 = CandidateProgram("(map (lambda (a) (+ a 1)) x)")
    p2 = CandidateProgram("(map (lambda (a) (+ a 2)) x)")
    hypotheses = [p1, p2]
    beliefs = [0.5, 0.5]

    # Observe output matching p1
    new_beliefs = prober.update_beliefs(hypotheses, beliefs, probe_input=[1], observed_output=[2])
    assert new_beliefs[0] > 0.99
    assert new_beliefs[1] < 0.01

    # Test collapse scenario (neither matches)
    collapsed_beliefs = prober.update_beliefs(hypotheses, beliefs, probe_input=[1], observed_output=[999])
    assert math.isclose(sum(collapsed_beliefs), 1.0)
