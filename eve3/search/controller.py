"""Proposal & Search Controller for EVE-3.

Coordinates multi-strategy candidate generation across:
1. Neural intuition generator (MLX / LLM)
2. Symbolic enumerator (bounded depth AST search)
3. Crystallized knowledge library abstractions
"""

from typing import Any, Dict, List, Optional, Tuple

from eve3.config import EveConfig
from eve3.models import CandidateProgram
from eve3.search.enumerator import SymbolicEnumerator
from eve3.system1_proposer.generator import HypothesisGenerator
from eve3.system1_proposer.sandbox import ProgramSandbox
from eve3.system3_crystallizer.library import KnowledgeLibrary


class SearchController:
    """Unified search controller coordinating neural and symbolic proposal strategies."""

    def __init__(
        self,
        config: Optional[EveConfig] = None,
        knowledge_library: Optional[KnowledgeLibrary] = None,
    ):
        self.config = config or EveConfig()
        self.knowledge_library = knowledge_library
        self.generator = HypothesisGenerator(self.config)
        self.enumerator = SymbolicEnumerator(max_depth=self.config.enumerator_max_depth)
        self.sandbox = ProgramSandbox(
            timeout_per_exec=self.config.sandbox_timeout_seconds,
            max_ast_depth=self.config.max_ast_depth,
            step_budget=self.config.sandbox_step_budget,
            max_output_size=self.config.sandbox_max_output_size,
            max_integer_bits=self.config.sandbox_max_integer_bits,
            max_recursion_depth=self.config.sandbox_max_recursion_depth,
        )
        if self.knowledge_library is not None:
            active_ops = self.knowledge_library.get_crystallized_operators()
            self.sandbox.register_crystallized_operators(active_ops)

    def propose_candidates(
        self,
        examples: List[Tuple[Any, Any]],
        strategy: str = "hybrid",  # "hybrid", "neural_only", "symbolic_only", "library_only"
        max_candidates: int = 16,
    ) -> List[CandidateProgram]:
        """Propose deduplicated, sandboxed candidate programs satisfying visible examples."""
        if not examples:
            return []

        sample_in = examples[0][0]
        domain_hint = "list" if isinstance(sample_in, list) else "int"
        mode = self.config.proposer_mode

        crystallized_ops: List[Dict[str, Any]] = []
        if self.knowledge_library is not None:
            crystallized_ops = self.knowledge_library.get_crystallized_operators()
            self.sandbox.register_crystallized_operators(crystallized_ops)

        proposals: List[CandidateProgram] = []
        seen_canonical = set()

        def add_candidates(cands: List[CandidateProgram]):
            for c in cands:
                canonical = getattr(c, "canonical_code", c.code_str)
                if canonical not in seen_canonical and len(proposals) < max_candidates:
                    seen_canonical.add(canonical)
                    proposals.append(c)

        # C.2: Constant pool de-benchmarking: constants strictly from {0, 1} U values appearing in examples
        extracted_consts = {0, 1}
        for inp, out in examples:
            for val in (inp, out):
                if isinstance(val, int):
                    extracted_consts.add(val)
                elif isinstance(val, (list, tuple)):
                    for item in val:
                        if isinstance(item, int):
                            extracted_consts.add(item)
        const_pool = sorted(extracted_consts)

        if mode == "llm_only":
            llm_cands = self.generator.generate_hypotheses(
                examples=examples,
                crystallized_operators=crystallized_ops,
                max_candidates=max_candidates,
            )
            add_candidates(llm_cands)
            return proposals

        if mode == "llm_plus_enumeration":
            if strategy in ("hybrid", "neural_only"):
                llm_cands = self.generator.generate_hypotheses(
                    examples=examples,
                    crystallized_operators=crystallized_ops,
                    max_candidates=max_candidates,
                )
                add_candidates(llm_cands)
            if strategy in ("hybrid", "symbolic_only"):
                enum_cands = self.enumerator.enumerate_candidates(
                    domain_hint=domain_hint,
                    constant_pool=const_pool,
                    max_candidates=max(max_candidates * 10, 160),
                    mode="generic_enumeration",
                )
                filtered = self.sandbox.filter_valid_candidates(
                    enum_cands, examples, created_by="enumerator"
                )
                add_candidates(filtered)
            if strategy in ("hybrid", "library_only") and crystallized_ops:
                self._add_library_candidates(crystallized_ops, examples, add_candidates)
            return proposals

        if mode == "generic_enumeration":
            if strategy in ("hybrid", "symbolic_only", "neural_only"):
                enum_cands = self.enumerator.enumerate_candidates(
                    domain_hint=domain_hint,
                    constant_pool=const_pool,
                    max_candidates=max(max_candidates * 10, 160),
                    mode="generic_enumeration",
                )
                filtered = self.sandbox.filter_valid_candidates(
                    enum_cands, examples, created_by="enumerator"
                )
                add_candidates(filtered)
            if strategy in ("hybrid", "library_only") and crystallized_ops:
                self._add_library_candidates(crystallized_ops, examples, add_candidates)
            return proposals

        # mode == "leaky_templates" (baseline control only)
        if strategy in ("hybrid", "symbolic_only"):
            enum_cands = self.enumerator.enumerate_candidates(
                domain_hint=domain_hint,
                max_candidates=max_candidates * 2,
                mode="leaky_templates",
            )
            filtered = self.sandbox.filter_valid_candidates(
                enum_cands, examples, created_by="enumerator"
            )
            add_candidates(filtered)

        if strategy in ("hybrid", "neural_only"):
            neural_cands = self.generator.generate_hypotheses(
                examples=examples,
                crystallized_operators=crystallized_ops,
                max_candidates=max_candidates,
            )
            add_candidates(neural_cands)

        if strategy in ("hybrid", "library_only") and crystallized_ops:
            self._add_library_candidates(crystallized_ops, examples, add_candidates)

        return proposals

    def _add_library_candidates(
        self,
        crystallized_ops: List[Dict[str, Any]],
        examples: List[Tuple[Any, Any]],
        add_fn: Any,
    ) -> None:
        lib_codes: List[Tuple[str, str]] = []
        capped_ops = crystallized_ops[: self.config.max_active_library_operators]
        for op in capped_ops:
            op_name = op["operator_name"]
            arity = op.get("arity", 1)
            if arity == 1:
                lib_codes.append((f"({op_name} x)", f"library:{op_name}"))
            elif arity == 2:
                for k in (1, 2, 0, -1):
                    lib_codes.append((f"({op_name} {k} x)", f"library:{op_name}"))
        lib_filtered = self.sandbox.filter_valid_candidates(
            lib_codes, examples, created_by="library"
        )
        add_fn(lib_filtered)
