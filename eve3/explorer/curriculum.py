"""Curriculum: Autonomous Task Generation, Learnability Filtering, and Multi-Objective Scoring.

Implements Phase 7 Autonomous Discovery (Explorer):
- Generates learning tasks from 3 distinct sources:
  1. Operator combination and parameter mutation over crystallized library primitives.
  2. Sub-goal decomposition of failed / complex discovery tasks.
  3. Grounding anchor sampling from external benchmark families.
- Multi-objective task scoring:
  Score(tau) = alpha * E[IG] + beta * DeltaCompress + delta * LP(family) - eta * Redundancy
- Zone of Proximal Development (ZPD) Learnability Filter:
  Admits only tasks with estimated success probability p_hat in [0.20, 0.80],
  discarding uninformative trivial tasks and hopeless unsolvable tasks.
"""

from dataclasses import dataclass, field
import json
import math
from pathlib import Path
import random
import time
from typing import Any, Callable, Dict, List, Optional, Set, Tuple
import uuid

from eve3.dsl.ast import ASTNode, ApplyNode, ConstNode, LambdaNode, VarNode
from eve3.dsl.interpreter import DSLInterpreter, SExprParser
from eve3.models import Task, LearnedAbstraction
from eve3.system3_crystallizer.library import KnowledgeLibrary


@dataclass
class CurriculumConfig:
    """Hyperparameters and weights for curriculum generation and scoring."""
    alpha_ig: float = 0.35             # Weight for Expected Information Gain
    beta_compress: float = 0.30        # Weight for MDL Compression Gain
    delta_lp: float = 0.20             # Weight for Family Learning Progress
    eta_redundancy: float = 0.15       # Penalty weight for Redundancy
    learnability_min: float = 0.20     # Minimum difficulty threshold (too hard if below)
    learnability_max: float = 0.80     # Maximum difficulty threshold (too easy if above)
    max_synthetic_ratio: float = 0.60  # Guardrail: synthetic tasks <= 60%
    default_anchor_ratio: float = 0.40 # Anchor proportion (>= 40%)
    history_window_size: int = 20      # Window size for learning progress tracking


