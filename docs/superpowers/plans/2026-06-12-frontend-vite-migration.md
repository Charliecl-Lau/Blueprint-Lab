# Frontend Vite Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the contents of `C:\Users\yeekw\Documents\Blueprint\frontend` with a production-ready Vite/React/TypeScript application that ports the design tokens and components from `frontend-claude_design` and implements the three product views (Input Panel, Progress, Assessment Viewer) wired to the FastAPI backend.

**Architecture:** Existing Vite/React 19/TypeScript project is cleaned and rebuilt. Design tokens are ported as CSS custom property files. UI components are proper `.tsx` named exports (no CDN, no Babel standalone). Three pages are connected via React Router. Zustand manages run and assessment state. A fetch-based API layer calls the FastAPI backend at `/api/*` (proxied by Vite in dev).

**Tech Stack:** React 19, TypeScript, Vite, Zustand, React Router v6, CSS Custom Properties

---

## File Structure

```
frontend/
├── src/
│   ├── tokens/
│   │   ├── typography.css
│   │   ├── colors.css
│   │   ├── spacing.css
│   │   ├── effects.css
│   │   └── base.css
│   ├── components/ui/
│   │   ├── Button.tsx
│   │   ├── Input.tsx
│   │   ├── Badge.tsx
│   │   ├── Card.tsx
│   │   ├── Select.tsx
│   │   ├── Tabs.tsx
│   │   ├── Switch.tsx
│   │   └── Checkbox.tsx
│   ├── pages/
│   │   ├── InputPanelPage.tsx
│   │   ├── ProgressPage.tsx
│   │   └── AssessmentViewerPage.tsx
│   ├── store/
│   │   └── runStore.ts
│   ├── api/
│   │   ├── client.ts
│   │   ├── runs.ts
│   │   └── assessments.ts
│   ├── hooks/
│   │   └── useSSE.ts
│   ├── types/
│   │   └── index.ts
│   ├── App.tsx
│   ├── main.tsx
│   └── index.css
├── vite.config.ts
└── package.json
```

---

## Task 1: Clean frontend/ and Install Dependencies

**Files:**
- Delete: `src/components/` (entire directory)
- Delete: `src/hooks/`, `src/store/`, `src/api/`, `src/types/` (if exist)
- Clear: `src/App.css`, `src/index.css`
- Modify: `vite.config.ts`

- [ ] **Step 1: Remove old source files**

Run in PowerShell from `C:\Users\yeekw\Documents\Blueprint\frontend`:
```powershell
Remove-Item -Recurse -Force src\components -ErrorAction SilentlyContinue
Remove-Item -Recurse -Force src\hooks -ErrorAction SilentlyContinue
Remove-Item -Recurse -Force src\store -ErrorAction SilentlyContinue
Remove-Item -Recurse -Force src\api -ErrorAction SilentlyContinue
Remove-Item -Recurse -Force src\types -ErrorAction SilentlyContinue
Remove-Item -Force src\App.css -ErrorAction SilentlyContinue
Clear-Content src\index.css
```

Expected: no errors, old dirs gone

- [ ] **Step 2: Install react-router-dom**

```powershell
npm install react-router-dom
```

Expected: `package.json` now lists `react-router-dom`

- [ ] **Step 3: Add Vite proxy config**

Write to `vite.config.ts`:
```typescript
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': 'http://localhost:8000',
    },
  },
})
```

---

## Task 2: Port CSS Design Tokens

**Files:**
- Create: `src/tokens/typography.css`
- Create: `src/tokens/colors.css`
- Create: `src/tokens/spacing.css`
- Create: `src/tokens/effects.css`
- Create: `src/tokens/base.css`
- Modify: `src/index.css`

- [ ] **Step 1: Create src/tokens/ directory and typography.css**

```powershell
New-Item -ItemType Directory -Force src\tokens
```

Write to `src/tokens/typography.css`:
```css
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:ital,opsz,wght@0,9..40,300;0,9..40,400;0,9..40,500;0,9..40,600;0,9..40,700;1,9..40,400&family=DM+Mono:wght@300;400;500&display=swap');

:root {
  --font-sans: 'DM Sans', -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif;
  --font-mono: 'DM Mono', 'SF Mono', ui-monospace, 'Fira Code', monospace;

  --text-xs:   0.6875rem;
  --text-sm:   0.8125rem;
  --text-base: 0.9375rem;
  --text-md:   1rem;
  --text-lg:   1.125rem;
  --text-xl:   1.25rem;
  --text-2xl:  1.5rem;
  --text-3xl:  1.875rem;
  --text-4xl:  2.25rem;
  --text-5xl:  3rem;
  --text-6xl:  3.75rem;
  --text-7xl:  4.5rem;

  --weight-light:    300;
  --weight-regular:  400;
  --weight-medium:   500;
  --weight-semibold: 600;
  --weight-bold:     700;

  --leading-none:    1;
  --leading-tight:   1.2;
  --leading-snug:    1.35;
  --leading-normal:  1.5;
  --leading-relaxed: 1.625;
  --leading-loose:   2;

  --tracking-tight:   -0.03em;
  --tracking-snug:    -0.02em;
  --tracking-normal:  -0.01em;
  --tracking-neutral:  0em;
  --tracking-wide:     0.02em;
  --tracking-wider:    0.06em;
  --tracking-widest:   0.12em;
}
```

- [ ] **Step 2: Create src/tokens/colors.css**

Write to `src/tokens/colors.css`:
```css
:root {
  --color-white: #FFFFFF;
  --color-black: #000000;

  --color-gray-50:  #F5F5F7;
  --color-gray-100: #EBEBED;
  --color-gray-200: #D2D2D7;
  --color-gray-300: #B8B8BE;
  --color-gray-400: #86868B;
  --color-gray-500: #6E6E73;
  --color-gray-600: #515154;
  --color-gray-700: #3D3D40;
  --color-gray-800: #2D2D2F;
  --color-gray-900: #1D1D1F;

  --color-blue-50:  #EBF2FF;
  --color-blue-100: #CEDFFD;
  --color-blue-200: #9DBEFB;
  --color-blue-300: #5E91F5;
  --color-blue-400: #2D6EEA;
  --color-blue-500: #1A56DB;
  --color-blue-600: #1444B0;
  --color-blue-700: #0D3282;
  --color-blue-800: #082356;
  --color-blue-900: #04112B;

  --color-green-50:  #EDFAF2;
  --color-green-100: #C6F0D8;
  --color-green-200: #8CE0B5;
  --color-green-500: #30C559;
  --color-green-600: #1EA347;

  --color-amber-50:  #FFF8EC;
  --color-amber-100: #FFE8B8;
  --color-amber-500: #FF9F0A;
  --color-amber-600: #CC7A00;

  --color-red-50:  #FFF0EE;
  --color-red-100: #FFD1CC;
  --color-red-500: #FF3B30;
  --color-red-600: #CC2018;

  --color-purple-50:  #F3EEFF;
  --color-purple-200: #D4B8F7;
  --color-purple-500: #9B5DE5;

  --color-bg:           var(--color-white);
  --color-bg-secondary: var(--color-gray-50);
  --color-bg-tertiary:  var(--color-gray-100);
  --color-bg-overlay:   rgba(0, 0, 0, 0.04);

  --color-surface:         var(--color-white);
  --color-surface-raised:  var(--color-white);
  --color-surface-sunken:  var(--color-gray-50);
  --color-surface-overlay: rgba(255, 255, 255, 0.92);

  --color-text-primary:   var(--color-gray-900);
  --color-text-secondary: var(--color-gray-500);
  --color-text-tertiary:  var(--color-gray-400);
  --color-text-disabled:  var(--color-gray-300);
  --color-text-inverse:   var(--color-white);
  --color-text-link:      var(--color-blue-500);

  --color-border:        var(--color-gray-200);
  --color-border-subtle: var(--color-gray-100);
  --color-border-strong: var(--color-gray-300);

  --color-accent:         var(--color-blue-500);
  --color-accent-hover:   var(--color-blue-600);
  --color-accent-pressed: var(--color-blue-700);
  --color-accent-subtle:  var(--color-blue-50);
  --color-accent-muted:   var(--color-blue-100);

  --color-success:        var(--color-green-500);
  --color-success-subtle: var(--color-green-50);
  --color-success-muted:  var(--color-green-100);

  --color-warning:        var(--color-amber-500);
  --color-warning-subtle: var(--color-amber-50);
  --color-warning-muted:  var(--color-amber-100);

  --color-error:          var(--color-red-500);
  --color-error-subtle:   var(--color-red-50);
  --color-error-muted:    var(--color-red-100);
}
```

- [ ] **Step 3: Create src/tokens/spacing.css**

Write to `src/tokens/spacing.css`:
```css
:root {
  --space-0:    0;
  --space-px:   1px;
  --space-0-5:  0.125rem;
  --space-1:    0.25rem;
  --space-1-5:  0.375rem;
  --space-2:    0.5rem;
  --space-2-5:  0.625rem;
  --space-3:    0.75rem;
  --space-3-5:  0.875rem;
  --space-4:    1rem;
  --space-5:    1.25rem;
  --space-6:    1.5rem;
  --space-7:    1.75rem;
  --space-8:    2rem;
  --space-9:    2.25rem;
  --space-10:   2.5rem;
  --space-12:   3rem;
  --space-14:   3.5rem;
  --space-16:   4rem;
  --space-20:   5rem;
  --space-24:   6rem;
  --space-32:   8rem;
  --space-40:   10rem;
  --space-48:   12rem;
  --space-64:   16rem;

  --spacing-page-x:    var(--space-8);
  --spacing-page-y:    var(--space-8);
  --spacing-section:   var(--space-12);
  --spacing-block:     var(--space-8);
  --spacing-panel:     var(--space-6);
  --spacing-panel-sm:  var(--space-4);
  --spacing-inline:    var(--space-3);
  --spacing-inline-sm: var(--space-2);
  --spacing-form-gap:  var(--space-5);
  --spacing-list-gap:  var(--space-3);

  --width-sidebar:    260px;
  --width-sidebar-sm: 220px;
  --width-panel:      320px;
  --width-content:    720px;
  --width-wide:       960px;
  --width-full:       100%;

  --height-topbar:    52px;
  --height-bottombar: 68px;
  --height-input-sm:  30px;
  --height-input-md:  36px;
  --height-input-lg:  44px;
  --height-btn-sm:    28px;
  --height-btn-md:    34px;
  --height-btn-lg:    42px;
}
```

