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
        self.enumerator = SymbolicEnumerator(max_depth=3)
        self.sandbox = ProgramSandbox(timeout_per_exec=self.config.sandbox_timeout_seconds)

    def propose_candidates(
        self,
        examples: List[Tuple[Any, Any]],
        strategy: str = "hybrid",  # "hybrid", "neural_only", "symbolic_only", "library_only"
        max_candidates: int = 16,
    ) -> List[CandidateProgram]:
        """Propose deduplicated, sandboxed candidate programs satisfying visible examples."""
        if not examples:
            return []

        # Determine domain hint based on input types
        sample_in = examples[0][0]
        domain_hint = "list" if isinstance(sample_in, list) else "int"

        # Fetch crystallized operators if library is active
        crystallized_ops: List[Dict[str, Any]] = []
        if self.knowledge_library is not None:
            crystallized_ops = self.knowledge_library.get_crystallized_operators()

        proposals: List[CandidateProgram] = []
        seen_codes = set()

        def add_candidates(cands: List[CandidateProgram]):
            for c in cands:
                if c.code_str not in seen_codes and len(proposals) < max_candidates:
                    seen_codes.add(c.code_str)
                    proposals.append(c)

        # 1. Symbolic Enumerator
        if strategy in ("hybrid", "symbolic_only"):
            enum_cands = self.enumerator.enumerate_candidates(
                domain_hint=domain_hint, max_candidates=max_candidates * 2
            )
            raw_codes = [c.code_str for c in enum_cands]
            filtered = self.sandbox.filter_valid_candidates(raw_codes, examples, created_by="enumerator")
            add_candidates(filtered)

        # 2. Neural / Heuristic Proposal Generator
        if strategy in ("hybrid", "neural_only"):
            neural_cands = self.generator.generate_hypotheses(
                examples=examples,
                crystallized_operators=crystallized_ops,
                max_candidates=max_candidates,
            )
            add_candidates(neural_cands)

        # 3. Crystallized Library Instantiations
        if strategy in ("hybrid", "library_only") and crystallized_ops:
            lib_codes = []
            for op in crystallized_ops:
                op_name = op["operator_name"]
                arity = op.get("arity", 1)
                if arity == 1:
                    lib_codes.append(f"({op_name} x)")
                elif arity == 2:
                    for k in (1, 2, 0, -1):
                        lib_codes.append(f"({op_name} {k} x)")
            lib_filtered = self.sandbox.filter_valid_candidates(lib_codes, examples, created_by="library")
            add_candidates(lib_filtered)

        return proposals
