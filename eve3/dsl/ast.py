"""Abstract Syntax Tree (AST) definitions for EVE-3 functional DSL."""

from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, List, Optional


class ExecutionStepLimitExceeded(RuntimeError):
    """Raised when DSL execution exceeds instruction step budget."""
    pass


class ExecutionContext:
    """Tracks execution budget and resource consumption."""

    def __init__(self, step_budget: int = 20000):
        self.step_budget = step_budget
        self.steps_executed = 0

    def tick(self):
        self.steps_executed += 1
        if self.steps_executed > self.step_budget:
            raise ExecutionStepLimitExceeded(
                f"DSL execution step budget exceeded ({self.step_budget} steps)"
            )


class ASTNode(ABC):
    """Base class for all DSL AST nodes."""

    @abstractmethod
    def evaluate(self, env: Dict[str, Any], context: Optional[ExecutionContext] = None) -> Any:
        """Evaluate node within the provided lexical environment."""
        pass

    @abstractmethod
    def to_sexpr(self) -> str:
        """Convert AST node to canonical S-expression string."""
        pass

    @property
    @abstractmethod
    def description_length(self) -> int:
        """MDL (Minimum Description Length) size metric (node count)."""
        pass

    @property
    @abstractmethod
    def depth(self) -> int:
        """Maximum depth of AST tree."""
        pass

    def __str__(self) -> str:
        return self.to_sexpr()

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}: {self.to_sexpr()}>"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, ASTNode):
            return False
        return self.to_sexpr() == other.to_sexpr()

    def __hash__(self) -> int:
        return hash(self.to_sexpr())


class ConstNode(ASTNode):
    """Constant literal (int, bool, list, str)."""

    def __init__(self, value: Any):
        self.value = value

    def evaluate(self, env: Dict[str, Any], context: Optional[ExecutionContext] = None) -> Any:
        if context:
            context.tick()
        return self.value

    def to_sexpr(self) -> str:
        if isinstance(self.value, bool):
            return "true" if self.value else "false"
        if isinstance(self.value, list):
            return f"[{', '.join(str(x) for x in self.value)}]"
        return str(self.value)

    @property
    def description_length(self) -> int:
        return 1

    @property
    def depth(self) -> int:
        return 1


class VarNode(ASTNode):
    """Variable reference."""

    def __init__(self, name: str):
        self.name = name

    def evaluate(self, env: Dict[str, Any], context: Optional[ExecutionContext] = None) -> Any:
        if context:
            context.tick()
        if self.name not in env:
            raise NameError(f"Undefined variable in DSL environment: '{self.name}'")
        return env[self.name]

    def to_sexpr(self) -> str:
        return self.name

    @property
    def description_length(self) -> int:
        return 1

    @property
    def depth(self) -> int:
        return 1


class LambdaNode(ASTNode):
    """Anonymous function expression: (lambda (arg1 arg2 ...) body)."""

    def __init__(self, arg_names: List[str], body: ASTNode):
        self.arg_names = arg_names
        self.body = body

    def evaluate(self, env: Dict[str, Any], context: Optional[ExecutionContext] = None) -> Callable[..., Any]:
        if context:
            context.tick()

        def closure(*args: Any) -> Any:
            new_env = dict(env)
            for name, val in zip(self.arg_names, args):
                new_env[name] = val
            return self.body.evaluate(new_env, context)

        return closure

    def to_sexpr(self) -> str:
        args_str = " ".join(self.arg_names)
        return f"(lambda ({args_str}) {self.body.to_sexpr()})"

    @property
    def description_length(self) -> int:
        return 1 + len(self.arg_names) + self.body.description_length

    @property
    def depth(self) -> int:
        return 1 + self.body.depth


class ApplyNode(ASTNode):
    """Function application: (op arg1 arg2 ...)."""

    def __init__(self, op_name: str, args: List[ASTNode]):
        self.op_name = op_name
        self.args = args

    def evaluate(self, env: Dict[str, Any], context: Optional[ExecutionContext] = None) -> Any:
        if context:
            context.tick()
        if self.op_name not in env:
            raise NameError(f"Unknown primitive or function '{self.op_name}' in environment")
        fn = env[self.op_name]
        evaluated_args = [arg.evaluate(env, context) for arg in self.args]
        return fn(*evaluated_args)

    def to_sexpr(self) -> str:
        if not self.args:
            return f"({self.op_name})"
        args_str = " ".join(arg.to_sexpr() for arg in self.args)
        return f"({self.op_name} {args_str})"

    @property
    def description_length(self) -> int:
        return 1 + sum(arg.description_length for arg in self.args)

    @property
    def depth(self) -> int:
        return 1 + max((arg.depth for arg in self.args), default=0)


class IfElseNode(ASTNode):
    """Conditional branching: (if condition then_expr else_expr)."""

    def __init__(self, condition: ASTNode, then_expr: ASTNode, else_expr: ASTNode):
        self.condition = condition
        self.then_expr = then_expr
        self.else_expr = else_expr

    def evaluate(self, env: Dict[str, Any], context: Optional[ExecutionContext] = None) -> Any:
        if context:
            context.tick()
        cond_val = self.condition.evaluate(env, context)
        if cond_val:
            return self.then_expr.evaluate(env, context)
        else:
            return self.else_expr.evaluate(env, context)

    def to_sexpr(self) -> str:
        return f"(if {self.condition.to_sexpr()} {self.then_expr.to_sexpr()} {self.else_expr.to_sexpr()})"

    @property
    def description_length(self) -> int:
        return 1 + self.condition.description_length + self.then_expr.description_length + self.else_expr.description_length

    @property
    def depth(self) -> int:
        return 1 + max(self.condition.depth, self.then_expr.depth, self.else_expr.depth)
