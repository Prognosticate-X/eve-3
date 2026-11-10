"""System 1: Hypothesis Generator (Intuition Engine).

Combines local LLM generation (via Apple Silicon MLX) with an enumerative
grammar fallback for zero-dependency local testing.
"""

import logging
import re
import time
from typing import Any, Dict, List, Optional, Tuple

from eve3.config import EveConfig
from eve3.models import Diagnostics
from eve3.system1_proposer.sandbox import CandidateProgram, ProgramSandbox

logger = logging.getLogger(__name__)

_BASE_HEURISTIC_TEMPLATES: List[Tuple[int, str]] = [
    # Identity and simple lists
    (1, "x"),
    (2, "(reverse x)"),
    (3, "(tail x)"),
    # Mapping transformations
    (4, "(map (lambda (a) (+ a 1)) x)"),
    (5, "(map (lambda (a) (+ a 2)) x)"),
    (6, "(map (lambda (a) (- a 1)) x)"),
    (7, "(map (lambda (a) (* a 2)) x)"),
    (8, "(map (lambda (a) (* a a)) x)"),
    (9, "(map (lambda (a) (inc a)) x)"),
    (10, "(map (lambda (a) (dec a)) x)"),
    (11, "(map (lambda (a) (neg a)) x)"),
    # Filtering
    (12, "(filter (lambda (a) (is_even a)) x)"),
    (13, "(filter (lambda (a) (is_odd a)) x)"),
    (14, "(filter (lambda (a) (gt a 0)) x)"),
    (15, "(filter (lambda (a) (gt a 2)) x)"),
    (16, "(filter (lambda (a) (gt a 3)) x)"),
    (17, "(filter (lambda (a) (lt a 5)) x)"),
    # Aggregation & Reductions
    (18, "(sum x)"),
    (19, "(length x)"),
    (20, "(head x)"),
    (21, "(fold (lambda (acc item) (+ acc item)) 0 x)"),
    (22, "(fold (lambda (acc item) (+ acc 1)) 0 x)"),
    (23, "(fold (lambda (acc item) (* acc item)) 1 x)"),
    # Chained transformations
    (24, "(reverse (map (lambda (a) (* a 2)) x))"),
    (25, "(map (lambda (a) (* a 2)) (reverse x))"),
    (26, "(filter (lambda (a) (is_even a)) (map (lambda (a) (+ a 1)) x))"),
    (27, "(sum (filter (lambda (a) (is_even a)) x))"),
]


