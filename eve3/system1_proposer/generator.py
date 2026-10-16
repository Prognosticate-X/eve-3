"""System 1: Hypothesis Generator (Intuition Engine).

Combines local LLM generation (via Apple Silicon MLX) with an enumerative
grammar fallback for zero-dependency local testing.
"""

from typing import Any, Dict, List, Optional, Tuple

from eve3.config import EveConfig
from eve3.system1_proposer.sandbox import CandidateProgram, ProgramSandbox


class HypothesisGenerator:
    """Proposes candidate programs in the DSL satisfying observed I/O pairs."""

    def __init__(self, config: Optional[EveConfig] = None):
        self.config = config or EveConfig()
        self.sandbox = ProgramSandbox(timeout_per_exec=self.config.sandbox_timeout_seconds)
        self._mlx_model = None
        self._mlx_tokenizer = None

    def build_prompt(
        self,
        examples: List[Tuple[Any, Any]],
        library_primitives: Optional[List[str]] = None,
        crystallized_operators: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        """Construct prompt for local LLM (e.g. Qwen2.5-Coder-3B)."""
        prims = list(library_primitives or [
            "map", "filter", "fold", "head", "tail", "cons", "reverse", "sum",
            "+", "-", "*", "inc", "dec", "is_even", "is_odd", "gt", "lt", "eq"
        ])
        if crystallized_operators:
            for op in crystallized_operators:
                prims.append(f"{op['operator_name']}(arity={op['arity']})")

        ex_str = "\n".join([f"Input: {inp} -> Output: {out}" for inp, out in examples])

        prompt = (
            "You are an expert neurosymbolic program synthesizer for EVE-3.\n"
            f"Available DSL primitives: {', '.join(prims)}\n"
            "DSL Syntax is Lisp S-expressions: (op arg1 arg2 ...), (lambda (x) body), (if c t e), [list].\n"
            "Given the following input-output examples, generate 5 candidate DSL programs that transform 'x' to the output.\n"
            "Return only valid DSL expressions, one per line:\n\n"
            f"Examples:\n{ex_str}\n\n"
            "Candidates:\n"
        )
        return prompt

    def generate_hypotheses(
        self,
        examples: List[Tuple[Any, Any]],
        library_primitives: Optional[List[str]] = None,
        crystallized_operators: Optional[List[Dict[str, Any]]] = None,
        max_candidates: int = 10,
    ) -> List[CandidateProgram]:
        """Generate verified candidates that pass all current examples."""
        raw_candidates = self._generate_raw_proposals(
            examples, library_primitives, crystallized_operators, max_candidates
        )
        return self.sandbox.filter_valid_candidates(raw_candidates, examples)

    def _generate_raw_proposals(
        self,
        examples: List[Tuple[Any, Any]],
        library_primitives: Optional[List[str]] = None,
        crystallized_operators: Optional[List[Dict[str, Any]]] = None,
        max_candidates: int = 10,
    ) -> List[str]:
        """Generate raw S-expression proposal strings."""
        if self._can_use_mlx():
            try:
                return self._generate_with_mlx(
                    examples, library_primitives, crystallized_operators, max_candidates
                )
            except Exception:
                pass  # Fall back to heuristic synthesizer

        return self._heuristic_synthesizer(
            examples, library_primitives, crystallized_operators, max_candidates
        )

    def _can_use_mlx(self) -> bool:
        try:
            import mlx.core
            import mlx_lm
            return True
        except ImportError:
            return False

    def _generate_with_mlx(
        self,
        examples: List[Tuple[Any, Any]],
        library_primitives: Optional[List[str]],
        crystallized_operators: Optional[List[Dict[str, Any]]],
        max_candidates: int,
    ) -> List[str]:
        """Generate candidate programs using MLX."""
        import mlx_lm
        if self._mlx_model is None:
            self._mlx_model, self._mlx_tokenizer = mlx_lm.load(self.config.model_name)

        prompt = self.build_prompt(examples, library_primitives, crystallized_operators)
        response = mlx_lm.generate(
            self._mlx_model,
            self._mlx_tokenizer,
            prompt=prompt,
            temp=self.config.generation_temperature,
            max_tokens=256,
        )
        lines = [line.strip() for line in response.split("\n") if line.strip().startswith("(")]
        return lines[:max_candidates]

    def _heuristic_synthesizer(
        self,
        examples: List[Tuple[Any, Any]],
        library_primitives: Optional[List[str]] = None,
        crystallized_operators: Optional[List[Dict[str, Any]]] = None,
        max_candidates: int = 10,
    ) -> List[str]:
        """Built-in heuristic generator for common transformations and learned operators."""
        if not examples:
            return []

        templates = [
            # Identity and simple lists
            "x",
            "(reverse x)",
            "(tail x)",
            # Mapping transformations
            "(map (lambda (a) (+ a 1)) x)",
            "(map (lambda (a) (+ a 2)) x)",
            "(map (lambda (a) (- a 1)) x)",
            "(map (lambda (a) (* a 2)) x)",
            "(map (lambda (a) (* a a)) x)",
            "(map (lambda (a) (inc a)) x)",
            "(map (lambda (a) (dec a)) x)",
            "(map (lambda (a) (neg a)) x)",
            # Filtering
            "(filter (lambda (a) (is_even a)) x)",
            "(filter (lambda (a) (is_odd a)) x)",
            "(filter (lambda (a) (gt a 0)) x)",
            "(filter (lambda (a) (gt a 2)) x)",
            "(filter (lambda (a) (gt a 3)) x)",
            "(filter (lambda (a) (lt a 5)) x)",
            # Aggregation & Reductions
            "(sum x)",
            "(length x)",
            "(head x)",
            "(fold (lambda (acc item) (+ acc item)) 0 x)",
            "(fold (lambda (acc item) (+ acc 1)) 0 x)",
            "(fold (lambda (acc item) (* acc item)) 1 x)",
            # Chained transformations
            "(reverse (map (lambda (a) (* a 2)) x))",
            "(map (lambda (a) (* a 2)) (reverse x))",
            "(filter (lambda (a) (is_even a)) (map (lambda (a) (+ a 1)) x))",
            "(sum (filter (lambda (a) (is_even a)) x))",
        ]

        # Dynamically inject learned crystallized operators into candidate templates
        if crystallized_operators:
            for op in crystallized_operators:
                op_name = op.get("operator_name")
                arity = op.get("arity", 1)
                if arity == 1:
                    templates.insert(0, f"({op_name} x)")
                elif arity == 2:
                    for k in (1, 2, 0, -1):
                        templates.insert(0, f"({op_name} {k} x)")

        # Inject custom library primitives if supplied
        if library_primitives:
            for prim in library_primitives:
                templates.append(f"({prim} x)")

        candidates = []
        for t in templates:
            candidates.append(t)
            if len(candidates) >= max_candidates * 3:
                break
        return candidates
