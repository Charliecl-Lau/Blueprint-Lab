import { render, screen } from '@testing-library/react'
import { expect, test } from 'vitest'
import type { ContentSegment, EquationEntry } from '../types'
import {
  MathContent,
  StandaloneEquations,
} from './MathContent'
import { referencedEquationLabels } from '../math/equationReferences'


const equations: EquationEntry[] = [
  { label: 'fraction', expression: 'DeltaH/(T DeltaS)', location: 'question' },
  { label: 'scripts', expression: 'x_a^2', location: 'question' },
  { label: 'root', expression: 'sqrt(x_a)', location: 'solution' },
]

test('renders structured and legacy expressions as semantic MathML', () => {
  const segments: ContentSegment[] = [
    { type: 'math', math: { type: 'fraction', numerator: { type: 'number', value: '1' }, denominator: { type: 'symbol', name: 'x' } } },
  ]
  const { container } = render(<>
    <MathContent text="fallback" segments={segments} equations={[]} location="question" />
    <MathContent text="[[EQ:scripts]] and [[EQ:root]]" equations={equations} location="question" />
  </>)

  expect(container.querySelectorAll('math')).toHaveLength(3)
  expect(container.querySelector('mfrac')).not.toBeNull()
  expect(container.querySelector('msubsup')).not.toBeNull()
  expect(container.querySelector('msqrt')).not.toBeNull()
  expect(screen.queryByText('[[EQ:scripts]]')).not.toBeInTheDocument()
})

test('keeps an unmatched equation placeholder visible', () => {
  render(<MathContent text="Use [[EQ:missing]] here." equations={equations} location="question" />)

  expect(screen.getByText('[[EQ:missing]]', { exact: false })).toBeVisible()
})

test('renders unreferenced equations once for their saved location', () => {
  const referenced = referencedEquationLabels('Use [[EQ:fraction]].', 'No other equation.')
  const { container } = render(
    <StandaloneEquations equations={equations} location="question" referencedLabels={referenced} />,
  )

  expect(screen.queryByText('fraction:')).not.toBeInTheDocument()
  expect(screen.getByText('scripts:')).toBeVisible()
  expect(screen.queryByText('root:')).not.toBeInTheDocument()
  expect(container.querySelectorAll('math')).toHaveLength(1)
})
