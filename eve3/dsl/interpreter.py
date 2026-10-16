"""Safe S-Expression Parser and Evaluation Runtime for EVE-3 DSL."""

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
import re
import time
from typing import Any, Dict, List, Optional, Tuple, Union

from eve3.dsl.ast import (
    ASTNode,
    ApplyNode,
    ConstNode,
    ExecutionContext,
    ExecutionStepLimitExceeded,
    IfElseNode,
    LambdaNode,
    VarNode,
)
from eve3.dsl.primitives import get_default_primitives


class ExecutionTimeoutError(RuntimeError):
    """Raised when DSL execution exceeds time budget."""
    pass


class DSLDepthExceededError(ValueError):
    """Raised when AST depth exceeds allowed threshold."""
    pass


class DSLParserError(ValueError):
    """Raised when S-expression syntax is invalid."""
    pass


class SExprParser:
    """Tokenizer and parser for Lisp-like S-expressions."""

    @staticmethod
    def tokenize(code: str) -> List[str]:
        # Tokenize parentheses, brackets, commas, string literals, and symbols
        token_pattern = r'\(|\)|\[|\]|,|\"[^\"]*\"|[^\s()\[\],]+'
        tokens = re.findall(token_pattern, code)
        return tokens

    @classmethod
    def parse(cls, code: str, max_depth: Optional[int] = None) -> ASTNode:
        tokens = cls.tokenize(code.strip())
        if not tokens:
            raise DSLParserError("Empty program code")
        ast, remaining = cls._parse_tokens(tokens)
        if remaining:
            raise DSLParserError(f"Unexpected trailing tokens: {remaining}")
        if max_depth is not None and ast.depth > max_depth:
            raise DSLDepthExceededError(
                f"AST depth ({ast.depth}) exceeds maximum allowed depth ({max_depth})"
            )
        return ast

    @classmethod
    def _parse_tokens(cls, tokens: List[str]) -> Tuple[ASTNode, List[str]]:
        if not tokens:
            raise DSLParserError("Unexpected EOF while parsing")
        tok = tokens[0]
        rest = tokens[1:]

        if tok == "(":
            elements: List[ASTNode] = []
            current = rest
            while current and current[0] != ")":
                node, current = cls._parse_tokens(current)
                elements.append(node)
            if not current:
                raise DSLParserError("Missing closing parenthesis ')'")
            closing = current[1:]  # discard ')'

            if not elements:
                raise DSLParserError("Empty application ()")

            # Check special forms
            head = elements[0]
            if isinstance(head, VarNode):
                if head.name == "lambda":
                    # (lambda (x y) body) or (lambda (x) body) or (lambda x body)
                    if len(elements) != 3:
                        raise DSLParserError("lambda requires exactly 2 arguments: (lambda (args...) body)")
                    var_form = elements[1]
                    body = elements[2]
                    if isinstance(var_form, VarNode):
                        arg_names = [var_form.name]
                    elif isinstance(var_form, ApplyNode):
                        arg_names = [var_form.op_name] + [
                            arg.name if isinstance(arg, VarNode) else str(arg)
                            for arg in var_form.args
                        ]
                    else:
                        arg_names = [str(var_form).strip("()")]
                    return LambdaNode(arg_names=arg_names, body=body), closing

                if head.name == "if":
                    # (if cond then else)
                    if len(elements) != 4:
                        raise DSLParserError("if requires 3 arguments: (if cond then else)")
                    return IfElseNode(condition=elements[1], then_expr=elements[2], else_expr=elements[3]), closing

                return ApplyNode(op_name=head.name, args=elements[1:]), closing
            else:
                raise DSLParserError(f"First element in application must be an operator/function, got {head}")

        elif tok == ")":
            raise DSLParserError("Unexpected closing parenthesis ')'")

        elif tok == "[":
            # List literal: [1, 2, 3] or [1 2 3]
            items: List[Any] = []
            current = rest
            while current and current[0] != "]":
                item_tok = current[0]
                if item_tok == ",":
                    current = current[1:]
                    continue
                # parse item as literal
                val = cls._parse_atom_val(item_tok)
                items.append(val)
                current = current[1:]
            if not current:
                raise DSLParserError("Missing closing bracket ']'")
            return ConstNode(items), current[1:]

        else:
            # Atom: number, boolean, variable or string
            return cls._parse_atom_node(tok), rest

    @classmethod
    def _parse_atom_val(cls, token: str) -> Any:
        if token.lower() == "true":
            return True
        if token.lower() == "false":
            return False
        try:
            return int(token)
        except ValueError:
            pass
        try:
            return float(token)
        except ValueError:
            pass
        if token.startswith('"') and token.endswith('"'):
            return token[1:-1]
        return token

    @classmethod
    def _parse_atom_node(cls, token: str) -> ASTNode:
        if token.lower() == "true":
            return ConstNode(True)
        if token.lower() == "false":
            return ConstNode(False)
        try:
            return ConstNode(int(token))
        except ValueError:
            pass
        try:
            return ConstNode(float(token))
        except ValueError:
            pass
        if token.startswith('"') and token.endswith('"'):
            return ConstNode(token[1:-1])
        return VarNode(token)


class DSLInterpreter:
    """Execution engine for AST nodes with step budgeting and timeout protection."""

    def __init__(self, extra_primitives: Optional[Dict[str, Any]] = None):
        self.base_env: Dict[str, Any] = get_default_primitives()
        if extra_primitives:
            self.base_env.update(extra_primitives)

    def run(
        self,
        program: Union[str, ASTNode],
        input_val: Any,
        timeout_seconds: float = 1.0,
        step_budget: int = 20000,
        max_depth: Optional[int] = None,
    ) -> Any:
        """Execute program on an input value with hard step budget and timeout."""
        if isinstance(program, str):
            ast = SExprParser.parse(program, max_depth=max_depth)
        else:
            ast = program
            if max_depth is not None and ast.depth > max_depth:
                raise DSLDepthExceededError(
                    f"AST depth ({ast.depth}) exceeds maximum allowed depth ({max_depth})"
                )

        env = dict(self.base_env)
        env["x"] = input_val
        env["input"] = input_val

        context = ExecutionContext(step_budget=step_budget)

        def _execute_sync():
            return ast.evaluate(env, context)

        # Execute with thread pool to enforce hard wall-clock timeout
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(_execute_sync)
            try:
                return future.result(timeout=timeout_seconds)
            except FuturesTimeoutError:
                raise ExecutionTimeoutError(
                    f"Execution exceeded hard timeout budget of {timeout_seconds}s"
                )
            except RecursionError:
                raise RuntimeError("DSL execution hit max Python recursion depth")