- [ ] **Step 4: Create src/tokens/effects.css**

Write to `src/tokens/effects.css`:
```css
:root {
  --radius-none: 0;
  --radius-xs:   4px;
  --radius-sm:   6px;
  --radius-md:   10px;
  --radius-lg:   14px;
  --radius-xl:   18px;
  --radius-2xl:  24px;
  --radius-3xl:  32px;
  --radius-full: 9999px;

  --shadow-none: none;
  --shadow-xs:   0 1px 2px rgba(0,0,0,0.04);
  --shadow-sm:   0 1px 3px rgba(0,0,0,0.06), 0 1px 2px rgba(0,0,0,0.04);
  --shadow-md:   0 4px 12px rgba(0,0,0,0.07), 0 2px 4px rgba(0,0,0,0.04);
  --shadow-lg:   0 8px 24px rgba(0,0,0,0.08), 0 4px 8px rgba(0,0,0,0.04);
  --shadow-xl:   0 16px 48px rgba(0,0,0,0.10), 0 8px 16px rgba(0,0,0,0.05);
  --shadow-2xl:  0 32px 64px rgba(0,0,0,0.14), 0 16px 32px rgba(0,0,0,0.06);
  --shadow-inset-sm: inset 0 1px 2px rgba(0,0,0,0.06);
  --shadow-inset-md: inset 0 2px 4px rgba(0,0,0,0.08);

  --focus-ring-blue:  0 0 0 3px rgba(26,86,219,0.18);
  --focus-ring-error: 0 0 0 3px rgba(255,59,48,0.18);
  --focus-ring-green: 0 0 0 3px rgba(48,197,89,0.18);

  --border-subtle: 1px solid var(--color-border-subtle);
  --border-base:   1px solid var(--color-border);
  --border-strong: 1px solid var(--color-border-strong);

  --ease-linear: linear;
  --ease-out:    cubic-bezier(0.0, 0.0, 0.2, 1);
  --ease-in:     cubic-bezier(0.4, 0.0, 1.0, 1);
  --ease-inout:  cubic-bezier(0.4, 0.0, 0.2, 1);
  --ease-spring: cubic-bezier(0.34, 1.56, 0.64, 1);
  --ease-bounce: cubic-bezier(0.34, 1.40, 0.64, 1);

  --duration-instant:  50ms;
  --duration-fast:    100ms;
  --duration-base:    180ms;
  --duration-slow:    280ms;
  --duration-slower:  400ms;
  --duration-slowest: 600ms;

  --transition-fast:   var(--duration-fast)   var(--ease-out);
  --transition-base:   var(--duration-base)   var(--ease-out);
  --transition-slow:   var(--duration-slow)   var(--ease-out);
  --transition-spring: var(--duration-slow)   var(--ease-spring);
  --transition-bounce: var(--duration-slower) var(--ease-bounce);

  --blur-sm:  blur(4px);
  --blur-md:  blur(8px);
  --blur-lg:  blur(16px);
  --blur-xl:  blur(24px);
  --blur-2xl: blur(40px);
}
```

- [ ] **Step 5: Create src/tokens/base.css**

Write to `src/tokens/base.css`:
```css
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

html {
  font-size: 16px;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
  text-rendering: optimizeLegibility;
  scroll-behavior: smooth;
}

body {
  font-family: var(--font-sans);
  font-size: var(--text-base);
  line-height: var(--leading-normal);
  color: var(--color-text-primary);
  background: var(--color-bg);
  letter-spacing: var(--tracking-normal);
}

h1, h2, h3, h4, h5, h6 {
  font-weight: var(--weight-semibold);
  line-height: var(--leading-tight);
  letter-spacing: var(--tracking-snug);
  color: var(--color-text-primary);
}

button, input, select, textarea { font-family: inherit; font-size: inherit; }
button { cursor: pointer; border: none; background: none; }
a { color: var(--color-text-link); text-decoration: none; }
input, textarea, select { outline: none; appearance: none; -webkit-appearance: none; }
::placeholder { color: var(--color-text-tertiary); opacity: 1; }
::selection { background: var(--color-accent-muted); color: var(--color-accent); }

::-webkit-scrollbar { width: 6px; height: 6px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: var(--color-gray-200); border-radius: var(--radius-full); }
::-webkit-scrollbar-thumb:hover { background: var(--color-gray-300); }

@keyframes db-spin { to { transform: rotate(360deg); } }
@keyframes db-pulse { 0%,100%{opacity:1} 50%{opacity:0.45} }
@keyframes db-fade-in { from{opacity:0;transform:translateY(4px)} to{opacity:1;transform:translateY(0)} }
@keyframes db-fade-out { from{opacity:1;transform:translateY(0)} to{opacity:0;transform:translateY(4px)} }
@keyframes db-scale-in { from{opacity:0;transform:scale(0.95)} to{opacity:1;transform:scale(1)} }
@keyframes db-shimmer { 0%{background-position:-400px 0} 100%{background-position:400px 0} }

.db-skeleton {
  background: linear-gradient(90deg, var(--color-gray-100) 25%, var(--color-gray-50) 50%, var(--color-gray-100) 75%);
  background-size: 800px 100%;
  animation: db-shimmer 1.4s ease-in-out infinite;
  border-radius: var(--radius-sm);
}
```

- [ ] **Step 6: Update src/index.css**

Write to `src/index.css`:
```css
@import './tokens/typography.css';
@import './tokens/colors.css';
@import './tokens/spacing.css';
@import './tokens/effects.css';
@import './tokens/base.css';

html, body, #root { height: 100%; }
```

---

## Task 3: Create TypeScript Types

**Files:**
- Create: `src/types/index.ts`

- [ ] **Step 1: Write src/types/index.ts**

```powershell
New-Item -ItemType Directory -Force src\types
```

Write to `src/types/index.ts`:
```typescript
export type Stage =
  | 'pending'
  | 'prompting'
  | 'planning'
  | 'validating'
  | 'generating'
  | 'complete'
  | 'error'

export type Framework = 'forge' | 'openai' | 'risen'
export type Personality = 'formal' | 'socratic' | 'encouraging' | 'challenging'
export type Length = 'short' | 'medium' | 'long'

export interface ControlSet {
  id?: number
  personality: Personality
  prompt_length: Length
  result_length: Length
  action_word_count: number
}

export interface MCQOption {
  id: number
  body: string
  is_correct: boolean
}

export interface Question {
  id: number
  type: 'mcq' | 'long_answer'
  body: string
  order: number
  options?: MCQOption[]
  model_answer?: string
}

export interface Assessment {
  id: number
  run_id: number
  framework: Framework
  control_set_id: number
  status: Stage
  questions?: Question[]
}

export interface Run {
  id: number
  topic: string
  expectations: string
  mcq_count: number
  long_answer_count: number
  created_at: string
  control_sets: ControlSet[]
  assessments: Assessment[]
}

export interface SSEEvent {
  assessment_id: number
  framework: Framework
  control_set: number
  stage: Stage
}

export interface CreateRunPayload {
  topic: string
  expectations: string
  mcq_count: number
  long_answer_count: number
  frameworks: Framework[]
  control_sets: Omit<ControlSet, 'id'>[]
}
```

---

## Task 4: Port UI Components — Button, Input, Badge, Card

**Files:**
- Create: `src/components/ui/Button.tsx`
- Create: `src/components/ui/Input.tsx`
- Create: `src/components/ui/Badge.tsx`
- Create: `src/components/ui/Card.tsx`

- [ ] **Step 1: Create directories**

```powershell
New-Item -ItemType Directory -Force src\components\ui
```

- [ ] **Step 2: Create src/components/ui/Button.tsx**

