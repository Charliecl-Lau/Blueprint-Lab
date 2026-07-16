import { expect, test } from 'vitest'
import { parseLinearMath } from './linearMath'


test('parses a Word-linear fraction', () => {
  expect(parseLinearMath('DeltaH/(T DeltaS)')).toMatchObject({
    type: 'fraction',
    numerator: { type: 'symbol', name: 'DeltaH' },
    denominator: { type: 'sequence' },
  })
})

test('parses subscripts, superscripts, and combined scripts', () => {
  expect(parseLinearMath('x_a')).toMatchObject({ type: 'subscript' })
  expect(parseLinearMath('x^2')).toMatchObject({ type: 'superscript' })
  expect(parseLinearMath('x_a^2')).toMatchObject({
    type: 'superscript',
    base: {
      type: 'subscript',
      base: { type: 'symbol', name: 'x' },
      subscript: { type: 'symbol', name: 'a' },
    },
    superscript: { type: 'number', value: '2' },
  })
})

test('parses named and Unicode radicals', () => {
  expect(parseLinearMath('sqrt(x_a)')).toMatchObject({
    type: 'radical',
    radicand: { type: 'subscript' },
  })
  expect(parseLinearMath('√x')).toMatchObject({ type: 'radical' })
})

test('preserves unsupported input as editable text', () => {
  expect(parseLinearMath('')).toEqual({ type: 'text', text: '' })
  expect(parseLinearMath('x)')).toEqual({ type: 'text', text: 'x)' })
})
