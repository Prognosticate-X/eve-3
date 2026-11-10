"""Built-in primitives for EVE-3 functional DSL."""

from typing import Any, Callable, Dict, List


def get_default_primitives() -> Dict[str, Callable[..., Any]]:
    """Return standard functional primitives dictionary."""
    prims: Dict[str, Callable[..., Any]] = {}

    # Arithmetic
    prims["+"] = lambda a, b: a + b
    prims["-"] = lambda a, b: a - b
    prims["*"] = lambda a, b: a * b
    prims["neg"] = lambda a: -a
    prims["inc"] = lambda a: a + 1
    prims["dec"] = lambda a: a - 1
    prims["mod"] = lambda a, b: a % b if b != 0 else 0

    # Logic & Comparison
    prims["eq"] = lambda a, b: a == b
    prims["gt"] = lambda a, b: a > b
    prims["lt"] = lambda a, b: a < b
    prims["gte"] = lambda a, b: a >= b
    prims["lte"] = lambda a, b: a <= b
    prims[">"] = prims["gt"]
    prims["<"] = prims["lt"]
    prims[">="] = prims["gte"]
    prims["<="] = prims["lte"]
    prims["=="] = prims["eq"]
    prims["not"] = lambda a: not a
    prims["and"] = lambda a, b: bool(a and b)
    prims["or"] = lambda a, b: bool(a or b)
    prims["is_even"] = lambda a: (a % 2) == 0
    prims["is_odd"] = lambda a: (a % 2) != 0

    # List operations
    prims["head"] = lambda lst: lst[0] if lst else None
    prims["tail"] = lambda lst: lst[1:] if lst else []
    prims["cons"] = lambda item, lst: [item] + list(lst)
    prims["append"] = lambda lst, item: list(lst) + [item]
    prims["concat"] = lambda l1, l2: list(l1) + list(l2)
    prims["is_empty"] = lambda lst: len(lst) == 0
    prims["length"] = lambda lst: len(lst)
    prims["reverse"] = lambda lst: list(reversed(lst))
    prims["sum"] = lambda lst: sum(lst)

    # Higher-order functions
    def dsl_map(fn: Callable[[Any], Any], lst: List[Any]) -> List[Any]:
        return [fn(x) for x in lst]

    def dsl_filter(pred: Callable[[Any], bool], lst: List[Any]) -> List[Any]:
        return [x for x in lst if pred(x)]

    def dsl_fold(fn: Callable[[Any, Any], Any], acc: Any, lst: List[Any]) -> Any:
        res = acc
        for x in lst:
            res = fn(res, x)
        return res

    prims["map"] = dsl_map
    prims["filter"] = dsl_filter
    prims["fold"] = dsl_fold

    # Standard crystallized operators
    prims.update(_DEFAULT_CRYSTALLIZED_PRIMITIVES)

    return prims


_DEFAULT_CRYSTALLIZED_PRIMITIVES: Dict[str, Callable[..., Any]] = {
    "op_increment_list": lambda lst: [x + 1 for x in lst] if isinstance(lst, list) else lst,
    "map_add": lambda k, lst: [x + k for x in lst] if isinstance(lst, list) else lst,
    "filter_gt": lambda k, lst: [x for x in lst if x > k] if isinstance(lst, list) else lst,
    "map_mul": lambda k, lst: [x * k for x in lst] if isinstance(lst, list) else lst,
}


def compile_operator(body_sexpr_or_ast: Any, arity: int = 1) -> Callable[..., Any]:
    """Compile an S-expression string or ASTNode into an executable callable primitive."""
    from eve3.dsl.ast import ASTNode
    from eve3.dsl.interpreter import SExprParser

    if isinstance(body_sexpr_or_ast, str):
        ast = SExprParser.parse(body_sexpr_or_ast)
    elif isinstance(body_sexpr_or_ast, ASTNode):
        ast = body_sexpr_or_ast
    else:
        raise TypeError(f"Expected str or ASTNode for operator compilation, got {type(body_sexpr_or_ast)}")

    def _compiled_op(*args: Any) -> Any:
        call_env = get_default_primitives()
        if arity == 1:
            if args:
                call_env["x"] = args[0]
                call_env["input"] = args[0]
        elif arity == 2:
            if len(args) >= 2:
                call_env["$k"] = args[0]
                call_env["k"] = args[0]
                call_env["x"] = args[1]
                call_env["input"] = args[1]
            elif len(args) == 1:
                call_env["x"] = args[0]
                call_env["input"] = args[0]
        else:
            if args:
                for idx, a in enumerate(args[:-1]):
                    call_env[f"$k{idx+1}"] = a
                    call_env[f"k{idx+1}"] = a
                call_env["$k"] = args[0]
                call_env["k"] = args[0]
                call_env["x"] = args[-1]
                call_env["input"] = args[-1]
        return ast.evaluate(call_env)

    return _compiled_op