Write to `src/components/ui/Button.tsx`:
```tsx
import { useState, ReactNode, ButtonHTMLAttributes } from 'react'

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary' | 'ghost' | 'outline' | 'destructive'
  size?: 'sm' | 'md' | 'lg'
  loading?: boolean
  icon?: ReactNode
  iconPosition?: 'left' | 'right'
  fullWidth?: boolean
  children?: ReactNode
}

export function Button({
  children,
  variant = 'primary',
  size = 'md',
  disabled = false,
  loading = false,
  icon,
  iconPosition = 'left',
  fullWidth = false,
  onClick,
  type = 'button',
  style,
  ...props
}: ButtonProps) {
  const [hovered, setHovered] = useState(false)
  const [pressed, setPressed] = useState(false)

  const sizes = {
    sm: { fontSize: '12px', padding: '0 11px', height: '28px', borderRadius: '7px', gap: '5px', iconSize: '13px' },
    md: { fontSize: '13px', padding: '0 15px', height: '34px', borderRadius: '9px', gap: '6px', iconSize: '14px' },
    lg: { fontSize: '15px', padding: '0 20px', height: '42px', borderRadius: '11px', gap: '7px', iconSize: '16px' },
  }

  const s = sizes[size]
  const isActive = hovered && !disabled
  const isPressed = pressed && !disabled

  const variantStyles: Record<string, object> = {
    primary: {
      background: isPressed ? 'var(--color-blue-700)' : isActive ? 'var(--color-accent-hover)' : 'var(--color-accent)',
      color: 'var(--color-white)',
      border: 'none',
      boxShadow: isActive ? '0 2px 8px rgba(26,86,219,0.32)' : '0 1px 3px rgba(26,86,219,0.20)',
    },
    secondary: {
      background: isPressed ? 'var(--color-gray-200)' : isActive ? 'var(--color-gray-100)' : 'var(--color-gray-50)',
      color: 'var(--color-text-primary)',
      border: '1px solid var(--color-border)',
      boxShadow: 'var(--shadow-xs)',
    },
    ghost: {
      background: isPressed ? 'var(--color-gray-100)' : isActive ? 'var(--color-gray-50)' : 'transparent',
      color: 'var(--color-text-primary)',
      border: 'none',
      boxShadow: 'none',
    },
    outline: {
      background: isPressed ? 'var(--color-blue-50)' : isActive ? 'var(--color-accent-subtle)' : 'transparent',
      color: 'var(--color-accent)',
      border: '1.5px solid var(--color-accent)',
      boxShadow: 'none',
    },
    destructive: {
      background: isPressed ? 'var(--color-red-600)' : isActive ? '#e8342a' : 'var(--color-error)',
      color: 'var(--color-white)',
      border: 'none',
      boxShadow: isActive ? '0 2px 8px rgba(255,59,48,0.32)' : '0 1px 3px rgba(255,59,48,0.20)',
    },
  }

  const btnStyle: object = {
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'center',
    gap: s.gap,
    height: s.height,
    padding: s.padding,
    borderRadius: s.borderRadius,
    fontSize: s.fontSize,
    fontFamily: 'var(--font-sans)',
    fontWeight: '500',
    letterSpacing: '-0.01em',
    whiteSpace: 'nowrap',
    cursor: disabled ? 'not-allowed' : 'pointer',
    transition: 'background 150ms var(--ease-out), box-shadow 150ms var(--ease-out), transform 100ms var(--ease-out)',
    outline: 'none',
    width: fullWidth ? '100%' : undefined,
    opacity: disabled ? 0.42 : 1,
    transform: isPressed ? 'scale(0.977)' : 'scale(1)',
    flexShrink: 0,
    ...variantStyles[variant],
    ...style,
  }

  const spinnerStyle: object = {
    display: 'inline-block',
    width: s.iconSize,
    height: s.iconSize,
    border: '1.5px solid currentColor',
    borderTopColor: 'transparent',
    borderRadius: '50%',
    animation: 'db-spin 0.55s linear infinite',
    flexShrink: 0,
  }

  return (
    <button
      type={type}
      style={btnStyle}
      disabled={disabled}
      onClick={!disabled ? onClick : undefined}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => { setHovered(false); setPressed(false) }}
      onMouseDown={() => setPressed(true)}
      onMouseUp={() => setPressed(false)}
      {...props}
    >
      {loading ? <span style={spinnerStyle} /> : (icon && iconPosition === 'left' ? icon : null)}
      {children}
      {!loading && icon && iconPosition === 'right' ? icon : null}
    </button>
  )
}
```

- [ ] **Step 3: Create src/components/ui/Input.tsx**

Write to `src/components/ui/Input.tsx`:
```tsx
import { useState, ReactNode, InputHTMLAttributes } from 'react'

interface InputProps extends Omit<InputHTMLAttributes<HTMLInputElement>, 'size' | 'prefix'> {
  label?: string
  error?: string
  hint?: string
  size?: 'sm' | 'md' | 'lg'
  prefix?: ReactNode
  suffix?: ReactNode
}

export function Input({
  label,
  placeholder,
  value,
  onChange,
  type = 'text',
  error,
  hint,
  disabled = false,
  readOnly = false,
  size = 'md',
  prefix,
  suffix,
  id,
  ...props
}: InputProps) {
  const [focused, setFocused] = useState(false)

  const inputId = id || (label ? label.toLowerCase().replace(/\s+/g, '-') : undefined)

  const heights: Record<string, string> = { sm: '30px', md: '36px', lg: '44px' }
  const fontSizes: Record<string, string> = { sm: '12px', md: '13px', lg: '15px' }
  const paddings: Record<string, string> = { sm: '0 10px', md: '0 12px', lg: '0 14px' }

  const wrapperStyle: object = {
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
    height: heights[size],
    padding: paddings[size],
    background: disabled ? 'var(--color-bg-secondary)' : readOnly ? 'var(--color-gray-50)' : 'var(--color-white)',
    border: `1px solid ${error ? 'var(--color-error)' : focused ? 'var(--color-accent)' : 'var(--color-border)'}`,
    borderRadius: 'var(--radius-md)',
    boxShadow: focused ? (error ? 'var(--focus-ring-error)' : 'var(--focus-ring-blue)') : 'none',
    transition: 'border-color var(--transition-fast), box-shadow var(--transition-fast)',
    cursor: disabled ? 'not-allowed' : readOnly ? 'default' : 'text',
  }

  const inputStyle: object = {
    flex: 1,
    border: 'none',
    outline: 'none',
    background: 'transparent',
    fontSize: fontSizes[size],
    fontFamily: 'var(--font-sans)',
    color: disabled ? 'var(--color-text-disabled)' : 'var(--color-text-primary)',
    letterSpacing: '-0.01em',
    width: '100%',
    minWidth: 0,
  }

  const affixStyle: object = {
    fontSize: fontSizes[size],
    color: 'var(--color-text-tertiary)',
    flexShrink: 0,
    whiteSpace: 'nowrap',
    userSelect: 'none',
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '5px', width: '100%' }}>
      {label && (
        <label htmlFor={inputId} style={{
          fontSize: '12px', fontWeight: '500', fontFamily: 'var(--font-sans)',
          color: error ? 'var(--color-error)' : 'var(--color-text-secondary)',
          letterSpacing: '-0.01em', userSelect: 'none',
        }}>
          {label}
        </label>
      )}
      <div style={wrapperStyle}>
        {prefix && <span style={affixStyle}>{prefix}</span>}
        <input
          id={inputId}
          type={type}
          value={value}
          onChange={disabled || readOnly ? undefined : onChange}
          placeholder={placeholder}
          disabled={disabled}
          readOnly={readOnly}
          style={inputStyle}
          onFocus={() => !disabled && setFocused(true)}
          onBlur={() => setFocused(false)}
          {...props}
        />
        {suffix && <span style={affixStyle}>{suffix}</span>}
      </div>
      {(error || hint) && (
        <span style={{
          fontSize: '11px', fontFamily: 'var(--font-sans)',
          color: error ? 'var(--color-error)' : 'var(--color-text-tertiary)',
          lineHeight: '1.4', letterSpacing: '-0.01em',
        }}>
          {error || hint}
        </span>
      )}
    </div>
  )
}
```

- [ ] **Step 4: Create src/components/ui/Badge.tsx**

Write to `src/components/ui/Badge.tsx`:
```tsx
import { ReactNode, HTMLAttributes } from 'react'

interface BadgeProps extends HTMLAttributes<HTMLSpanElement> {
  variant?: 'default' | 'info' | 'success' | 'warning' | 'error' | 'purple'
  size?: 'sm' | 'md' | 'lg'
  dot?: boolean
  children?: ReactNode
}

export function Badge({ children, variant = 'default', size = 'md', dot = false, style, ...props }: BadgeProps) {
  const variants: Record<string, object> = {
    default: { background: 'var(--color-gray-100)', color: 'var(--color-text-secondary)', border: '1px solid var(--color-border)', dotColor: 'var(--color-gray-400)' },
    info:    { background: 'var(--color-accent-subtle)', color: 'var(--color-blue-600)', border: '1px solid var(--color-blue-200)', dotColor: 'var(--color-accent)' },
    success: { background: 'var(--color-success-subtle)', color: 'var(--color-green-600)', border: '1px solid var(--color-green-200)', dotColor: 'var(--color-success)' },
    warning: { background: 'var(--color-warning-subtle)', color: 'var(--color-amber-600)', border: '1px solid var(--color-amber-100)', dotColor: 'var(--color-warning)' },
    error:   { background: 'var(--color-error-subtle)', color: 'var(--color-red-600)', border: '1px solid var(--color-red-100)', dotColor: 'var(--color-error)' },
    purple:  { background: 'var(--color-purple-50)', color: 'var(--color-purple-500)', border: '1px solid var(--color-purple-200)', dotColor: 'var(--color-purple-500)' },
  }

  const sizes: Record<string, object> = {
    sm: { fontSize: '10px', padding: '1px 6px', height: '17px', borderRadius: '5px', gap: '3px', dotSize: '4px' },
    md: { fontSize: '11px', padding: '2px 7px', height: '20px', borderRadius: '6px', gap: '4px', dotSize: '5px' },
    lg: { fontSize: '12px', padding: '3px 9px', height: '24px', borderRadius: '7px', gap: '5px', dotSize: '6px' },
  }

  const v = variants[variant] as any
  const s = sizes[size] as any

  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: s.gap, height: s.height,
      padding: s.padding, borderRadius: s.borderRadius, fontSize: s.fontSize,
      fontFamily: 'var(--font-sans)', fontWeight: '500', letterSpacing: '0.01em',
      whiteSpace: 'nowrap', background: v.background, color: v.color, border: v.border, lineHeight: 1,
      ...style,
    }} {...props}>
      {dot && <span style={{ width: s.dotSize, height: s.dotSize, borderRadius: '50%', background: v.dotColor, flexShrink: 0, display: 'inline-block' }} />}
      {children}
    </span>
  )
}
```

- [ ] **Step 5: Create src/components/ui/Card.tsx**