class Curriculum:
    """Generates, scores, filters, and manages self-directed curriculum tasks."""

    def __init__(
        self,
        config: Optional[CurriculumConfig] = None,
        benchmarks_dir: Optional[Path] = None,
        seed: Optional[int] = None,
    ):
        self.config = config or CurriculumConfig()
        if benchmarks_dir is not None:
            self.benchmarks_dir = Path(benchmarks_dir)
        else:
            self.benchmarks_dir = Path(__file__).parent.parent.parent / "benchmarks"
        
        self.rng = random.Random(seed if seed is not None else 42)
        self.interpreter = DSLInterpreter()
        
        # Tracking history for learning progress and redundancy
        self.family_outcomes: Dict[str, List[bool]] = {}
        self.recent_task_signatures: List[str] = []
        self.task_history: List[Task] = []

    def propose_tasks(
        self,
        lib: Optional[KnowledgeLibrary] = None,
        n: int = 5,
        failed_tasks: Optional[List[Task]] = None,
    ) -> List[Task]:
        """Propose n diverse, learnable tasks respecting the synthetic ratio guardrail."""
        if n <= 0:
            return []

        # Enforce anti-collapse guardrail: synthetic ratio <= max_synthetic_ratio (e.g. 60%)
        max_synth = int(math.floor(n * self.config.max_synthetic_ratio))
        target_anchors = max(1, n - max_synth)
        target_synth = n - target_anchors

        proposed: List[Task] = []

        # 1. Generate anchor tasks from external benchmarks
        anchors = self.propose_from_anchors(target_anchors)
        proposed.extend(anchors)

        # 2. Decompose failed tasks if available
        synth_generated: List[Task] = []
        if failed_tasks and target_synth > 0:
            decomposed = self.propose_from_decomposition(failed_tasks, max_tasks=target_synth // 2 + 1)
            synth_generated.extend(decomposed)

        # 3. Generate from operator combination & mutation
        remaining_synth = target_synth - len(synth_generated)
        if remaining_synth > 0:
            mutated = self.propose_from_operators(lib, n=remaining_synth + 2)
            synth_generated.extend(mutated)

        # Filter synthetic tasks through the Learnability Filter
        for task in synth_generated:
            if len(proposed) >= n:
                break
            if self.learnable(task):
                proposed.append(task)

        # If filtered synth fell short of n, fill remainder with diverse anchors
        if len(proposed) < n:
            more_anchors = self.propose_from_anchors(n - len(proposed))
            proposed.extend(more_anchors)

        # Score and rank all proposed tasks
        for task in proposed:
            task.metadata["curriculum_score"] = self.score(task)

        proposed.sort(key=lambda t: t.metadata.get("curriculum_score", 0.0), reverse=True)
        return proposed[:n]

    def propose_from_operators(
        self,
        lib: Optional[KnowledgeLibrary],
        n: int = 3,
    ) -> List[Task]:
        """Generate tasks by composing and mutating crystallized abstractions or DSL operators."""
        tasks: List[Task] = []
        attempts = 0
        max_attempts = n * 10

        # Base templates for functional composition
        templates = [
            # Map-Increment/Multiply
            ("(map (lambda (a) (+ a {k})) x)", "list_mapping", "Increment each element by {k}"),
            ("(map (lambda (a) (* a {k})) x)", "list_mapping", "Multiply each element by {k}"),
            ("(map (lambda (a) (- a {k})) x)", "list_mapping", "Subtract {k} from each element"),
            # Filter-Predicate
            ("(filter (lambda (a) (> a {k})) x)", "list_filtering", "Keep elements strictly greater than {k}"),
            ("(filter (lambda (a) (< a {k})) x)", "list_filtering", "Keep elements strictly less than {k}"),
            ("(filter (lambda (a) (is_even a)) x)", "list_filtering", "Keep only even integers"),
            ("(filter (lambda (a) (is_odd a)) x)", "list_filtering", "Keep only odd integers"),
            # Reduction
            ("(sum x)", "list_reduction", "Calculate sum of all elements"),
            ("(sum (map (lambda (a) (+ a {k})) x))", "list_reduction", "Sum of elements after incrementing each by {k}"),
            # Structural
            ("(reverse x)", "list_structural", "Reverse list elements"),
            ("(reverse (map (lambda (a) (+ a {k})) x))", "list_structural", "Reverse list after incrementing each by {k}"),
            # Composition
            ("(map (lambda (a) (+ a {k})) (filter (lambda (a) (> a {m})) x))", "list_composition", "Filter elements > {m} then increment by {k}"),
            ("(filter (lambda (a) (> a {m})) (map (lambda (a) (+ a {k})) x))", "list_composition", "Increment elements by {k} then keep those > {m}"),
            ("(sum (filter (lambda (a) (> a {m})) x))", "list_composition", "Sum of elements that are strictly greater than {m}"),
            ("(sum (filter (lambda (a) (is_even a)) x))", "list_composition", "Sum of all even elements"),
        ]

        # Candidate parameter values for mutation
        k_values = [1, 2, 3, 4, 5, -1, -2]
        m_values = [0, 1, 2, 3, -1]

        # Candidate test inputs for execution
        sample_inputs = [
            [1, 2, 3, 4],
            [0, -2, 5, 3],
            [10, -5, 20, 0],
            [],
            [2, 4, 6],
            [-3, -1, -7],
            [5, 10, 15],
            [1, 3, 5, 7],
            [8, -4, 0, 12],
        ]

        while len(tasks) < n and attempts < max_attempts:
            attempts += 1
            code_pattern, family, desc_pattern = self.rng.choice(templates)
            k = self.rng.choice(k_values)
            m = self.rng.choice(m_values)

            code_str = code_pattern.replace("{k}", str(k)).replace("{m}", str(m))
            desc = desc_pattern.replace("{k}", str(k)).replace("{m}", str(m))

            try:
                ast = SExprParser.parse(code_str)
            except Exception:
                continue

            # Evaluate ground truth on test inputs using the safe interpreter
            visible_examples: List[Dict[str, Any]] = []
            hidden_tests: List[Dict[str, Any]] = []

            eval_success = True
            for i, inp in enumerate(sample_inputs):
                try:
                    out = self.interpreter.run(ast, inp, timeout_seconds=0.5)
                    test_pair = {"input": list(inp), "output": out}
                    if i < 3:
                        visible_examples.append(test_pair)
                    else:
                        hidden_tests.append(test_pair)
                except Exception:
                    eval_success = False
                    break

            if not eval_success or len(visible_examples) < 2 or len(hidden_tests) < 2:
                continue

            task_id = f"synth_{family}_{uuid.uuid4().hex[:6]}"
            task = Task(
                task_id=task_id,
                task_family=family,
                description=desc,
                visible_examples=visible_examples,
                hidden_tests=hidden_tests,
                reference_program=code_str,
                metadata={
                    "ast_depth": ast.depth,
                    "ast_nodes": ast.description_length,
                    "k": k,
                    "m": m,
                },
                source="mutation",
            )
            tasks.append(task)

        return tasks

    def propose_from_decomposition(
        self,
        complex_tasks: List[Task],
        max_tasks: int = 2,
    ) -> List[Task]:
        """Decompose complex / failed tasks into simpler stepping-stone sub-goals."""
        sub_tasks: List[Task] = []
        for task in complex_tasks:
            if len(sub_tasks) >= max_tasks:
                break
            if not task.reference_program:
                continue

            ref_code = task.reference_program.strip()
            # If composite like (map ... (filter ... x)) or (sum (filter ... x))
            inner_code: Optional[str] = None
            inner_family: str = "list_mapping"
            inner_desc: str = ""

            if "(map" in ref_code and "(filter" in ref_code:
                # Subgoal 1: the inner filter
                start_filter = ref_code.find("(filter")
                if start_filter != -1:
                    inner_code = "(filter (lambda (a) (> a 0)) x)"
                    inner_family = "list_filtering"
                    inner_desc = f"Subgoal decomposition for {task.task_id}: filter condition"
            elif "(sum" in ref_code:
                # Subgoal: simplify to unreduced mapping or filtering
                if "(filter" in ref_code:
                    inner_code = "(filter (lambda (a) (> a 0)) x)"
                    inner_family = "list_filtering"
                    inner_desc = f"Subgoal decomposition for {task.task_id}: isolate filter before sum"
                elif "(map" in ref_code:
                    inner_code = "(map (lambda (a) (+ a 1)) x)"
                    inner_family = "list_mapping"
                    inner_desc = f"Subgoal decomposition for {task.task_id}: isolate map before sum"

            if not inner_code:
                continue

            try:
                sub_ast = SExprParser.parse(inner_code)
                vis: List[Dict[str, Any]] = []
                for ex in task.visible_examples:
                    out = self.interpreter.run(sub_ast, ex["input"], timeout_seconds=0.5)
                    vis.append({"input": list(ex["input"]), "output": out})

                hid: List[Dict[str, Any]] = []
                for ex in task.hidden_tests:
                    out = self.interpreter.run(sub_ast, ex["input"], timeout_seconds=0.5)
                    hid.append({"input": list(ex["input"]), "output": out})

                sub_task = Task(
                    task_id=f"subgoal_{task.task_id}_{uuid.uuid4().hex[:4]}",
                    task_family=inner_family,
                    description=inner_desc,
                    visible_examples=vis,
                    hidden_tests=hid,
                    reference_program=inner_code,
                    metadata={"parent_task_id": task.task_id, "decomposition_type": "subgoal"},
                    source="decomposition",
                )
                sub_tasks.append(sub_task)
            except Exception:
                continue

        return sub_tasks

    def propose_from_anchors(self, n: int = 2) -> List[Task]:
        """Sample grounding anchor tasks from external benchmarks/families/."""
        anchors: List[Task] = []
        families_dir = self.benchmarks_dir / "families"
        if not families_dir.exists():
            return []

        # Load available benchmark family files
        json_files = list(families_dir.glob("*.json"))
        # Exclude manifest and strictly held-out families from training anchor pool
        valid_files = [
            f for f in json_files 
            if f.name != "manifest.json" and f.name != "list_composition.json"
        ]

        if not valid_files:
            return []

        sampled_files = self.rng.choices(valid_files, k=max(n * 2, 4))
        for jf in sampled_files:
            if len(anchors) >= n:
                break
            try:
                with open(jf, "r", encoding="utf-8") as f:
                    data = json.load(f)
                raw_tasks = data.get("tasks", [])
                if raw_tasks:
                    raw_task = self.rng.choice(raw_tasks)
                    # Create Task object
                    task = Task.from_dict(raw_task)
                    task.source = "anchor"
                    anchors.append(task)
            except Exception:
                continue

        return anchors[:n]

    def score(self, task: Task) -> float:
        """Compute multi-objective curriculum utility score for a task.
        
        Score(tau) = alpha * E[IG] + beta * DeltaCompress + delta * LP(family) - eta * Redundancy
        """
        # 1. Expected Information Gain E[IG]
        # Higher when visible examples contain both positive, negative, and edge inputs
        ig = self._compute_expected_information_gain(task)

        # 2. MDL Compression Benefit DeltaCompress
        # Higher if the program has structure that can be factored into reusable abstractions
        delta_compress = self._compute_compression_gain(task)

        # 3. Learning Progress LP(family)
        # Higher if this task family is currently in a state of rapid improvement (steep curve)
        lp = self.get_learning_progress(task.task_family)

        # 4. Redundancy penalty
        # Higher if this task is very similar to recently encountered tasks
        redundancy = self._compute_redundancy(task)

        score = (
            self.config.alpha_ig * ig
            + self.config.beta_compress * delta_compress
            + self.config.delta_lp * lp
            - self.config.eta_redundancy * redundancy
        )

        return float(max(0.0, min(1.0, score)))

    def learnable(self, task: Task, lo: Optional[float] = None, hi: Optional[float] = None) -> bool:
        """Zone of Proximal Development filter: checks if 0.20 <= p_hat <= 0.80."""
        lo_thresh = lo if lo is not None else self.config.learnability_min
        hi_thresh = hi if hi is not None else self.config.learnability_max

        p_hat = self.estimate_difficulty(task)
        task.difficulty_estimate = p_hat

        return lo_thresh <= p_hat <= hi_thresh

    def estimate_difficulty(self, task: Task) -> float:
        """Estimate candidate success probability p_hat in [0.0, 1.0]."""
        # Base historical proficiency in this family
        fam_history = self.family_outcomes.get(task.task_family, [])
        if fam_history:
            recent = fam_history[-self.config.history_window_size:]
            base_acc = sum(recent) / len(recent)
        else:
            base_acc = 0.5  # Prior default

        # Structural complexity from AST
        depth = task.metadata.get("ast_depth", 2)
        nodes = task.metadata.get("ast_nodes", 4)
        if task.reference_program:
            try:
                ast = SExprParser.parse(task.reference_program)
                depth = ast.depth
                nodes = ast.description_length
            except Exception:
                pass

        # Complexity penalty / bonus
        # Depth 1 is a trivial operation; depth >= 4 is complex; nodes >= 8 is complex
        complexity_cost = 0.35 * max(0, depth - 2) + 0.15 * max(0, nodes - 4)
        simplicity_bonus = 1.0 if depth <= 1 else 0.0
        
        # Logistic sigmoid estimation
        logits = (base_acc - 0.5) * 3.0 + simplicity_bonus - complexity_cost
        p_hat = 1.0 / (1.0 + math.exp(-logits))

        return float(max(0.01, min(0.99, p_hat)))

    def record_task_outcome(self, task: Task, success: bool):
        """Update historical learning progress and task history."""
        family = task.task_family
        if family not in self.family_outcomes:
            self.family_outcomes[family] = []
        self.family_outcomes[family].append(success)

        # Track task signature for redundancy
        sig = f"{family}:{task.description}:{len(task.visible_examples)}"
        self.recent_task_signatures.append(sig)
        if len(self.recent_task_signatures) > self.config.history_window_size * 2:
            self.recent_task_signatures.pop(0)

        self.task_history.append(task)

    def get_learning_progress(self, family: str) -> float:
        """Compute Learning Progress LP = |acc_recent - acc_prior| for task family."""
        history = self.family_outcomes.get(family, [])
        if len(history) < 4:
            return 0.5  # Initial moderate progress prior

        mid = len(history) // 2
        prior = history[:mid]
        recent = history[mid:]

        acc_prior = sum(prior) / len(prior)
        acc_recent = sum(recent) / len(recent)

        # Absolute change in accuracy reflects active learning dynamics
        return float(min(1.0, abs(acc_recent - acc_prior) * 2.0))

    def _compute_expected_information_gain(self, task: Task) -> float:
        """Estimate information gain based on input diversity and edge case coverage."""
        all_inputs = [ex.get("input", []) for ex in task.visible_examples + task.hidden_tests]
        if not all_inputs:
            return 0.2

        has_empty = any(len(inp) == 0 for inp in all_inputs)
        has_negative = any(any(x < 0 for x in inp) for inp in all_inputs if isinstance(inp, list))
        has_zeros = any(0 in inp for inp in all_inputs if isinstance(inp, list))
        has_large = any(any(abs(x) >= 10 for x in inp) for inp in all_inputs if isinstance(inp, list))

        diversity_count = sum([has_empty, has_negative, has_zeros, has_large])
        # Higher diversity means higher potential to falsify incorrect hypotheses
        return float(min(1.0, 0.25 + 0.18 * diversity_count))

    def _compute_compression_gain(self, task: Task) -> float:
        """Estimate MDL description length savings if this task's abstraction is crystallized."""
        if not task.reference_program:
            return 0.3
        try:
            ast = SExprParser.parse(task.reference_program)
            # Programs with node count >= 5 yield substantial compression when abstracted
            nodes = ast.description_length
            if nodes >= 6:
                return 0.85
            elif nodes >= 4:
                return 0.60
            else:
                return 0.30
        except Exception:
            return 0.30

    def _compute_redundancy(self, task: Task) -> float:
        """Compute semantic overlap with recent tasks."""
        if not self.recent_task_signatures:
            return 0.0

        current_sig = f"{task.task_family}:{task.description}:{len(task.visible_examples)}"
        matches = sum(1 for s in self.recent_task_signatures if s == current_sig)
        return float(min(1.0, matches / max(1, len(self.recent_task_signatures))))
