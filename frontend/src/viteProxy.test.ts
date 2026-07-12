import { expect, test } from 'vitest'
import type { UserConfig } from 'vite'
import viteConfig from '../vite.config'

test('removes the local api prefix before proxying to FastAPI', () => {
  const proxy = (viteConfig as UserConfig).server?.proxy?.['/api']

  expect(typeof proxy).toBe('object')
  expect(typeof proxy === 'object' && proxy.rewrite?.('/api/experiments')).toBe('/experiments')
})