Write to `src/components/ui/Card.tsx`:
```tsx
import { useState, ReactNode, HTMLAttributes } from 'react'

interface CardProps extends HTMLAttributes<HTMLDivElement> {
  variant?: 'default' | 'elevated' | 'bordered' | 'subtle'
  padding?: 'none' | 'sm' | 'md' | 'lg' | 'xl'
  interactive?: boolean
  selected?: boolean
  children?: ReactNode
}

export function Card({
  children,
  variant = 'default',
  padding = 'md',
  interactive = false,
  selected = false,
  onClick,
  style,
  ...props
}: CardProps) {
  const [hovered, setHovered] = useState(false)

  const paddingMap: Record<string, string> = {
    none: '0',
    sm:   'var(--space-4)',
    md:   'var(--space-5) var(--space-6)',
    lg:   'var(--space-6) var(--space-8)',
    xl:   'var(--space-8) var(--space-10)',
  }

  const baseStyles: Record<string, object> = {
    default:  { background: 'var(--color-surface)', border: selected ? '1.5px solid var(--color-accent)' : '1px solid var(--color-border)', boxShadow: interactive && hovered ? 'var(--shadow-md)' : 'var(--shadow-sm)' },
    elevated: { background: 'var(--color-surface)', border: selected ? '1.5px solid var(--color-accent)' : 'none', boxShadow: interactive && hovered ? 'var(--shadow-lg)' : 'var(--shadow-md)' },
    bordered: { background: 'var(--color-surface)', border: selected ? '1.5px solid var(--color-accent)' : 'var(--border-strong)', boxShadow: 'none' },
    subtle:   { background: selected ? 'var(--color-accent-subtle)' : 'var(--color-bg-secondary)', border: selected ? '1.5px solid var(--color-blue-200)' : 'var(--border-subtle)', boxShadow: 'none' },
  }

  return (
    <div
      style={{
        borderRadius: 'var(--radius-lg)',
        padding: paddingMap[padding],
        cursor: interactive ? 'pointer' : 'default',
        transition: 'box-shadow var(--transition-base), transform var(--transition-base), border-color var(--transition-fast)',
        transform: interactive && hovered && !selected ? 'translateY(-1px)' : 'translateY(0)',
        outline: 'none',
        ...baseStyles[variant],
        ...style,
      }}
      onClick={interactive ? onClick : undefined}
      onMouseEnter={interactive ? () => setHovered(true) : undefined}
      onMouseLeave={interactive ? () => setHovered(false) : undefined}
      {...props}
    >
      {children}
    </div>
  )
}
```

---

## Task 5: Port UI Components — Select, Tabs, Switch, Checkbox

**Files:**
- Create: `src/components/ui/Select.tsx`
- Create: `src/components/ui/Tabs.tsx`
- Create: `src/components/ui/Switch.tsx`
- Create: `src/components/ui/Checkbox.tsx`

- [ ] **Step 1: Create src/components/ui/Select.tsx**

Write to `src/components/ui/Select.tsx`:
```tsx
import { useState, SelectHTMLAttributes } from 'react'

interface SelectOption { value: string; label: string; disabled?: boolean }

interface SelectProps extends Omit<SelectHTMLAttributes<HTMLSelectElement>, 'size'> {
  label?: string
  options?: SelectOption[]
  error?: string
  hint?: string
  size?: 'sm' | 'md' | 'lg'
  placeholder?: string
}

export function Select({ label, value, onChange, options = [], disabled = false, error, hint, size = 'md', placeholder, id, ...props }: SelectProps) {
  const [focused, setFocused] = useState(false)
  const inputId = id || (label ? label.toLowerCase().replace(/\s+/g, '-') : undefined)
  const heights: Record<string, string> = { sm: '30px', md: '36px', lg: '44px' }
  const fontSizes: Record<string, string> = { sm: '12px', md: '13px', lg: '15px' }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '5px', width: '100%' }}>
      {label && (
        <label htmlFor={inputId} style={{ fontSize: '12px', fontWeight: '500', fontFamily: 'var(--font-sans)', color: error ? 'var(--color-error)' : 'var(--color-text-secondary)', letterSpacing: '-0.01em', userSelect: 'none' }}>
          {label}
        </label>
      )}
      <div style={{ position: 'relative', width: '100%' }}>
        <select
          id={inputId}
          value={value}
          onChange={disabled ? undefined : onChange}
          disabled={disabled}
          style={{
            width: '100%', height: heights[size], padding: `0 32px 0 12px`,
            fontSize: fontSizes[size], fontFamily: 'var(--font-sans)', fontWeight: '400',
            letterSpacing: '-0.01em', color: value ? 'var(--color-text-primary)' : 'var(--color-text-tertiary)',
            background: disabled ? 'var(--color-bg-secondary)' : 'var(--color-white)',
            border: `1px solid ${error ? 'var(--color-error)' : focused ? 'var(--color-accent)' : 'var(--color-border)'}`,
            borderRadius: 'var(--radius-md)',
            boxShadow: focused ? (error ? 'var(--focus-ring-error)' : 'var(--focus-ring-blue)') : 'none',
            cursor: disabled ? 'not-allowed' : 'pointer',
            transition: 'border-color var(--transition-fast), box-shadow var(--transition-fast)',
            appearance: 'none', WebkitAppearance: 'none', outline: 'none',
            opacity: disabled ? 0.55 : 1,
          }}
          onFocus={() => setFocused(true)}
          onBlur={() => setFocused(false)}
          {...props}
        >
          {placeholder && <option value="" disabled hidden>{placeholder}</option>}
          {options.map(opt => (
            <option key={opt.value} value={opt.value} disabled={opt.disabled}>{opt.label}</option>
          ))}
        </select>
        <span style={{ position: 'absolute', right: '10px', top: '50%', transform: 'translateY(-50%)', pointerEvents: 'none', color: 'var(--color-text-tertiary)', display: 'flex', alignItems: 'center' }}>
          <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
            <path d="M3 5.5l4 4 4-4" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round"/>
          </svg>
        </span>
      </div>
      {(error || hint) && (
        <span style={{ fontSize: '11px', fontFamily: 'var(--font-sans)', color: error ? 'var(--color-error)' : 'var(--color-text-tertiary)', lineHeight: '1.4' }}>
          {error || hint}
        </span>
      )}
    </div>
  )
}
```

- [ ] **Step 2: Create src/components/ui/Tabs.tsx**

Write to `src/components/ui/Tabs.tsx`:
```tsx
import { useState, ReactNode } from 'react'

export interface TabItem { id: string; label: string; icon?: ReactNode; count?: number }

interface TabsProps {
  tabs?: TabItem[]
  activeTab?: string
  onTabChange?: (id: string) => void
  variant?: 'underline' | 'pill' | 'boxed'
}

export function Tabs({ tabs = [], activeTab, onTabChange, variant = 'underline' }: TabsProps) {
  const [hovered, setHovered] = useState<string | null>(null)

  const containerStyles: Record<string, object> = {
    underline: { display: 'flex', borderBottom: '1px solid var(--color-border)', gap: '0' },
    pill: { display: 'inline-flex', gap: '2px', background: 'var(--color-bg-secondary)', borderRadius: 'var(--radius-lg)', padding: '3px' },
    boxed: { display: 'flex', gap: 'var(--space-1)' },
  }

  function getTabStyle(active: boolean, isHovered: boolean): object {
    if (variant === 'underline') return {
      padding: '8px 16px', fontSize: '13px', fontWeight: active ? '500' : '400',
      fontFamily: 'var(--font-sans)', letterSpacing: '-0.01em',
      color: active ? 'var(--color-text-primary)' : isHovered ? 'var(--color-text-secondary)' : 'var(--color-text-tertiary)',
      cursor: 'pointer', background: 'none', border: 'none',
      borderBottom: `2px solid ${active ? 'var(--color-accent)' : 'transparent'}`,
      marginBottom: '-1px', transition: 'color var(--transition-fast), border-color var(--transition-fast)',
      outline: 'none', display: 'flex', alignItems: 'center', gap: '6px', whiteSpace: 'nowrap', flexShrink: 0,
    }
    if (variant === 'pill') return {
      padding: '5px 13px', fontSize: '13px', fontWeight: active ? '500' : '400',
      fontFamily: 'var(--font-sans)', letterSpacing: '-0.01em',
      color: active ? 'var(--color-text-primary)' : isHovered ? 'var(--color-text-secondary)' : 'var(--color-text-tertiary)',
      cursor: 'pointer', background: active ? 'var(--color-white)' : isHovered ? 'rgba(0,0,0,0.03)' : 'transparent',
      border: 'none', borderRadius: 'var(--radius-md)', boxShadow: active ? 'var(--shadow-sm)' : 'none',
      transition: 'all var(--transition-base)', outline: 'none',
      display: 'flex', alignItems: 'center', gap: '6px', whiteSpace: 'nowrap', flexShrink: 0,
    }
    return {
      padding: '5px 13px', fontSize: '13px', fontWeight: active ? '500' : '400',
      fontFamily: 'var(--font-sans)', letterSpacing: '-0.01em',
      color: active ? 'var(--color-accent)' : isHovered ? 'var(--color-text-secondary)' : 'var(--color-text-tertiary)',
      cursor: 'pointer', background: active ? 'var(--color-accent-subtle)' : isHovered ? 'var(--color-bg-secondary)' : 'transparent',
      border: active ? '1px solid var(--color-blue-200)' : '1px solid transparent',
      borderRadius: 'var(--radius-md)', transition: 'all var(--transition-fast)', outline: 'none',
      display: 'flex', alignItems: 'center', gap: '6px', whiteSpace: 'nowrap', flexShrink: 0,
    }
  }

  return (
    <div style={containerStyles[variant]} role="tablist">
      {tabs.map(tab => (
        <button
          key={tab.id}
          role="tab"
          aria-selected={activeTab === tab.id}
          style={getTabStyle(activeTab === tab.id, hovered === tab.id)}
          onClick={() => onTabChange?.(tab.id)}
          onMouseEnter={() => setHovered(tab.id)}
          onMouseLeave={() => setHovered(null)}
        >
          {tab.icon && <span style={{ display: 'inline-flex', flexShrink: 0 }}>{tab.icon}</span>}
          {tab.label}
          {tab.count != null && (
            <span style={{
              fontSize: '10px', fontWeight: '500',
              background: activeTab === tab.id ? 'var(--color-accent)' : 'var(--color-gray-200)',
              color: activeTab === tab.id ? 'white' : 'var(--color-text-secondary)',
              borderRadius: 'var(--radius-full)', padding: '1px 5px', lineHeight: '14px', minWidth: '16px', textAlign: 'center',
            }}>
              {tab.count}
            </span>
          )}
        </button>
      ))}
    </div>
  )
}
```

