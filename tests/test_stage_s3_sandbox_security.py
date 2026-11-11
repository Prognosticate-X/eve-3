"""Tests for Stage S3 Sandbox Security & Non-blocking Timeout Guardrails [H11]."""

import time
import pytest
from eve3.dsl.ast import (
    ASTNode,
    ApplyNode,
    ConstNode,
    ExecutionContext,
    ExecutionRecursionLimitExceeded,
    ExecutionSizeLimitExceeded,
    ExecutionStepLimitExceeded,
    VarNode,
)
from eve3.dsl.interpreter import DSLInterpreter, ExecutionTimeoutError
from eve3.system1_proposer.sandbox import ProgramSandbox


class TestStageS3SandboxSecurity:
    """Validate non-blocking timeout, memory bomb containment, and recursion guardrails."""

    def test_timeout_is_non_blocking(self):
        """H11 / Vulnerability 1: Hard timeout budget returns immediately without blocking worker thread."""
        interpreter = DSLInterpreter()
        # Register a primitive that sleeps for 2 seconds
        interpreter.base_env["slow_sleep"] = lambda: time.sleep(1.5)

        t0 = time.perf_counter()
        with pytest.raises(ExecutionTimeoutError) as exc_info:
            interpreter.run("(slow_sleep)", 0, timeout_seconds=0.1)
        elapsed = time.perf_counter() - t0

        assert "hard timeout budget" in str(exc_info.value)
        # Main thread must return quickly (< 0.5s), NOT wait for 1.5s
        assert elapsed < 0.6, f"Timeout blocked the main thread! Elapsed: {elapsed:.3f}s"

    def test_fold_memory_bomb_caught_by_size_limit(self):
        """H11 / Vulnerability 2: Repeated list doubling in fold triggers ExecutionSizeLimitExceeded."""
        interpreter = DSLInterpreter()
        # (fold (lambda (acc item) (concat acc acc)) [1] x)
        # on length-12 input doubles list 12 times -> 4096 elements > default limit 1000
        prog = "(fold (lambda (acc item) (concat acc acc)) [1] x)"
        inp = list(range(12))

        with pytest.raises(ExecutionSizeLimitExceeded):
            interpreter.run(prog, inp, max_output_size=1000)

    def test_fold_integer_squaring_bomb_caught_by_bit_limit(self):
        """H11 / Vulnerability 2: Repeated squaring in fold triggers ExecutionSizeLimitExceeded."""
        interpreter = DSLInterpreter()
        # Repeated squaring: 2^(2^12) -> exceeds 2048 bit budget in 12 steps
        prog = "(fold (lambda (acc item) (* acc acc)) 2 x)"
        inp = list(range(12))

        with pytest.raises(ExecutionSizeLimitExceeded):
            interpreter.run(prog, inp, max_integer_bits=2048)

    def test_call_chain_recursion_limit(self):
        """H11: Deep nested call chains trigger ExecutionRecursionLimitExceeded."""
        interpreter = DSLInterpreter()
        # Construct nested calls (inc (inc (inc ... x))) beyond max_recursion_depth
        node: ASTNode = VarNode("x")
        for _ in range(60):
            node = ApplyNode("inc", [node])

        with pytest.raises(ExecutionRecursionLimitExceeded):
            interpreter.run(node, 0, max_recursion_depth=50)

    def test_sandbox_filters_and_records_all_security_rejections(self):
        """H11: ProgramSandbox catches and categorizes memory/timeout/recursion bombs."""
        sandbox = ProgramSandbox(
            timeout_per_exec=0.1,
            max_output_size=500,
            max_integer_bits=1024,
            max_recursion_depth=30,
        )
        sandbox.interpreter.base_env["slow_sleep"] = lambda: time.sleep(1.5)

        candidates = [
            "(slow_sleep)",
            "(fold (lambda (acc item) (concat acc acc)) [1] x)",
            "(fold (lambda (acc item) (* acc acc)) 2 x)",
        ]
        examples = [(list(range(12)), 42)]

        valid = sandbox.filter_valid_candidates(candidates, examples)
        assert len(valid) == 0

        rejections = sandbox.diagnostics.sandbox_rejections
        assert rejections.get("ExecutionTimeoutError", 0) >= 1
        assert rejections.get("ExecutionSizeLimitExceeded", 0) >= 1
