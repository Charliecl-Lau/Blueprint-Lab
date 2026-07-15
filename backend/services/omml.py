from typing import Iterable

from docx.oxml import OxmlElement


_GREEK_NAMES = {
    "Alpha": "Α",
    "Beta": "Β",
    "Gamma": "Γ",
    "Delta": "Δ",
    "Theta": "Θ",
    "Lambda": "Λ",
    "Mu": "Μ",
    "Pi": "Π",
    "Sigma": "Σ",
    "Phi": "Φ",
    "Psi": "Ψ",
    "Omega": "Ω",
    "alpha": "α",
    "beta": "β",
    "gamma": "γ",
    "delta": "δ",
    "epsilon": "ε",
    "theta": "θ",
    "lambda": "λ",
    "mu": "μ",
    "nu": "ν",
    "pi": "π",
    "rho": "ρ",
    "sigma": "σ",
    "tau": "τ",
    "phi": "φ",
    "chi": "χ",
    "psi": "ψ",
    "omega": "ω",
}


def _as_dict(node):
    return node.model_dump(exclude_none=True) if hasattr(node, "model_dump") else node


def _math_run(value: str):
    run = OxmlElement("m:r")
    text = OxmlElement("m:t")
    text.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
    text.text = value
    run.append(text)
    return run


def _symbol_text(name: str) -> str:
    if name in _GREEK_NAMES:
        return _GREEK_NAMES[name]
    for word in sorted(_GREEK_NAMES, key=len, reverse=True):
        if name.startswith(word) and len(name) > len(word):
            return f"{_GREEK_NAMES[word]}{name[len(word):]}"
    return name


def _container(tag: str, children: Iterable):
    element = OxmlElement(tag)
    for child in children:
        element.append(child)
    return element


def _serialize(node) -> list:
    node = _as_dict(node)
    kind = node["type"]
    if kind == "text":
        return [_math_run(node["text"])]
    if kind == "symbol":
        return [_math_run(_symbol_text(node["name"]))]
    if kind == "number":
        return [_math_run(node["value"])]
    if kind == "operator":
        return [_math_run(node["value"])]
    if kind == "differential":
        return [_math_run(f"d{_symbol_text(node['variable'])}")]
    if kind == "sequence":
        return [child for item in node["items"] for child in _serialize(item)]
    if kind == "equation":
        return _serialize(node["left"]) + [_math_run("=")] + _serialize(node["right"])
    if kind == "product":
        operator = {"implicit": "", "dot": "·", "cross": "×"}.get(
            node.get("operator", "implicit"), ""
        )
        result = []
        for index, term in enumerate(node["terms"]):
            if index and operator:
                result.append(_math_run(operator))
            result.extend(_serialize(term))
        return result
    if kind == "fraction":
        fraction = OxmlElement("m:f")
        fraction.append(_container("m:num", _serialize(node["numerator"])))
        fraction.append(_container("m:den", _serialize(node["denominator"])))
        return [fraction]
    if kind in ("subscript", "superscript"):
        element = OxmlElement("m:sSub" if kind == "subscript" else "m:sSup")
        element.append(_container("m:e", _serialize(node["base"])))
        script_key = "subscript" if kind == "subscript" else "superscript"
        script_tag = "m:sub" if kind == "subscript" else "m:sup"
        element.append(_container(script_tag, _serialize(node[script_key])))
        return [element]
    if kind == "radical":
        radical = OxmlElement("m:rad")
        degree = node.get("degree")
        properties = OxmlElement("m:radPr")
        if degree is None:
            degree_hidden = OxmlElement("m:degHide")
            degree_hidden.set("{http://schemas.openxmlformats.org/officeDocument/2006/math}val", "1")
            properties.append(degree_hidden)
        radical.append(properties)
        radical.append(_container("m:deg", _serialize(degree) if degree else []))
        radical.append(_container("m:e", _serialize(node["radicand"])))
        return [radical]
    if kind == "matrix":
        matrix = OxmlElement("m:m")
        for row in node["rows"]:
            matrix_row = OxmlElement("m:mr")
            for cell in row:
                matrix_row.append(_container("m:e", _serialize(cell)))
            matrix.append(matrix_row)
        return [matrix]
    raise ValueError(f"Unsupported structured math node: {kind}")


def append_math(paragraph, node) -> None:
    math = OxmlElement("m:oMath")
    for child in _serialize(node):
        math.append(child)
    paragraph._p.append(math)


def append_content(paragraph, segments, fallback: str) -> None:
    if not segments:
        paragraph.add_run(fallback)
        return
    for segment in segments:
        segment = _as_dict(segment)
        if segment["type"] == "text":
            paragraph.add_run(segment["text"])
        else:
            append_math(paragraph, segment["math"])
