from eve3.dsl.ast import ApplyNode, ConstNode, VarNode
from eve3.dsl.interpreter import DSLInterpreter, DSLParserError, SExprParser


def test_parser_basic_atoms():
    node = SExprParser.parse("42")
    assert isinstance(node, ConstNode)
    assert node.value == 42

    node = SExprParser.parse("true")
    assert isinstance(node, ConstNode)
    assert node.value is True

    node = SExprParser.parse("x")
    assert isinstance(node, VarNode)
    assert node.name == "x"


def test_parser_list_literal():
    node = SExprParser.parse("[1, 2, 3]")
    assert isinstance(node, ConstNode)
    assert node.value == [1, 2, 3]


def test_parser_application_and_evaluation():
    interp = DSLInterpreter()
    
    # Simple addition
    res = interp.run("(+ 10 5)", input_val=None)
    assert res == 15

    # Reverse list
    res = interp.run("(reverse x)", input_val=[1, 2, 3])
    assert res == [3, 2, 1]

    # Map increment
    res = interp.run("(map (lambda (a) (+ a 1)) x)", input_val=[1, 2, 3])
    assert res == [2, 3, 4]

    # Filter even
    res = interp.run("(filter (lambda (a) (is_even a)) x)", input_val=[1, 2, 3, 4, 5, 6])
    assert res == [2, 4, 6]

    # Fold sum
    res = interp.run("(fold (lambda (acc item) (+ acc item)) 0 x)", input_val=[1, 2, 3, 4])
    assert res == 10

    # Conditional
    res = interp.run("(if (gt (length x) 2) true false)", input_val=[1, 2, 3])
    assert res is True
    res = interp.run("(if (gt (length x) 2) true false)", input_val=[1])
    assert res is False


def test_parser_syntax_errors():
    failed = False
    try:
        SExprParser.parse("(+ 1 2")  # Missing closing paren
    except DSLParserError:
        failed = True
    assert failed

    failed = False
    try:
        SExprParser.parse("")
    except DSLParserError:
        failed = True
    assert failed