- [ ] **Step 3: Create src/components/ui/Switch.tsx**

Write to `src/components/ui/Switch.tsx`:
```tsx
interface SwitchProps {
  checked: boolean
  onChange: (checked: boolean) => void
  size?: 'sm' | 'md' | 'lg'
  disabled?: boolean
  label?: string
}

export function Switch({ checked, onChange, size = 'md', disabled = false, label }: SwitchProps) {
  const sizes: Record<string, { track: object; knob: object; knobOn: string }> = {
    sm: { track: { width: 28, height: 16, borderRadius: 99 }, knob: { width: 12, height: 12, top: 2, left: 2 }, knobOn: '14px' },
    md: { track: { width: 36, height: 20, borderRadius: 99 }, knob: { width: 16, height: 16, top: 2, left: 2 }, knobOn: '18px' },
    lg: { track: { width: 44, height: 24, borderRadius: 99 }, knob: { width: 20, height: 20, top: 2, left: 2 }, knobOn: '22px' },
  }
  const s = sizes[size]

  return (
    <label style={{ display: 'inline-flex', alignItems: 'center', gap: '8px', cursor: disabled ? 'not-allowed' : 'pointer', userSelect: 'none' }}>
      <div
        role="switch"
        aria-checked={checked}
        tabIndex={disabled ? -1 : 0}
        onClick={() => !disabled && onChange(!checked)}
        onKeyDown={(e) => { if ((e.key === ' ' || e.key === 'Enter') && !disabled) onChange(!checked) }}
        style={{
          position: 'relative', flexShrink: 0, opacity: disabled ? 0.45 : 1,
          background: checked ? 'var(--color-accent)' : 'var(--color-gray-300)',
          transition: 'background var(--transition-base)',
          ...s.track,
        }}
      >
        <span style={{
          position: 'absolute',
          top: (s.knob as any).top,
          left: checked ? s.knobOn : `${(s.knob as any).left}px`,
          width: (s.knob as any).width,
          height: (s.knob as any).height,
          borderRadius: '50%',
          background: 'white',
          boxShadow: '0 1px 3px rgba(0,0,0,0.2)',
          transition: 'left var(--transition-spring)',
        }} />
      </div>
      {label && <span style={{ fontSize: '13px', fontFamily: 'var(--font-sans)', color: 'var(--color-text-primary)' }}>{label}</span>}
    </label>
  )
}
```

- [ ] **Step 4: Create src/components/ui/Checkbox.tsx**

Write to `src/components/ui/Checkbox.tsx`:
```tsx
interface CheckboxProps {
  checked: boolean
  indeterminate?: boolean
  onChange: (checked: boolean) => void
  disabled?: boolean
  label?: string
  description?: string
}

export function Checkbox({ checked, indeterminate = false, onChange, disabled = false, label, description }: CheckboxProps) {
  const isChecked = checked || indeterminate

  return (
    <label style={{ display: 'inline-flex', alignItems: 'flex-start', gap: '8px', cursor: disabled ? 'not-allowed' : 'pointer', userSelect: 'none' }}>
      <div
        role="checkbox"
        aria-checked={indeterminate ? 'mixed' : checked}
        tabIndex={disabled ? -1 : 0}
        onClick={() => !disabled && onChange(!checked)}
        onKeyDown={(e) => { if ((e.key === ' ' || e.key === 'Enter') && !disabled) onChange(!checked) }}
        style={{
          width: 16, height: 16, borderRadius: 4, flexShrink: 0, marginTop: 1,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          background: isChecked ? 'var(--color-accent)' : 'var(--color-white)',
          border: isChecked ? '1.5px solid var(--color-accent)' : '1.5px solid var(--color-border)',
          transition: 'background var(--transition-fast), border-color var(--transition-fast)',
          opacity: disabled ? 0.45 : 1,
        }}
      >
        {indeterminate && (
          <svg width="8" height="2" viewBox="0 0 8 2" fill="none">
            <rect width="8" height="2" rx="1" fill="white"/>
          </svg>
        )}
        {!indeterminate && checked && (
          <svg width="9" height="7" viewBox="0 0 9 7" fill="none">
            <path d="M1 3.5L3.5 6L8 1" stroke="white" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
          </svg>
        )}
      </div>
      {(label || description) && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '2px' }}>
          {label && <span style={{ fontSize: '13px', fontFamily: 'var(--font-sans)', color: 'var(--color-text-primary)', fontWeight: '500' }}>{label}</span>}
          {description && <span style={{ fontSize: '12px', fontFamily: 'var(--font-sans)', color: 'var(--color-text-secondary)' }}>{description}</span>}
        </div>
      )}
    </label>
  )
}
```

---

## Task 6: API Layer

**Files:**
- Create: `src/api/client.ts`
- Create: `src/api/runs.ts`
- Create: `src/api/assessments.ts`

- [ ] **Step 1: Create directories and src/api/client.ts**

```powershell
New-Item -ItemType Directory -Force src\api
```

Write to `src/api/client.ts`:
```typescript
const BASE = '/api'

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...init?.headers },
    ...init,
  })
  if (!res.ok) {
    const text = await res.text()
    throw new Error(`${res.status}: ${text}`)
  }
  return res.json()
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body: unknown) => request<T>(path, { method: 'POST', body: JSON.stringify(body) }),
}
```

- [ ] **Step 2: Create src/api/runs.ts**

Write to `src/api/runs.ts`:
```typescript
import { api } from './client'
import { CreateRunPayload, Run } from '../types'

export const runsApi = {
  create: (payload: CreateRunPayload): Promise<{ id: number }> =>
    api.post('/runs', payload),

  get: (id: number): Promise<Run> =>
    api.get(`/runs/${id}`),
}
```

- [ ] **Step 3: Create src/api/assessments.ts**

Write to `src/api/assessments.ts`:
```typescript
import { api } from './client'
import { Assessment } from '../types'

export const assessmentsApi = {
  get: (id: number): Promise<Assessment> =>
    api.get(`/assessments/${id}`),

  regenerate: (id: number): Promise<{ ok: boolean }> =>
    api.post(`/assessments/${id}/regenerate`, {}),

  exportPdf: async (id: number, variant: 'student' | 'answer_key'): Promise<void> => {
    const res = await fetch(`/api/assessments/${id}/export-pdf`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ variant }),
    })
    if (!res.ok) throw new Error('PDF export failed')
    const blob = await res.blob()
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `assessment-${id}-${variant}.pdf`
    a.click()
    URL.revokeObjectURL(url)
  },
}
```

---

## Task 7: Zustand Store and SSE Hook

**Files:**
- Create: `src/store/runStore.ts`
- Create: `src/hooks/useSSE.ts`

- [ ] **Step 1: Create src/store/runStore.ts**

```powershell
New-Item -ItemType Directory -Force src\store
New-Item -ItemType Directory -Force src\hooks
```

Write to `src/store/runStore.ts`:
```typescript
import { create } from 'zustand'
import { Run, Assessment, SSEEvent } from '../types'

interface RunStore {
  run: Run | null
  assessments: Record<number, Assessment>
  selectedAssessmentId: number | null

  setRun: (run: Run) => void
  applySSEEvent: (event: SSEEvent) => void
  setAssessment: (assessment: Assessment) => void
  selectAssessment: (id: number) => void
  reset: () => void
}

export const useRunStore = create<RunStore>((set) => ({
  run: null,
  assessments: {},
  selectedAssessmentId: null,

  setRun: (run) => {
    const assessments: Record<number, Assessment> = {}
    run.assessments.forEach(a => { assessments[a.id] = a })
    set({ run, assessments, selectedAssessmentId: null })
  },

  applySSEEvent: (event) => set((state) => {
    const existing = Object.values(state.assessments).find(
      a => a.framework === event.framework && a.control_set_id === event.control_set
    )
    if (!existing) return state
    const updated = { ...existing, status: event.stage }
    const assessments = { ...state.assessments, [existing.id]: updated }
    const selectedAssessmentId =
      state.selectedAssessmentId === null && event.stage === 'complete'
        ? existing.id
        : state.selectedAssessmentId
    return { assessments, selectedAssessmentId }
  }),

  setAssessment: (assessment) => set((state) => ({
    assessments: { ...state.assessments, [assessment.id]: assessment },
  })),

  selectAssessment: (id) => set({ selectedAssessmentId: id }),

  reset: () => set({ run: null, assessments: {}, selectedAssessmentId: null }),
}))
```

- [ ] **Step 2: Create src/hooks/useSSE.ts**

Write to `src/hooks/useSSE.ts`:
```typescript
import { useEffect } from 'react'
import { SSEEvent } from '../types'

export function useSSE(
  runId: number | null,
  onEvent: (event: SSEEvent) => void,
  onDone?: () => void,
) {
  useEffect(() => {
    if (!runId) return
    const es = new EventSource(`/api/runs/${runId}/events`)

    es.onmessage = (e) => {
      const data: SSEEvent = JSON.parse(e.data)
      onEvent(data)
    }

    es.addEventListener('done', () => {
      es.close()
      onDone?.()
    })

    es.onerror = () => es.close()

    return () => es.close()
  }, [runId])
}
```

---

## Task 8: App.tsx and Routing

**Files:**
- Modify: `src/App.tsx`
- Modify: `src/main.tsx`

- [ ] **Step 1: Write src/App.tsx**

Write to `src/App.tsx`:
```tsx
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { InputPanelPage } from './pages/InputPanelPage'
import { ProgressPage } from './pages/ProgressPage'
import { AssessmentViewerPage } from './pages/AssessmentViewerPage'

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<InputPanelPage />} />
        <Route path="/runs/:runId/progress" element={<ProgressPage />} />
        <Route path="/runs/:runId/viewer" element={<AssessmentViewerPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  )
}
```

