# Signed OMML Superscripts Design

## Problem

The Word-linear parser correctly converts unsigned superscripts such as `x^2`,
but it parses an ungrouped signed exponent such as `K^-1` as a superscript that
contains only `-`, followed by a baseline `1`. This produces structurally valid
OMML with incorrect visual semantics. Generated assessment equations commonly
use signed powers for units and scientific notation, so the defect appears only
for that subset of expressions.

## Design

Extend script parsing in `backend/services/omml.py` so the value following `^`
or `_` may be a signed atom. When the next token is an ASCII plus or minus, or a
Unicode minus sign, the parser will combine that sign and the following atom into
one sequence node. Existing grouped scripts, unsigned scripts, and chained
subscript/superscript behavior remain unchanged.

The change belongs in the parser rather than prompt instructions or expression
preprocessing. Handling the syntax at its interpretation boundary repairs saved
and future expressions consistently without relying on model formatting or a
regex rewrite that could alter grouped expressions.

## Error Handling

A sign without a following atom remains malformed input. The existing public
parser behavior will catch that parse error and preserve the original expression
as editable OMML text rather than emitting a partially interpreted equation.

## Tests

Add a focused parser regression test proving that signed numeric and symbolic
exponents are represented wholly inside the superscript node. Add a DOCX-level
regression assertion that the generated `<m:sup>` element contains both the sign
and exponent value, with no part of the exponent emitted after `</m:sSup>`.

Run the focused OMML and DOCX exporter tests, followed by the complete backend
test suite to detect regressions in equation parsing and document generation.
