import type { Key, ReactNode } from 'react'


type MathMLProps = { children?: ReactNode; key?: Key }

declare module 'react' {
  namespace JSX {
    interface IntrinsicElements {
      math: MathMLProps & { xmlns?: string }
      mfrac: MathMLProps
      mi: MathMLProps
      mn: MathMLProps
      mo: MathMLProps
      mroot: MathMLProps
      mrow: MathMLProps
      msqrt: MathMLProps
      msub: MathMLProps
      msubsup: MathMLProps
      msup: MathMLProps
      mtable: MathMLProps
      mtd: MathMLProps
      mtext: MathMLProps
      mtr: MathMLProps
    }
  }
}
