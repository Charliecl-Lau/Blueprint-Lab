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
    assert parse_linear_expression("K^-") == {"type": "text", "text": "K^-"}


def test_linear_parser_keeps_signed_values_inside_superscripts():
    for expression, sign, value in (
        ("K^-1", "-", {"type": "number", "value": "1"}),
        ("x^+n", "+", {"type": "symbol", "name": "n"}),
        ("10^−3", "−", {"type": "number", "value": "3"}),
    ):
        parsed = parse_linear_expression(expression)

        assert parsed["type"] == "superscript"
        assert parsed["superscript"] == {
            "type": "sequence",
            "items": [
                {"type": "operator", "value": sign},
                value,
            ],
        }
