from backend.services.omml import parse_linear_expression


def test_linear_parser_builds_fraction_scripts_and_radical_nodes():
    fraction = parse_linear_expression("DeltaH/(T DeltaS)")
    assert fraction["type"] == "fraction"
    assert fraction["numerator"] == {"type": "symbol", "name": "DeltaH"}
    assert fraction["denominator"]["type"] == "sequence"

    scripts = parse_linear_expression("x_a^2")
    assert scripts["type"] == "superscript"
    assert scripts["base"]["type"] == "subscript"
    assert scripts["base"]["subscript"] == {"type": "symbol", "name": "a"}
    assert scripts["superscript"] == {"type": "number", "value": "2"}

    radical = parse_linear_expression("sqrt(x_a)")
    assert radical["type"] == "radical"
    assert radical["radicand"]["type"] == "subscript"


def test_linear_parser_falls_back_to_editable_text_for_malformed_input():
    assert parse_linear_expression("x_(") == {"type": "text", "text": "x_("}
