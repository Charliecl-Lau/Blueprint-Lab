import type { MathNode } from '../types'


const TOKEN_PATTERN = /sqrt|[A-Za-z]+|[0-9]+(?:\.[0-9]+)?|[^\s]/gi
const PRODUCT_OPERATORS = ['*', '·', '×']
const PRODUCT_BOUNDARIES = ['+', '-', '=', '/', ')', '}']

function sequence(items: MathNode[]): MathNode {
  return items.length === 1 ? items[0] : { type: 'sequence', items }
}

class Parser {
  private position = 0
  private readonly tokens: string[]

  constructor(tokens: string[]) {
    this.tokens = tokens
  }

  parse(): MathNode {
    if (this.tokens.length === 0) throw new Error('empty expression')
    const node = this.equation()
    if (this.peek() !== undefined) throw new Error(`unexpected token: ${this.peek()}`)
    return node
  }

  private peek(): string | undefined {
    return this.tokens[this.position]
  }

  private take(): string {
    const token = this.peek()
    if (token === undefined) throw new Error('unexpected end of expression')
    this.position += 1
    return token
  }

  private equation(): MathNode {
    const items = [this.sum()]
    while (this.peek() === '=') {
      this.take()
      items.push({ type: 'operator', value: '=' }, this.sum())
    }
    return sequence(items)
  }

  private sum(): MathNode {
    const items = [this.fraction()]
    while (this.peek() === '+' || this.peek() === '-') {
      items.push({ type: 'operator', value: this.take() }, this.fraction())
    }
    return sequence(items)
  }

  private fraction(): MathNode {
    let node = this.product()
    while (this.peek() === '/') {
      this.take()
      node = { type: 'fraction', numerator: node, denominator: this.product() }
    }
    return node
  }

  private product(): MathNode {
    const items = [this.script()]
    while (this.peek() !== undefined && !PRODUCT_BOUNDARIES.includes(this.peek()!)) {
      if (PRODUCT_OPERATORS.includes(this.peek()!)) {
        items.push({ type: 'operator', value: this.take() })
      }
      items.push(this.script())
    }
    return sequence(items)
  }

  private script(): MathNode {
    let node = this.atom()
    while (this.peek() === '_' || this.peek() === '^') {
      const operator = this.take()
      const value = this.atom()
      node = operator === '_'
        ? { type: 'subscript', base: node, subscript: value }
        : { type: 'superscript', base: node, superscript: value }
    }
    return node
  }

  private atom(): MathNode {
    const token = this.take()
    if (token === '(' || token === '{') {
      const closing = token === '(' ? ')' : '}'
      const node = this.equation()
      if (this.take() !== closing) throw new Error(`missing ${closing}`)
      return node
    }
    if (token.toLowerCase() === 'sqrt' || token === '√') {
      return { type: 'radical', radicand: this.atom() }
    }
    if ([')', '}', '_', '^', '/'].includes(token)) {
      throw new Error(`unexpected token: ${token}`)
    }
    if (/^[0-9]+(?:\.[0-9]+)?$/.test(token)) {
      return { type: 'number', value: token }
    }
    if (['+', '-', '*', '·', '×', '=', ','].includes(token)) {
      return { type: 'operator', value: token }
    }
    return { type: 'symbol', name: token }
  }
}

export function parseLinearMath(expression: string): MathNode {
  try {
    return new Parser(expression.match(TOKEN_PATTERN) ?? []).parse()
  } catch {
    return { type: 'text', text: expression }
  }
}
