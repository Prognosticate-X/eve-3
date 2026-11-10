"""Abstract Syntax Tree (AST) definitions for EVE-3 functional DSL."""

from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, List, Optional


class ExecutionStepLimitExceeded(RuntimeError):
    """Raised when DSL execution exceeds instruction step budget."""
    pass


class ExecutionSizeLimitExceeded(RuntimeError):
    """Raised when DSL execution produces output exceeding size or bit-length budget."""
    pass


class ExecutionRecursionLimitExceeded(RuntimeError):
    """Raised when DSL execution exceeds maximum recursion depth budget."""
    pass


class ExecutionContext:
    """Tracks execution budget and resource consumption."""

    def __init__(
        self,
        step_budget: int = 20000,
        max_output_size: int = 1000,
        max_integer_bits: int = 2048,
        max_recursion_depth: int = 50,
    ):
        self.step_budget = step_budget
        self.max_output_size = max_output_size
        self.max_integer_bits = max_integer_bits
        self.max_recursion_depth = max_recursion_depth
        self.steps_executed = 0
        self.current_recursion_depth = 0

    def tick(self) -> None:
        self.steps_executed += 1
        if self.steps_executed > self.step_budget:
            raise ExecutionStepLimitExceeded(
                f"DSL execution step budget exceeded ({self.step_budget} steps)"
            )

    def enter_call(self) -> None:
        self.current_recursion_depth += 1
        if self.current_recursion_depth > self.max_recursion_depth:
            raise ExecutionRecursionLimitExceeded(
                f"DSL execution exceeded recursion limit ({self.max_recursion_depth})"
            )

    def exit_call(self) -> None:
        if self.current_recursion_depth > 0:
            self.current_recursion_depth -= 1

    def check_val(self, val: Any) -> Any:
        if isinstance(val, (list, tuple)):
            if len(val) > self.max_output_size:
                raise ExecutionSizeLimitExceeded(
                    f"DSL output collection size ({len(val)}) exceeded limit ({self.max_output_size})"
                )
        elif isinstance(val, str):
            if len(val) > self.max_output_size:
                raise ExecutionSizeLimitExceeded(
                    f"DSL string length ({len(val)}) exceeded limit ({self.max_output_size})"
                )
        elif isinstance(val, int) and not isinstance(val, bool):
            if val.bit_length() > self.max_integer_bits:
                raise ExecutionSizeLimitExceeded(
                    f"DSL integer bit length ({val.bit_length()}) exceeded limit ({self.max_integer_bits})"
                )
        return val


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

    @abstractmethod
    def to_canonical_sexpr(self, env_map: Optional[Dict[str, str]] = None) -> str:
        """Convert AST node to alpha-normalized canonical S-expression string."""
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
            context.check_val(self.value)
        return self.value

    def to_sexpr(self) -> str:
        if isinstance(self.value, bool):
            return "true" if self.value else "false"
        if isinstance(self.value, list):
            return f"[{', '.join(str(x) for x in self.value)}]"
        return str(self.value)

    def to_canonical_sexpr(self, env_map: Optional[Dict[str, str]] = None) -> str:
        return self.to_sexpr()

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
        val = env[self.name]
        if context:
            context.check_val(val)
        return val

    def to_sexpr(self) -> str:
        return self.name

    def to_canonical_sexpr(self, env_map: Optional[Dict[str, str]] = None) -> str:
        if env_map and self.name in env_map:
            return env_map[self.name]
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
            if context:
                context.enter_call()
            try:
                new_env = dict(env)
                for name, val in zip(self.arg_names, args):
                    new_env[name] = val
                res = self.body.evaluate(new_env, context)
                if context:
                    context.check_val(res)
                return res
            finally:
                if context:
                    context.exit_call()

        return closure

    def to_sexpr(self) -> str:
        args_str = " ".join(self.arg_names)
        return f"(lambda ({args_str}) {self.body.to_sexpr()})"

    def to_canonical_sexpr(self, env_map: Optional[Dict[str, str]] = None) -> str:
        new_env = dict(env_map) if env_map is not None else {}
        canonical_params: List[str] = []
        for name in self.arg_names:
            var_id = f"${len(new_env)}"
            new_env[name] = var_id
            canonical_params.append(var_id)
        params_str = " ".join(canonical_params)
        body_str = self.body.to_canonical_sexpr(new_env)
        return f"(lambda ({params_str}) {body_str})"

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
            context.enter_call()
        try:
            if self.op_name not in env:
                raise NameError(f"Unknown primitive or function '{self.op_name}' in environment")
            fn = env[self.op_name]
            evaluated_args = [arg.evaluate(env, context) for arg in self.args]
            res = fn(*evaluated_args)
            if context:
                context.check_val(res)
            return res
        finally:
            if context:
                context.exit_call()

    def to_sexpr(self) -> str:
        if not self.args:
            return f"({self.op_name})"
        args_str = " ".join(arg.to_sexpr() for arg in self.args)
        return f"({self.op_name} {args_str})"

    def to_canonical_sexpr(self, env_map: Optional[Dict[str, str]] = None) -> str:
        op = env_map.get(self.op_name, self.op_name) if env_map else self.op_name
        if not self.args:
            return f"({op})"
        args_str = " ".join(arg.to_canonical_sexpr(env_map) for arg in self.args)
        return f"({op} {args_str})"

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

    def to_canonical_sexpr(self, env_map: Optional[Dict[str, str]] = None) -> str:
        cond_str = self.condition.to_canonical_sexpr(env_map)
        then_str = self.then_expr.to_canonical_sexpr(env_map)
        else_str = self.else_expr.to_canonical_sexpr(env_map)
        return f"(if {cond_str} {then_str} {else_str})"

    @property
    def description_length(self) -> int:
        return 1 + self.condition.description_length + self.then_expr.description_length + self.else_expr.description_length

    @property
    def depth(self) -> int:
        return 1 + max(self.condition.depth, self.then_expr.depth, self.else_expr.depth)