class HypothesisGenerator:
    """Proposes candidate programs in the DSL satisfying observed I/O pairs."""

    _MLX_MODEL_CACHE: Dict[str, Tuple[Any, Any]] = {}

    def __init__(self, config: Optional[EveConfig] = None):
        self.config = config or EveConfig()
        self.sandbox = ProgramSandbox(
            timeout_per_exec=self.config.sandbox_timeout_seconds,
            max_ast_depth=self.config.max_ast_depth,
            step_budget=self.config.sandbox_step_budget,
            max_output_size=self.config.sandbox_max_output_size,
            max_integer_bits=self.config.sandbox_max_integer_bits,
            max_recursion_depth=self.config.sandbox_max_recursion_depth,
        )
        self.diagnostics = self.sandbox.diagnostics
        self._mlx_model = None
        self._mlx_tokenizer = None

    def build_prompt(
        self,
        examples: List[Tuple[Any, Any]],
        library_primitives: Optional[List[str]] = None,
        crystallized_operators: Optional[List[Dict[str, Any]]] = None,
        num_candidates: Optional[int] = None,
    ) -> str:
        """Construct prompt for local LLM (e.g. Qwen2.5-Coder-3B)."""
        k = num_candidates if num_candidates is not None else self.config.max_hypotheses_per_round
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
            f"Given the following input-output examples, generate {k} candidate DSL programs that transform 'x' to the output.\n"
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
        """Generate verified candidates that pass all current examples according to proposer_mode."""
        mode = self.config.proposer_mode

        if mode == "generic_enumeration":
            return []

        if mode in ("llm_only", "llm_plus_enumeration"):
            if not self._can_use_mlx():
                raise RuntimeError(
                    f"proposer_mode={mode!r} requires MLX-LM, but mlx / mlx_lm is not available"
                )
            try:
                tagged_llm = self._generate_with_mlx_provenance(
                    examples, library_primitives, crystallized_operators, max_candidates
                )
            except (RuntimeError, ValueError, TypeError, AttributeError, OSError, KeyError, ImportError) as exc:
                self.diagnostics.record_swallowed_error("generator._generate_raw_proposals", exc)
                if mode == "llm_only":
                    raise RuntimeError(f"LLM generation failed in llm_only mode: {exc}") from exc
                logger.warning("MLX generation failed in %s (%s: %s)", mode, type(exc).__name__, exc)
                return []
            return self.sandbox.filter_valid_candidates(tagged_llm, examples, created_by="llm")

        # mode == "leaky_templates" (retained only as control baseline)
        tagged_templates = self._heuristic_synthesizer_provenance(
            examples, library_primitives, crystallized_operators, max_candidates
        )
        return self.sandbox.filter_valid_candidates(tagged_templates, examples, created_by="heuristic")

    def _generate_raw_proposals(
        self,
        examples: List[Tuple[Any, Any]],
        library_primitives: Optional[List[str]] = None,
        crystallized_operators: Optional[List[Dict[str, Any]]] = None,
        max_candidates: int = 10,
    ) -> List[str]:
        """Generate raw S-expression proposal strings."""
        mode = self.config.proposer_mode
        if mode == "generic_enumeration":
            return []
        if mode in ("llm_only", "llm_plus_enumeration"):
            if not self._can_use_mlx():
                raise RuntimeError(f"proposer_mode={mode!r} requires MLX-LM")
            return self._generate_with_mlx(
                examples, library_primitives, crystallized_operators, max_candidates
            )
        return self._heuristic_synthesizer(
            examples, library_primitives, crystallized_operators, max_candidates
        )

    def _can_use_mlx(self) -> bool:
        try:
            import mlx.core  # noqa: F401
            import mlx_lm  # noqa: F401
            return True
        except ImportError:
            return False

    def _ensure_mlx_loaded(self) -> None:
        import mlx_lm
        if self._mlx_model is None:
            cached = self._MLX_MODEL_CACHE.get(self.config.model_name)
            if cached is not None:
                self._mlx_model, self._mlx_tokenizer = cached
            else:
                self._mlx_model, self._mlx_tokenizer = mlx_lm.load(self.config.model_name)
                self._MLX_MODEL_CACHE[self.config.model_name] = (self._mlx_model, self._mlx_tokenizer)

    @staticmethod
    def _extract_candidate_lines(response: str, max_candidates: int) -> List[str]:
        lines: List[str] = []
        for raw_line in response.split("\n"):
            s = raw_line.strip()
            if not s or s.startswith("```"):
                continue
            # Strip optional leading numbering such as "1. " or "- " and wrapping backticks
            s = re.sub(r"^(?:\d+[\.\)]\s*|[-*]\s*)", "", s).strip()
            if s.startswith("`") and s.endswith("`") and len(s) > 2:
                s = s[1:-1].strip()
            if s.startswith("(") or s == "x":
                lines.append(s)
        return lines[:max_candidates]

    def _generate_with_mlx_provenance(
        self,
        examples: List[Tuple[Any, Any]],
        library_primitives: Optional[List[str]],
        crystallized_operators: Optional[List[Dict[str, Any]]],
        max_candidates: int,
    ) -> List[Tuple[str, str]]:
        """Generate candidate programs using MLX with sampler API and provenance tags."""
        import mlx_lm
        from mlx_lm.sample_utils import make_sampler

        self._ensure_mlx_loaded()
        prompt = self.build_prompt(
            examples,
            library_primitives,
            crystallized_operators,
            num_candidates=max_candidates,
        )

        formatted_prompt = prompt
        if hasattr(self._mlx_tokenizer, "apply_chat_template"):
            try:
                chat_str = self._mlx_tokenizer.apply_chat_template(
                    [{"role": "user", "content": prompt}],
                    tokenize=False,
                    add_generation_prompt=True,
                )
                if isinstance(chat_str, str) and chat_str:
                    formatted_prompt = chat_str
            except (TypeError, ValueError, AttributeError, KeyError) as exc:
                self.diagnostics.record_swallowed_error("generator.apply_chat_template", exc)
                logger.debug("Chat template formatting fallback: %s", exc)

        sampler = make_sampler(temp=float(self.config.generation_temperature))
        self.diagnostics.record_llm_call()
        call_idx = self.diagnostics.llm_calls

        t0 = time.perf_counter()
        response = mlx_lm.generate(
            self._mlx_model,
            self._mlx_tokenizer,
            prompt=formatted_prompt,
            sampler=sampler,
            max_tokens=256,
        )
        latency_ms = (time.perf_counter() - t0) * 1000.0
        self.diagnostics.record_llm_latency(latency_ms)

        extracted = self._extract_candidate_lines(response, max_candidates)
        return [(code, f"llm:call={call_idx}:line={i}") for i, code in enumerate(extracted, 1)]

    def _generate_with_mlx(
        self,
        examples: List[Tuple[Any, Any]],
        library_primitives: Optional[List[str]],
        crystallized_operators: Optional[List[Dict[str, Any]]],
        max_candidates: int,
    ) -> List[str]:
        """Generate candidate programs using MLX."""
        tagged = self._generate_with_mlx_provenance(
            examples, library_primitives, crystallized_operators, max_candidates
        )
        return [code for code, _ in tagged]

    def _heuristic_synthesizer_provenance(
        self,
        examples: List[Tuple[Any, Any]],
        library_primitives: Optional[List[str]] = None,
        crystallized_operators: Optional[List[Dict[str, Any]]] = None,
        max_candidates: int = 10,
    ) -> List[Tuple[str, str]]:
        """Built-in heuristic generator returning (code_str, source_detail) pairs."""
        if not examples:
            return []

        templates: List[Tuple[str, str]] = [
            (code, f"template:#{idx}") for idx, code in _BASE_HEURISTIC_TEMPLATES
        ]

        # Dynamically inject learned crystallized operators into candidate templates
        if crystallized_operators:
            for op in crystallized_operators:
                op_name = op.get("operator_name")
                arity = op.get("arity", 1)
                if arity == 1:
                    templates.insert(0, (f"({op_name} x)", f"template:crystallized:{op_name}"))
                elif arity == 2:
                    for k in (1, 2, 0, -1):
                        templates.insert(0, (f"({op_name} {k} x)", f"template:crystallized:{op_name}"))

        # Inject custom library primitives if supplied
        if library_primitives:
            for prim in library_primitives:
                templates.append((f"({prim} x)", f"template:primitive:{prim}"))

        return templates[: max_candidates * 3]

    def _heuristic_synthesizer(
        self,
        examples: List[Tuple[Any, Any]],
        library_primitives: Optional[List[str]] = None,
        crystallized_operators: Optional[List[Dict[str, Any]]] = None,
        max_candidates: int = 10,
    ) -> List[str]:
        """Built-in heuristic generator for common transformations and learned operators."""
        tagged = self._heuristic_synthesizer_provenance(
            examples, library_primitives, crystallized_operators, max_candidates
        )
        return [code for code, _ in tagged]