- [ ] **Step 2: Verify src/main.tsx imports index.css**

Ensure `src/main.tsx` contains:
```tsx
import React from 'react'
import ReactDOM from 'react-dom/client'
import './index.css'
import App from './App.tsx'

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)
```

---

## Task 9: Input Panel Page

**Files:**
- Create: `src/pages/InputPanelPage.tsx`

- [ ] **Step 1: Create src/pages/ directory**

```powershell
New-Item -ItemType Directory -Force src\pages
```

- [ ] **Step 2: Write src/pages/InputPanelPage.tsx**

Write to `src/pages/InputPanelPage.tsx`:
```tsx
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Button } from '../components/ui/Button'
import { Input } from '../components/ui/Input'
import { Select } from '../components/ui/Select'
import { Checkbox } from '../components/ui/Checkbox'
import { runsApi } from '../api/runs'
import { useRunStore } from '../store/runStore'
import { ControlSet, Framework, Personality, Length } from '../types'

const defaultControlSet = (): Omit<ControlSet, 'id'> => ({
  personality: 'formal',
  prompt_length: 'medium',
  result_length: 'medium',
  action_word_count: 3,
})

const personalityOptions = [
  { value: 'formal', label: 'Formal' },
  { value: 'socratic', label: 'Socratic' },
  { value: 'encouraging', label: 'Encouraging' },
  { value: 'challenging', label: 'Challenging' },
]

const lengthOptions = [
  { value: 'short', label: 'Short' },
  { value: 'medium', label: 'Medium' },
  { value: 'long', label: 'Long' },
]

export function InputPanelPage() {
  const navigate = useNavigate()
  const reset = useRunStore(s => s.reset)

  const [topic, setTopic] = useState('')
  const [expectations, setExpectations] = useState('')
  const [mcqCount, setMcqCount] = useState(10)
  const [longAnswerCount, setLongAnswerCount] = useState(3)
  const [frameworks, setFrameworks] = useState<Record<Framework, boolean>>({ forge: true, openai: true, risen: true })
  const [controlSets, setControlSets] = useState<Omit<ControlSet, 'id'>[]>([
    defaultControlSet(), defaultControlSet(), defaultControlSet(), defaultControlSet(),
  ])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const selectedFrameworks = (Object.keys(frameworks) as Framework[]).filter(k => frameworks[k])

  const updateControlSet = (i: number, key: keyof Omit<ControlSet, 'id'>, value: string | number) => {
    setControlSets(prev => prev.map((cs, idx) => idx === i ? { ...cs, [key]: value } : cs))
  }

  const handleSubmit = async () => {
    if (!topic.trim()) { setError('Topic is required'); return }
    if (!expectations.trim()) { setError('Expectations are required'); return }
    if (selectedFrameworks.length === 0) { setError('Select at least one framework'); return }

    setLoading(true)
    setError('')
    reset()

    try {
      const { id } = await runsApi.create({
        topic: topic.trim(),
        expectations: expectations.trim(),
        mcq_count: mcqCount,
        long_answer_count: longAnswerCount,
        frameworks: selectedFrameworks,
        control_sets: controlSets,
      })
      navigate(`/runs/${id}/progress`)
    } catch (e: any) {
      setError(e.message || 'Failed to create run')
      setLoading(false)
    }
  }

  return (
    <div style={{ height: '100vh', display: 'flex', flexDirection: 'column', fontFamily: 'var(--font-sans)', background: 'var(--color-bg-secondary)' }}>

      {/* Topbar */}
      <div style={{ height: 'var(--height-topbar)', background: 'var(--color-surface)', borderBottom: '1px solid var(--color-border)', display: 'flex', alignItems: 'center', padding: '0 24px', gap: 12, flexShrink: 0 }}>
        <svg width="22" height="22" viewBox="0 0 40 40" fill="none">
          <rect width="40" height="40" rx="10" fill="#1A56DB"/>
          <path d="M9 11h8.5C21.09 11 24 13.91 24 17.5v5C24 26.09 21.09 29 17.5 29H9V11z" stroke="white" strokeWidth="2" fill="none" strokeLinejoin="round"/>
        </svg>
        <span style={{ fontSize: 14, fontWeight: 600, color: 'var(--color-text-primary)', letterSpacing: '-0.02em' }}>Assessment Generator</span>
        <span style={{ fontSize: 13, color: 'var(--color-text-tertiary)' }}>New Run</span>
      </div>

      {/* Body */}
      <div style={{ flex: 1, overflow: 'auto', display: 'flex', gap: 0 }}>

        {/* Sidebar */}
        <div style={{ width: 'var(--width-panel)', background: 'var(--color-surface)', borderRight: '1px solid var(--color-border)', padding: '24px 20px', display: 'flex', flexDirection: 'column', gap: 24, overflowY: 'auto', flexShrink: 0 }}>

          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            <div style={{ fontSize: 11, fontWeight: 600, letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--color-text-tertiary)' }}>Topic</div>
            <Input label="Chapter / Topic" placeholder="e.g. Introduction to Statistics" value={topic} onChange={e => setTopic(e.target.value)} />
            <Input label="Expectations" placeholder="What should students demonstrate?" value={expectations} onChange={e => setExpectations(e.target.value)} />
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            <div style={{ fontSize: 11, fontWeight: 600, letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--color-text-tertiary)' }}>Question Mix</div>
            <div style={{ display: 'flex', gap: 8 }}>
              <Input label="MCQ" type="number" value={String(mcqCount)} onChange={e => setMcqCount(Number(e.target.value))} suffix="q" size="sm" />
              <Input label="Long Answer" type="number" value={String(longAnswerCount)} onChange={e => setLongAnswerCount(Number(e.target.value))} suffix="q" size="sm" />
            </div>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            <div style={{ fontSize: 11, fontWeight: 600, letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--color-text-tertiary)' }}>Frameworks</div>
            <Checkbox checked={frameworks.forge} onChange={v => setFrameworks(p => ({ ...p, forge: v }))} label="Forge-skills" description="Context · Task · Constraints · Verification" />
            <Checkbox checked={frameworks.openai} onChange={v => setFrameworks(p => ({ ...p, openai: v }))} label="OpenAI-style" description="Role · Goal · Measure · Constraints" />
            <Checkbox checked={frameworks.risen} onChange={v => setFrameworks(p => ({ ...p, risen: v }))} label="RISEN" description="Role · Instructions · Steps · End goal" />
          </div>
        </div>

        {/* Main content — control variable sets */}
        <div style={{ flex: 1, padding: '24px 28px', overflowY: 'auto' }}>
          <div style={{ marginBottom: 20 }}>
            <div style={{ fontSize: 16, fontWeight: 600, color: 'var(--color-text-primary)', letterSpacing: '-0.02em', marginBottom: 4 }}>Control Variable Sets</div>
            <div style={{ fontSize: 13, color: 'var(--color-text-secondary)' }}>
              Each set combines with every selected framework — {selectedFrameworks.length} framework{selectedFrameworks.length !== 1 ? 's' : ''} × 4 sets = <strong>{selectedFrameworks.length * 4}</strong> assessments
            </div>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            {controlSets.map((cs, i) => (
              <div key={i} style={{ background: 'var(--color-surface)', border: '1px solid var(--color-border)', borderRadius: 'var(--radius-lg)', padding: '16px 20px' }}>
                <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--color-text-secondary)', marginBottom: 12 }}>Set {i + 1}</div>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr 1fr', gap: 12, alignItems: 'end' }}>
                  <Select label="Personality" size="sm" value={cs.personality} onChange={e => updateControlSet(i, 'personality', e.target.value as Personality)} options={personalityOptions} />
                  <Select label="Prompt Length" size="sm" value={cs.prompt_length} onChange={e => updateControlSet(i, 'prompt_length', e.target.value as Length)} options={lengthOptions} />
                  <Select label="Result Length" size="sm" value={cs.result_length} onChange={e => updateControlSet(i, 'result_length', e.target.value as Length)} options={lengthOptions} />
                  <div>
                    <label style={{ fontSize: '12px', fontWeight: '500', color: 'var(--color-text-secondary)', display: 'block', marginBottom: 5 }}>
                      Action Words ({cs.action_word_count})
                    </label>
                    <input
                      type="range" min={1} max={5} value={cs.action_word_count}
                      onChange={e => updateControlSet(i, 'action_word_count', Number(e.target.value))}
                      style={{ width: '100%', accentColor: 'var(--color-accent)' }}
                    />
                  </div>
                </div>
              </div>
            ))}
          </div>

          {error && (
            <div style={{ marginTop: 16, padding: '10px 14px', background: 'var(--color-error-subtle)', border: '1px solid var(--color-red-100)', borderRadius: 'var(--radius-md)', fontSize: 13, color: 'var(--color-red-600)' }}>
              {error}
            </div>
          )}
        </div>
      </div>

      {/* Bottom bar */}
      <div style={{ height: 'var(--height-bottombar)', background: 'var(--color-surface)', borderTop: '1px solid var(--color-border)', display: 'flex', alignItems: 'center', justifyContent: 'flex-end', padding: '0 28px', flexShrink: 0 }}>
        <Button variant="primary" size="lg" loading={loading} onClick={handleSubmit} disabled={loading}>
          Generate {selectedFrameworks.length * 4} Assessments
        </Button>
      </div>
    </div>
  )
}
```

---

## Task 10: Progress Page

**Files:**
- Create: `src/pages/ProgressPage.tsx`

- [ ] **Step 1: Write src/pages/ProgressPage.tsx**

