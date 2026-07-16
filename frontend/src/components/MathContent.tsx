import { Fragment, type ReactNode } from 'react'
import type { ContentSegment, EquationEntry, MathNode } from '../types'
import { EQUATION_PLACEHOLDER_PATTERN } from '../math/equationReferences'
import { parseLinearMath } from '../math/linearMath'


const GREEK_NAMES: Record<string, string> = {
  Alpha: 'Α', Beta: 'Β', Gamma: 'Γ', Delta: 'Δ', Theta: 'Θ', Lambda: 'Λ',
  Mu: 'Μ', Pi: 'Π', Sigma: 'Σ', Phi: 'Φ', Psi: 'Ψ', Omega: 'Ω',
  alpha: 'α', beta: 'β', gamma: 'γ', delta: 'δ', epsilon: 'ε', theta: 'θ',
  lambda: 'λ', mu: 'μ', nu: 'ν', pi: 'π', rho: 'ρ', sigma: 'σ', tau: 'τ',
  phi: 'φ', chi: 'χ', psi: 'ψ', omega: 'ω',
}

function symbolText(name: string): string {
  if (GREEK_NAMES[name]) return GREEK_NAMES[name]
  const prefix = Object.keys(GREEK_NAMES)
    .sort((left, right) => right.length - left.length)
    .find((candidate) => name.startsWith(candidate) && name.length > candidate.length)
  return prefix ? `${GREEK_NAMES[prefix]}${name.slice(prefix.length)}` : name
}

function renderMathNode(node: MathNode, fallback: string): ReactNode {
  switch (node.type) {
    case 'text':
      return <mtext>{node.text}</mtext>
    case 'symbol':
      return <mi>{symbolText(node.name)}</mi>
    case 'number':
      return <mn>{node.value}</mn>
    case 'operator':
      return <mo>{node.value}</mo>
    case 'sequence':
      return <mrow>{node.items.map((item, index) => <Fragment key={index}>{renderMathNode(item, fallback)}</Fragment>)}</mrow>
    case 'equation':
      return <mrow>{renderMathNode(node.left, fallback)}<mo>=</mo>{renderMathNode(node.right, fallback)}</mrow>
    case 'fraction':
      return <mfrac>{renderMathNode(node.numerator, fallback)}{renderMathNode(node.denominator, fallback)}</mfrac>
    case 'differential':
      return <mrow><mi>d</mi><mi>{symbolText(node.variable)}</mi></mrow>
    case 'product':
      return <mrow>{node.terms.map((term, index) => <Fragment key={index}>{index > 0 && node.operator === 'dot' && <mo>·</mo>}{index > 0 && node.operator === 'cross' && <mo>×</mo>}{renderMathNode(term, fallback)}</Fragment>)}</mrow>
    case 'superscript':
      if (node.base.type === 'subscript') {
        return <msubsup>{renderMathNode(node.base.base, fallback)}{renderMathNode(node.base.subscript, fallback)}{renderMathNode(node.superscript, fallback)}</msubsup>
      }
      return <msup>{renderMathNode(node.base, fallback)}{renderMathNode(node.superscript, fallback)}</msup>
    case 'subscript':
      if (node.base.type === 'superscript') {
        return <msubsup>{renderMathNode(node.base.base, fallback)}{renderMathNode(node.subscript, fallback)}{renderMathNode(node.base.superscript, fallback)}</msubsup>
      }
      return <msub>{renderMathNode(node.base, fallback)}{renderMathNode(node.subscript, fallback)}</msub>
    case 'radical':
      return node.degree
        ? <mroot>{renderMathNode(node.radicand, fallback)}{renderMathNode(node.degree, fallback)}</mroot>
        : <msqrt>{renderMathNode(node.radicand, fallback)}</msqrt>
    case 'matrix':
      return <mtable>{node.rows.map((row, rowIndex) => <mtr key={rowIndex}>{row.map((cell, cellIndex) => <mtd key={cellIndex}>{renderMathNode(cell, fallback)}</mtd>)}</mtr>)}</mtable>
    default:
      return <mtext>{fallback || 'Unsupported equation'}</mtext>
  }
}

function MathExpression({ node, fallback }: { node: MathNode; fallback: string }) {
  return <math xmlns="http://www.w3.org/1998/Math/MathML">{renderMathNode(node, fallback)}</math>
}

function equationNode(equation: EquationEntry): MathNode {
  return equation.math ?? parseLinearMath(equation.expression ?? '')
}

function PlaceholderContent({ text, equations }: { text: string; equations: EquationEntry[] }) {
  const equationByLabel = new Map(equations.map((equation) => [equation.label, equation]))
  const content: ReactNode[] = []
  let cursor = 0
  let key = 0
  for (const match of text.matchAll(EQUATION_PLACEHOLDER_PATTERN)) {
    const index = match.index
    if (index > cursor) content.push(<Fragment key={key++}>{text.slice(cursor, index)}</Fragment>)
    const equation = equationByLabel.get(match[1])
    content.push(equation
      ? <MathExpression key={key++} node={equationNode(equation)} fallback={equation.expression ?? equation.label} />
      : <Fragment key={key++}>{match[0]}</Fragment>)
    cursor = index + match[0].length
  }
  if (cursor < text.length) content.push(<Fragment key={key}>{text.slice(cursor)}</Fragment>)
  return <>{content}</>
}

export function MathContent({
  text,
  segments,
  equations = [],
  location,
}: {
  text: string
  segments?: ContentSegment[]
  equations?: EquationEntry[]
  location: 'question' | 'solution'
}) {
  return <span className="math-content" data-equation-location={location}>
    {segments && segments.length > 0
      ? segments.map((segment, index) => segment.type === 'math' && segment.math
        ? <MathExpression key={index} node={segment.math} fallback={segment.text ?? ''} />
        : <Fragment key={index}>{segment.text ?? ''}</Fragment>)
      : <PlaceholderContent text={text} equations={equations} />}
  </span>
}

export function StandaloneEquations({
  equations = [],
  location,
  referencedLabels,
}: {
  equations?: EquationEntry[]
  location: 'question' | 'solution'
  referencedLabels: Set<string>
}) {
  const rendered = new Set<string>()
  const standalone = equations.filter((equation) => {
    if (equation.location !== location || referencedLabels.has(equation.label) || rendered.has(equation.label)) return false
    rendered.add(equation.label)
    return true
  })
  return <>{standalone.map((equation) => <div className="standalone-equation" key={equation.label}>
    <span>{equation.label}:</span>{' '}
    <MathExpression node={equationNode(equation)} fallback={equation.expression ?? equation.label} />
  </div>)}</>
}