Write to `src/pages/ProgressPage.tsx`:
```tsx
import { useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { Badge } from '../components/ui/Badge'
import { Button } from '../components/ui/Button'
import { useSSE } from '../hooks/useSSE'
import { useRunStore } from '../store/runStore'
import { runsApi } from '../api/runs'
import { Stage } from '../types'

const stageConfig: Record<Stage, { label: string; variant: 'default' | 'info' | 'success' | 'warning' | 'error' }> = {
  pending:    { label: 'Pending',    variant: 'default' },
  prompting:  { label: 'Prompting',  variant: 'info' },
  planning:   { label: 'Planning',   variant: 'info' },
  validating: { label: 'Validating', variant: 'warning' },
  generating: { label: 'Generating', variant: 'warning' },
  complete:   { label: 'Complete',   variant: 'success' },
  error:      { label: 'Error',      variant: 'error' },
}

const frameworkLabel: Record<string, string> = { forge: 'Forge', openai: 'OpenAI', risen: 'RISEN' }

export function ProgressPage() {
  const { runId } = useParams<{ runId: string }>()
  const navigate = useNavigate()
  const { run, assessments, selectedAssessmentId, setRun, applySSEEvent } = useRunStore()

  const numericRunId = runId ? Number(runId) : null

  useEffect(() => {
    if (!numericRunId) return
    runsApi.get(numericRunId).then(setRun)
  }, [numericRunId])

  useSSE(numericRunId, applySSEEvent)

  const assessmentList = Object.values(assessments)
  const complete = assessmentList.filter(a => a.status === 'complete').length
  const total = assessmentList.length || 12
  const allDone = complete === total && total > 0

  return (
    <div style={{ height: '100vh', display: 'flex', flexDirection: 'column', fontFamily: 'var(--font-sans)' }}>

      {/* Topbar */}
      <div style={{ height: 'var(--height-topbar)', background: 'var(--color-surface)', borderBottom: '1px solid var(--color-border)', display: 'flex', alignItems: 'center', padding: '0 24px', gap: 12, flexShrink: 0 }}>
        <button onClick={() => navigate('/')} style={{ display: 'flex', alignItems: 'center', gap: 5, fontSize: 13, color: 'var(--color-text-secondary)', background: 'none', border: 'none', cursor: 'pointer', fontFamily: 'inherit' }}>
          <svg width="14" height="14" viewBox="0 0 16 16" fill="none"><path d="M10 4L6 8l4 4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/></svg>
          Back
        </button>
        <div style={{ width: 1, height: 20, background: 'var(--color-border)' }} />
        <span style={{ fontSize: 14, fontWeight: 600, color: 'var(--color-text-primary)', letterSpacing: '-0.02em' }}>Generating Assessments</span>
        {run && <span style={{ fontSize: 13, color: 'var(--color-text-tertiary)' }}>{run.topic}</span>}
        <div style={{ flex: 1 }} />
        {allDone && (
          <Button variant="primary" size="sm" onClick={() => navigate(`/runs/${runId}/viewer`)}>
            View Assessments →
          </Button>
        )}
      </div>

      {/* Progress bar */}
      <div style={{ height: 3, background: 'var(--color-gray-100)', flexShrink: 0 }}>
        <div style={{ height: '100%', width: `${(complete / total) * 100}%`, background: 'var(--color-accent)', transition: 'width 0.6s ease', borderRadius: '0 99px 99px 0' }} />
      </div>

      {/* Status summary */}
      <div style={{ background: 'var(--color-surface)', borderBottom: '1px solid var(--color-border)', padding: '10px 28px', display: 'flex', alignItems: 'center', gap: 20, flexShrink: 0 }}>
        {(['complete', 'generating', 'pending'] as Stage[]).map(stage => {
          const count = stage === 'pending'
            ? assessmentList.filter(a => ['pending', 'prompting', 'planning', 'validating'].includes(a.status)).length
            : assessmentList.filter(a => a.status === stage).length
          const colors: Record<string, string> = { complete: '#30C559', generating: '#FF9F0A', pending: '#D2D2D7' }
          const labels: Record<string, string> = { complete: 'complete', generating: 'generating', pending: 'queued' }
          return (
            <div key={stage} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <div style={{ width: 8, height: 8, borderRadius: '50%', background: colors[stage] }} />
              <span style={{ fontSize: 13, color: 'var(--color-text-primary)' }}><strong>{count}</strong> {labels[stage]}</span>
            </div>
          )
        })}
        <div style={{ marginLeft: 'auto', fontSize: 12, color: 'var(--color-text-tertiary)' }}>
          {allDone ? 'All complete — ready to review' : `${complete} / ${total} complete`}
        </div>
      </div>

      {/* Grid */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '24px 28px', background: 'var(--color-bg-secondary)' }}>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4,1fr)', gap: 14, maxWidth: 1200 }}>
          {assessmentList.map(a => {
            const cfg = stageConfig[a.status]
            const isGenerating = ['prompting', 'planning', 'validating', 'generating'].includes(a.status)
            const isComplete = a.status === 'complete'
            const isQueued = a.status === 'pending'

            return (
              <div key={a.id} style={{
                background: 'var(--color-surface)', borderRadius: 'var(--radius-lg)',
                border: '1px solid var(--color-border)', padding: '18px 20px',
                boxShadow: isComplete ? 'var(--shadow-sm)' : 'none',
                opacity: isQueued ? 0.7 : 1,
                animation: 'db-fade-in 0.25s ease',
              }}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <div style={{
                      width: 28, height: 28, borderRadius: 8, flexShrink: 0,
                      background: isComplete ? 'var(--color-accent)' : isGenerating ? 'var(--color-warning)' : 'var(--color-gray-100)',
                      display: 'flex', alignItems: 'center', justifyContent: 'center',
                      fontSize: 11, fontWeight: 700, color: isQueued ? 'var(--color-text-tertiary)' : 'white',
                    }}>
                      {frameworkLabel[a.framework]?.slice(0, 1)}
                    </div>
                    <div>
                      <div style={{ fontSize: 12, fontWeight: 500, color: 'var(--color-text-primary)' }}>{frameworkLabel[a.framework]}</div>
                      <div style={{ fontSize: 11, color: 'var(--color-text-tertiary)' }}>Set {a.control_set_id}</div>
                    </div>
                  </div>
                  <Badge variant={cfg.variant} dot size="sm">{cfg.label}</Badge>
                </div>

                {isGenerating && (
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, color: 'var(--color-text-secondary)' }}>
                    <span style={{ display: 'inline-block', width: 10, height: 10, border: '1.5px solid var(--color-warning)', borderTopColor: 'transparent', borderRadius: '50%', animation: 'db-spin 0.6s linear infinite' }} />
                    {cfg.label}…
                  </div>
                )}

                {isQueued && (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
                    {[85, 60, 75].map((w, i) => (
                      <div key={i} className="db-skeleton" style={{ height: 9, width: `${w}%`, opacity: 0.5 - i * 0.1 }} />
                    ))}
                  </div>
                )}

                {isComplete && (
                  <div style={{ fontSize: 12, color: 'var(--color-text-secondary)' }}>
                    Ready to review
                  </div>
                )}
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}
```

---

## Task 11: Assessment Viewer Page

**Files:**
- Create: `src/pages/AssessmentViewerPage.tsx`

- [ ] **Step 1: Write src/pages/AssessmentViewerPage.tsx**

Write to `src/pages/AssessmentViewerPage.tsx`:
```tsx
import { useEffect, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { Tabs } from '../components/ui/Tabs'
import { Badge } from '../components/ui/Badge'
import { Button } from '../components/ui/Button'
import { useRunStore } from '../store/runStore'
import { runsApi } from '../api/runs'
import { assessmentsApi } from '../api/assessments'
import { Assessment, Question } from '../types'

const frameworkLabel: Record<string, string> = { forge: 'Forge', openai: 'OpenAI', risen: 'RISEN' }

function MCQQuestion({ q }: { q: Question }) {
  const [selected, setSelected] = useState<number | null>(null)
  const [showAnswer, setShowAnswer] = useState(false)
  const correct = q.options?.find(o => o.is_correct)

  return (
    <div style={{ marginBottom: 28 }}>
      <div style={{ fontSize: 13, fontWeight: 500, color: 'var(--color-text-primary)', marginBottom: 10, lineHeight: 1.55 }}>
        <span style={{ color: 'var(--color-text-tertiary)', marginRight: 6 }}>Q{q.order}.</span>
        {q.body}
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginBottom: 10 }}>
        {q.options?.map(opt => (
          <label key={opt.id} style={{
            display: 'flex', alignItems: 'center', gap: 10, padding: '8px 12px', borderRadius: 'var(--radius-md)',
            border: `1px solid ${selected === opt.id ? 'var(--color-accent)' : 'var(--color-border)'}`,
            background: selected === opt.id ? 'var(--color-accent-subtle)' : 'var(--color-surface)',
            cursor: 'pointer', fontSize: 13, color: 'var(--color-text-primary)',
          }}>
            <input type="radio" name={`q-${q.id}`} checked={selected === opt.id} onChange={() => setSelected(opt.id)} style={{ accentColor: 'var(--color-accent)' }} />
            {opt.body}
          </label>
        ))}
      </div>
      <button onClick={() => setShowAnswer(p => !p)} style={{ fontSize: 12, color: 'var(--color-accent)', background: 'none', border: 'none', cursor: 'pointer', fontFamily: 'inherit', padding: 0 }}>
        {showAnswer ? 'Hide' : 'Show'} model answer
      </button>
      {showAnswer && correct && (
        <div style={{ marginTop: 8, padding: '8px 12px', background: 'var(--color-success-subtle)', border: '1px solid var(--color-green-200)', borderRadius: 'var(--radius-md)', fontSize: 12, color: 'var(--color-green-600)' }}>
          ✓ {correct.body}
        </div>
      )}
    </div>
  )
}

function LongAnswerQuestion({ q }: { q: Question }) {
  const [showAnswer, setShowAnswer] = useState(false)

  return (
    <div style={{ marginBottom: 28 }}>
      <div style={{ fontSize: 13, fontWeight: 500, color: 'var(--color-text-primary)', marginBottom: 10, lineHeight: 1.55 }}>
        <span style={{ color: 'var(--color-text-tertiary)', marginRight: 6 }}>Q{q.order}.</span>
        {q.body}
      </div>
      <textarea
        placeholder="Write your answer here..."
        rows={5}
        style={{
          width: '100%', padding: '10px 12px', fontSize: 13, fontFamily: 'var(--font-sans)',
          border: '1px solid var(--color-border)', borderRadius: 'var(--radius-md)',
          background: 'var(--color-surface)', color: 'var(--color-text-primary)',
          resize: 'vertical', outline: 'none', lineHeight: 1.55,
        }}
      />
      <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 6 }}>
        <button onClick={() => setShowAnswer(p => !p)} style={{ fontSize: 12, color: 'var(--color-accent)', background: 'none', border: 'none', cursor: 'pointer', fontFamily: 'inherit', padding: 0 }}>
          {showAnswer ? 'Hide' : 'Show'} model answer
        </button>
        <span style={{ fontSize: 11, color: 'var(--color-text-tertiary)' }}>~200 words</span>
      </div>
      {showAnswer && q.model_answer && (
        <div style={{ marginTop: 8, padding: '10px 12px', background: 'var(--color-accent-subtle)', border: '1px solid var(--color-blue-200)', borderRadius: 'var(--radius-md)', fontSize: 12, color: 'var(--color-text-secondary)', lineHeight: 1.6 }}>
          {q.model_answer}
        </div>
      )}
    </div>
  )
}

export function AssessmentViewerPage() {
  const { runId } = useParams<{ runId: string }>()
  const navigate = useNavigate()
  const { run, assessments, selectedAssessmentId, setRun, selectAssessment, setAssessment } = useRunStore()
  const [activeTab, setActiveTab] = useState('questions')
  const [exportOpen, setExportOpen] = useState(false)
  const [exporting, setExporting] = useState(false)

  const numericRunId = runId ? Number(runId) : null

  useEffect(() => {
    if (!numericRunId) return
    runsApi.get(numericRunId).then(setRun)
  }, [numericRunId])

  const selectedId = selectedAssessmentId ?? Object.values(assessments).find(a => a.status === 'complete')?.id
  const selected: Assessment | undefined = selectedId ? assessments[selectedId] : undefined

  useEffect(() => {
    if (!selected || selected.questions) return
    assessmentsApi.get(selected.id).then(setAssessment)
  }, [selected?.id])

  const handleExport = async (variant: 'student' | 'answer_key') => {
    if (!selectedId) return
    setExporting(true)
    setExportOpen(false)
    try {
      await assessmentsApi.exportPdf(selectedId, variant)
    } finally {
      setExporting(false)
    }
  }

  const handleRegenerate = async () => {
    if (!selectedId) return
    await assessmentsApi.regenerate(selectedId)
  }

  const sidebarAssessments = Object.values(assessments).filter(a => a.id !== selectedId && a.status === 'complete')

  return (
    <div style={{ height: '100vh', display: 'flex', flexDirection: 'column', fontFamily: 'var(--font-sans)' }}>

      {/* Toolbar */}
      <div style={{ height: 'var(--height-topbar)', background: 'var(--color-surface)', borderBottom: '1px solid var(--color-border)', display: 'flex', alignItems: 'center', padding: '0 20px', gap: 10, flexShrink: 0 }}>
        <button onClick={() => navigate(`/runs/${runId}/progress`)} style={{ display: 'flex', alignItems: 'center', gap: 5, fontSize: 13, color: 'var(--color-text-secondary)', background: 'none', border: 'none', cursor: 'pointer', fontFamily: 'inherit' }}>
          <svg width="14" height="14" viewBox="0 0 16 16" fill="none"><path d="M10 4L6 8l4 4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/></svg>
          Back
        </button>
        <div style={{ width: 1, height: 20, background: 'var(--color-border)' }} />
        <svg width="20" height="20" viewBox="0 0 40 40" fill="none"><rect width="40" height="40" rx="10" fill="#1A56DB"/><path d="M9 11h8.5C21.09 11 24 13.91 24 17.5v5C24 26.09 21.09 29 17.5 29H9V11z" stroke="white" strokeWidth="2" fill="none" strokeLinejoin="round"/></svg>
        <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--color-text-primary)' }}>{run?.topic}</span>
        <div style={{ flex: 1 }} />
        <Button variant="ghost" size="sm" onClick={handleRegenerate}>Regenerate</Button>
        <div style={{ position: 'relative' }}>
          <Button variant="secondary" size="sm" onClick={() => setExportOpen(p => !p)} loading={exporting}>
            Export PDF ▾
          </Button>
          {exportOpen && (
            <div style={{ position: 'absolute', right: 0, top: '100%', marginTop: 4, background: 'var(--color-surface)', border: '1px solid var(--color-border)', borderRadius: 'var(--radius-md)', boxShadow: 'var(--shadow-md)', zIndex: 10, minWidth: 180 }}>
              {[{ key: 'student' as const, label: 'Student Version' }, { key: 'answer_key' as const, label: 'Answer Key' }].map(opt => (
                <button key={opt.key} onClick={() => handleExport(opt.key)} style={{ display: 'block', width: '100%', padding: '9px 14px', fontSize: 13, color: 'var(--color-text-primary)', background: 'none', border: 'none', cursor: 'pointer', fontFamily: 'inherit', textAlign: 'left' }}>
                  {opt.label}
                </button>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Body */}
      <div style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>

        {/* Comparison sidebar */}
        <div style={{ width: 'var(--width-sidebar)', background: 'var(--color-surface)', borderRight: '1px solid var(--color-border)', overflowY: 'auto', padding: '12px 0', flexShrink: 0 }}>
          <div style={{ padding: '4px 16px 10px', fontSize: 11, fontWeight: 600, letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--color-text-tertiary)' }}>
            Other Variants
          </div>
          {sidebarAssessments.map(a => (
            <button key={a.id} onClick={() => selectAssessment(a.id)} style={{
              display: 'block', width: '100%', padding: '10px 16px', background: 'none', border: 'none',
              cursor: 'pointer', fontFamily: 'inherit', textAlign: 'left',
              borderLeft: `2px solid ${selectedId === a.id ? 'var(--color-accent)' : 'transparent'}`,
              background: selectedId === a.id ? 'var(--color-accent-subtle)' : 'none',
            }}>
              <div style={{ fontSize: 12, fontWeight: 500, color: 'var(--color-text-primary)', marginBottom: 2 }}>
                {frameworkLabel[a.framework]} · Set {a.control_set_id}
              </div>
              <Badge variant="success" dot size="sm">Complete</Badge>
            </button>
          ))}
        </div>

        {/* Primary panel */}
        <div style={{ flex: 1, overflowY: 'auto', padding: '24px 32px', background: 'var(--color-bg-secondary)' }}>
          {selected ? (
            <>
              <div style={{ marginBottom: 20 }}>
                <div style={{ fontSize: 16, fontWeight: 600, color: 'var(--color-text-primary)', letterSpacing: '-0.02em', marginBottom: 6 }}>
                  {frameworkLabel[selected.framework]} Framework
                </div>
                <Tabs
                  tabs={[
                    { id: 'questions', label: 'Questions' },
                    { id: 'answer-key', label: 'Answer Key' },
                    { id: 'student', label: 'Student View' },
                  ]}
                  activeTab={activeTab}
                  onTabChange={setActiveTab}
                  variant="underline"
                />
              </div>

              {selected.questions ? (
                <div>
                  {selected.questions.map(q =>
                    q.type === 'mcq'
                      ? <MCQQuestion key={q.id} q={q} />
                      : <LongAnswerQuestion key={q.id} q={q} />
                  )}
                </div>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                  {[100, 80, 90, 70].map((w, i) => (
                    <div key={i} className="db-skeleton" style={{ height: 60, width: `${w}%` }} />
                  ))}
                </div>
              )}
            </>
          ) : (
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '60%', color: 'var(--color-text-tertiary)', fontSize: 14 }}>
              Waiting for first assessment to complete…
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
```

---

## Task 12: Smoke Test Frontend

- [ ] **Step 1: Run type check**

```powershell
npx tsc --noEmit
```

Expected: no errors. Fix any type errors before continuing.

- [ ] **Step 2: Start dev server**

```powershell
npm run dev
```

Expected: Vite starts on `http://localhost:5173`. Open the URL — Input Panel page should render with topbar, sidebar, and control set grid using the design system tokens (DM Sans font, blue accent colors).

- [ ] **Step 3: Verify navigation stubs**

With dev server running, navigate to:
- `http://localhost:5173/` → Input Panel renders ✓
- `http://localhost:5173/runs/1/progress` → Progress page renders (empty grid, no assessments yet) ✓
- `http://localhost:5173/runs/1/viewer` → Viewer renders (sidebar empty, "Waiting" message in primary panel) ✓

Expected: all three pages load without console errors.

---

## Task 13: Cleanup — Remove Static Prototype Directories

- [ ] **Step 1: Remove frontend-claude_design**

```powershell
Remove-Item -Recurse -Force "C:\Users\yeekw\Documents\Blueprint\frontend-claude_design"
```

Expected: directory gone, no errors

- [ ] **Step 2: Remove frontend-claude_design-copy**

```powershell
Remove-Item -Recurse -Force "C:\Users\yeekw\Documents\Blueprint\frontend-claude_design-copy" -ErrorAction SilentlyContinue
```

Expected: directory gone (or "no such path" if it doesn't exist — either is fine)

- [ ] **Step 3: Verify Blueprint directory**

```powershell
Get-ChildItem "C:\Users\yeekw\Documents\Blueprint" | Select-Object Name
```

Expected: `frontend-claude_design` and `frontend-claude_design-copy` are NOT in the listing. `frontend` and `backend` remain.

---
