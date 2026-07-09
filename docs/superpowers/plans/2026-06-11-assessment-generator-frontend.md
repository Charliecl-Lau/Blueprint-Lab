# Assessment Generator — Frontend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the React frontend that lets instructors configure assessment runs, watch 12 parallel assessments generate in real-time via SSE, and interactively view, compare, and export the results.

**Architecture:** Vite + React 18 + TypeScript. Zustand manages all application state (run config, SSE progress, loaded assessments). The backend's `POST /runs` returns an SSE stream over fetch (not EventSource, because it's a POST), so a custom `useSSEPost` hook handles the stream. Claude Design handles styling — this plan focuses on component structure, data flow, and interaction logic.

**Tech Stack:** React 18, TypeScript, Vite, Zustand, fetch API (native), Vitest, React Testing Library

> **Note on Claude Design:** Styling and visual design are handled by Claude Design. This plan specifies component structure, props, and interaction logic. Do not block tasks on styling — apply minimal placeholder classes and let Claude Design handle the visual layer.

---

## File Map

| File | Responsibility |
|---|---|
| `frontend/src/types/api.ts` | All TypeScript interfaces matching API response shapes |
| `frontend/src/api/client.ts` | Typed fetch wrappers for all API routes |
| `frontend/src/hooks/useSSEPost.ts` | Hook: POST to /runs, reads SSE stream, dispatches events to store |
| `frontend/src/store/useRunStore.ts` | Zustand store: run config state, SSE progress map, loaded assessments, UI state |
| `frontend/src/components/InputPanel/InputPanel.tsx` | Run configuration form (topic, expectations, counts, frameworks) |
| `frontend/src/components/InputPanel/ControlSetRow.tsx` | Single row for one control set (personality, lengths, action word count) |
| `frontend/src/components/ProgressGrid/ProgressGrid.tsx` | 12-cell grid showing per-assessment stage progress |
| `frontend/src/components/AssessmentViewer/questions/MCQQuestion.tsx` | MCQ question with radio options and model answer toggle |
| `frontend/src/components/AssessmentViewer/questions/LongAnswerQuestion.tsx` | Long answer question with textarea and word count guide |
| `frontend/src/components/AssessmentViewer/ComparisonSidebar.tsx` | 11-card collapsed list; clicking swaps primary panel |
| `frontend/src/components/AssessmentViewer/PrimaryPanel.tsx` | Full assessment rendering: metadata header + all questions |
| `frontend/src/components/AssessmentViewer/Toolbar.tsx` | Pin, Regenerate, Export PDF dropdown |
| `frontend/src/components/AssessmentViewer/AssessmentViewer.tsx` | Two-column layout: sidebar + primary panel |
| `frontend/src/App.tsx` | Top-level: shows InputPanel → ProgressGrid → AssessmentViewer in sequence |

---

## Task 1: Project Setup

**Files:**
- Create: `frontend/` (Vite project)
- Create: `frontend/src/types/api.ts`

- [ ] **Step 1: Scaffold the Vite project**

Run from repo root:
```bash
npm create vite@latest frontend -- --template react-ts
cd frontend
npm install
```

Expected: `frontend/` created with `src/App.tsx`, `src/main.tsx`, `vite.config.ts`.

- [ ] **Step 2: Install additional dependencies**

```bash
cd frontend
npm install zustand
npm install --save-dev vitest @testing-library/react @testing-library/user-event @testing-library/jest-dom jsdom
```

- [ ] **Step 3: Configure Vitest in `frontend/vite.config.ts`**

```typescript
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test-setup.ts"],
  },
  server: {
    proxy: {
      "/runs": "http://localhost:8000",
      "/assessments": "http://localhost:8000",
    },
  },
});
```

- [ ] **Step 4: Create `frontend/src/test-setup.ts`**

```typescript
import "@testing-library/jest-dom";
```

- [ ] **Step 5: Add test script to `frontend/package.json`**

In the `"scripts"` section, add:
```json
"test": "vitest"
```

- [ ] **Step 6: Write a smoke test to verify the setup works**

Create `frontend/src/App.test.tsx`:

```typescript
import { render, screen } from "@testing-library/react";
import App from "./App";

test("renders without crashing", () => {
  render(<App />);
  expect(document.body).toBeTruthy();
});
```

Replace `frontend/src/App.tsx` with a minimal stub:
```typescript
export default function App() {
  return <div>Assessment Generator</div>;
}
```

- [ ] **Step 7: Run the test**

```bash
cd frontend && npm test
```

Expected: `renders without crashing PASS`

- [ ] **Step 8: Commit**

```bash
git add frontend/
git commit -m "feat: scaffold React + Vite + TypeScript frontend with Vitest"
```

---

## Task 2: TypeScript Types

**Files:**
- Create: `frontend/src/types/api.ts`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/types/api.test.ts`:

```typescript
import type { Run, Assessment, Question, MCQOption } from "./api";

test("type definitions compile", () => {
  const option: MCQOption = { id: 1, body: "Synchronize", is_correct: true };
  const question: Question = {
    id: 1,
    type: "mcq",
    body: "What is SYN?",
    order: 0,
    options: [option],
    model_answer: null,
  };
  const assessment: Assessment = {
    id: 1,
    framework: "forge",
    control_set_id: 1,
    status: "complete",
    questions: [question],
  };
  expect(option.is_correct).toBe(true);
  expect(assessment.framework).toBe("forge");
});
```

- [ ] **Step 2: Run to verify it fails**

```bash
cd frontend && npm test -- api.test.ts
```
Expected: `Cannot find module './api'` error.

- [ ] **Step 3: Create `frontend/src/types/api.ts`**

```typescript
export type AssessmentStatus =
  | "pending"
  | "prompting"
  | "planning"
  | "validating"
  | "generating"
  | "complete"
  | "error";

export type Framework = "forge" | "openai" | "risen";

export type QuestionType = "mcq" | "long_answer";

export interface MCQOption {
  id: number;
  body: string;
  is_correct: boolean;
}

export interface ModelAnswer {
  body: string;
}

export interface Question {
  id: number;
  type: QuestionType;
  body: string;
  order: number;
  options: MCQOption[];
  model_answer: ModelAnswer | null;
}

export interface Assessment {
  id: number;
  framework: Framework;
  control_set_id: number;
  status: AssessmentStatus;
  questions: Question[];
}

export interface ControlSet {
  id: number;
  personality: string;
  prompt_length: string;
  result_length: string;
  action_word_count: number;
}

export interface Run {
  id: number;
  topic: string;
  expectations: string;
  mcq_count: number;
  long_answer_count: number;
  created_at: string;
  control_sets: ControlSet[];
  assessments: Array<{ id: number; framework: Framework; control_set_id: number; status: AssessmentStatus }>;
}

export interface SSEProgressEvent {
  assessment_id: number;
  framework: Framework;
  control_set: number;
  stage: AssessmentStatus;
}

export interface SSERunStartedEvent {
  run_id: number;
  type: "run_started";
}

// API request types

export interface ControlSetCreate {
  personality: string;
  prompt_length: string;
  result_length: string;
  action_word_count: number;
}

export interface RunCreate {
  topic: string;
  expectations: string;
  mcq_count: number;
  long_answer_count: number;
  control_sets: ControlSetCreate[];
  frameworks: Framework[];
}
```

- [ ] **Step 4: Run the test**

```bash
cd frontend && npm test -- api.test.ts
```

Expected: `PASS`

- [ ] **Step 5: Commit**

```bash
git add frontend/src/types/
git commit -m "feat: add TypeScript API type definitions"
```

---

## Task 3: API Client

**Files:**
- Create: `frontend/src/api/client.ts`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/api/client.test.ts`:

```typescript
import { describe, it, expect, vi, beforeEach } from "vitest";
import { getAssessment, regenerateAssessment } from "./client";

describe("API client", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
  });

  it("getAssessment calls correct URL", async () => {
    const mockAssessment = { id: 1, framework: "forge", status: "complete", questions: [], control_set_id: 1 };
    (fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      ok: true,
      json: async () => mockAssessment,
    });
    const result = await getAssessment(1);
    expect(fetch).toHaveBeenCalledWith("/assessments/1");
    expect(result.id).toBe(1);
  });

  it("regenerateAssessment calls correct URL with POST", async () => {
    (fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      ok: true,
      json: async () => ({ assessment_id: 1, status: "pending" }),
    });
    await regenerateAssessment(1);
    expect(fetch).toHaveBeenCalledWith("/assessments/1/regenerate", expect.objectContaining({ method: "POST" }));
  });

  it("throws on non-ok response", async () => {
    (fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      ok: false,
      status: 404,
      json: async () => ({ detail: "Not found" }),
    });
    await expect(getAssessment(999)).rejects.toThrow("404");
  });
});
```

- [ ] **Step 2: Run to verify it fails**

```bash
cd frontend && npm test -- client.test.ts
```
Expected: `Cannot find module './client'`.

- [ ] **Step 3: Create `frontend/src/api/client.ts`**

```typescript
import type { Assessment, RunCreate } from "../types/api";

async function apiFetch<T>(url: string, options?: RequestInit): Promise<T> {
  const response = await fetch(url, options);
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(`${response.status}: ${error.detail ?? "Request failed"}`);
  }
  return response.json() as Promise<T>;
}

export async function getAssessment(id: number): Promise<Assessment> {
  return apiFetch<Assessment>(`/assessments/${id}`);
}

export async function regenerateAssessment(id: number): Promise<{ assessment_id: number; status: string }> {
  return apiFetch(`/assessments/${id}/regenerate`, { method: "POST" });
}

export async function exportPdf(id: number, variant: "student" | "answer_key"): Promise<Blob> {
  const response = await fetch(`/assessments/${id}/export-pdf?variant=${variant}`, { method: "POST" });
  if (!response.ok) throw new Error(`${response.status}: Export failed`);
  return response.blob();
}

export function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

// Returns a ReadableStream reader for the SSE POST /runs response.
// The caller is responsible for reading events from the stream.
export async function createRun(payload: RunCreate): Promise<ReadableStreamDefaultReader<Uint8Array>> {
  const response = await fetch("/runs", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok || !response.body) {
    throw new Error(`${response.status}: Failed to start run`);
  }
  return response.body.getReader();
}
```

- [ ] **Step 4: Run the tests**

```bash
cd frontend && npm test -- client.test.ts
```

Expected: All 3 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/api/
git commit -m "feat: add typed API client with fetch wrappers"
```

---

## Task 4: Zustand Store

**Files:**
- Create: `frontend/src/store/useRunStore.ts`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/store/useRunStore.test.ts`:

```typescript
import { describe, it, expect, beforeEach } from "vitest";
import { act } from "@testing-library/react";
import { useRunStore } from "./useRunStore";
import type { Assessment } from "../types/api";

describe("useRunStore", () => {
  beforeEach(() => {
    useRunStore.setState(useRunStore.getInitialState());
  });

  it("starts in 'input' phase", () => {
    expect(useRunStore.getState().phase).toBe("input");
  });

  it("setPhase transitions correctly", () => {
    act(() => useRunStore.getState().setPhase("progress"));
    expect(useRunStore.getState().phase).toBe("progress");
  });

  it("updateAssessmentProgress stores stage by assessment id", () => {
    act(() => {
      useRunStore.getState().updateAssessmentProgress(3, "planning");
    });
    expect(useRunStore.getState().progressMap[3]).toBe("planning");
  });

  it("loadAssessment stores assessment and sets primary", () => {
    const mockAssessment: Assessment = {
      id: 5,
      framework: "forge",
      control_set_id: 1,
      status: "complete",
      questions: [],
    };
    act(() => {
      useRunStore.getState().loadAssessment(mockAssessment);
    });
    expect(useRunStore.getState().assessments[5]).toEqual(mockAssessment);
    expect(useRunStore.getState().primaryAssessmentId).toBe(5);
  });

  it("setPrimaryAssessment changes the displayed assessment", () => {
    act(() => useRunStore.getState().setPrimaryAssessmentId(7));
    expect(useRunStore.getState().primaryAssessmentId).toBe(7);
  });
});
```

- [ ] **Step 2: Run to verify it fails**

```bash
cd frontend && npm test -- useRunStore.test.ts
```
Expected: `Cannot find module './useRunStore'`.

- [ ] **Step 3: Create `frontend/src/store/useRunStore.ts`**

```typescript
import { create } from "zustand";
import type { Assessment, AssessmentStatus, RunCreate } from "../types/api";

type Phase = "input" | "progress" | "viewer";

interface RunStore {
  phase: Phase;
  runId: number | null;
  runConfig: RunCreate | null;

  // keyed by assessment_id
  progressMap: Record<number, AssessmentStatus>;
  assessments: Record<number, Assessment>;
  primaryAssessmentId: number | null;

  // UI state for viewer
  pinnedAssessmentIds: number[];

  setPhase: (phase: Phase) => void;
  setRunId: (id: number) => void;
  setRunConfig: (config: RunCreate) => void;
  updateAssessmentProgress: (assessmentId: number, stage: AssessmentStatus) => void;
  loadAssessment: (assessment: Assessment) => void;
  setPrimaryAssessmentId: (id: number) => void;
  togglePin: (id: number) => void;
  reset: () => void;
}

const initialState = {
  phase: "input" as Phase,
  runId: null,
  runConfig: null,
  progressMap: {},
  assessments: {},
  primaryAssessmentId: null,
  pinnedAssessmentIds: [],
};

export const useRunStore = create<RunStore>()((set) => ({
  ...initialState,

  setPhase: (phase) => set({ phase }),
  setRunId: (id) => set({ runId: id }),
  setRunConfig: (config) => set({ runConfig: config }),

  updateAssessmentProgress: (assessmentId, stage) =>
    set((state) => ({
      progressMap: { ...state.progressMap, [assessmentId]: stage },
    })),

  loadAssessment: (assessment) =>
    set((state) => ({
      assessments: { ...state.assessments, [assessment.id]: assessment },
      primaryAssessmentId: state.primaryAssessmentId ?? assessment.id,
    })),

  setPrimaryAssessmentId: (id) => set({ primaryAssessmentId: id }),

  togglePin: (id) =>
    set((state) => ({
      pinnedAssessmentIds: state.pinnedAssessmentIds.includes(id)
        ? state.pinnedAssessmentIds.filter((pid) => pid !== id)
        : [...state.pinnedAssessmentIds, id],
    })),

  reset: () => set(initialState),
}));

// Expose initial state for test resets
(useRunStore as unknown as { getInitialState: () => typeof initialState }).getInitialState =
  () => initialState;
```

- [ ] **Step 4: Run the tests**

```bash
cd frontend && npm test -- useRunStore.test.ts
```

Expected: All 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/store/
git commit -m "feat: add Zustand store for run state, SSE progress map, and assessment viewer state"
```

---

## Task 5: SSE Post Hook

**Files:**
- Create: `frontend/src/hooks/useSSEPost.ts`

This hook calls `createRun`, reads the SSE stream line-by-line, parses JSON events, and dispatches them to the store. It handles the `run_started` event (to extract `run_id`) and `stage` events (to update the progress map).

- [ ] **Step 1: Write the failing test**

Create `frontend/src/hooks/useSSEPost.test.ts`:

```typescript
import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, act, waitFor } from "@testing-library/react";
import { useSSEPost } from "./useSSEPost";
import { useRunStore } from "../store/useRunStore";
import * as clientModule from "../api/client";

function encodeSSEStream(events: string[]): ReadableStreamDefaultReader<Uint8Array> {
  const encoder = new TextEncoder();
  const sseText = events.map((e) => `data: ${e}\n\n`).join("");
  const buffer = encoder.encode(sseText);
  let offset = 0;
  return {
    read: vi.fn().mockImplementation(async () => {
      if (offset >= buffer.length) return { done: true, value: undefined };
      const chunk = buffer.slice(offset, offset + 100);
      offset += 100;
      return { done: false, value: chunk };
    }),
    cancel: vi.fn(),
    closed: Promise.resolve(undefined),
    releaseLock: vi.fn(),
  } as unknown as ReadableStreamDefaultReader<Uint8Array>;
}

describe("useSSEPost", () => {
  beforeEach(() => {
    useRunStore.setState({ progressMap: {}, runId: null, phase: "input" });
    vi.restoreAllMocks();
  });

  it("parses run_started event and sets runId in store", async () => {
    const events = [
      JSON.stringify({ run_id: 42, type: "run_started" }),
      JSON.stringify({ assessment_id: 1, framework: "forge", control_set: 1, stage: "complete" }),
    ];
    vi.spyOn(clientModule, "createRun").mockResolvedValueOnce(encodeSSEStream(events));

    const { result } = renderHook(() => useSSEPost());
    await act(async () => {
      await result.current.startRun({
        topic: "TCP",
        expectations: "test",
        mcq_count: 2,
        long_answer_count: 1,
        control_sets: [],
        frameworks: ["forge"],
      });
    });

    await waitFor(() => {
      expect(useRunStore.getState().runId).toBe(42);
    });
  });

  it("dispatches progress events to the store", async () => {
    const events = [
      JSON.stringify({ run_id: 10, type: "run_started" }),
      JSON.stringify({ assessment_id: 5, framework: "openai", control_set: 2, stage: "planning" }),
    ];
    vi.spyOn(clientModule, "createRun").mockResolvedValueOnce(encodeSSEStream(events));

    const { result } = renderHook(() => useSSEPost());
    await act(async () => {
      await result.current.startRun({ topic: "T", expectations: "E", mcq_count: 2, long_answer_count: 1, control_sets: [], frameworks: ["openai"] });
    });

    await waitFor(() => {
      expect(useRunStore.getState().progressMap[5]).toBe("planning");
    });
  });
});
```

- [ ] **Step 2: Run to verify it fails**

```bash
cd frontend && npm test -- useSSEPost.test.ts
```
Expected: `Cannot find module './useSSEPost'`.

- [ ] **Step 3: Create `frontend/src/hooks/useSSEPost.ts`**

```typescript
import { useCallback, useRef } from "react";
import { createRun } from "../api/client";
import { useRunStore } from "../store/useRunStore";
import type { RunCreate, SSEProgressEvent, SSERunStartedEvent } from "../types/api";

export function useSSEPost() {
  const { setRunId, setPhase, updateAssessmentProgress } = useRunStore();
  const readerRef = useRef<ReadableStreamDefaultReader<Uint8Array> | null>(null);

  const startRun = useCallback(async (payload: RunCreate) => {
    setPhase("progress");
    const reader = await createRun(payload);
    readerRef.current = reader;

    const decoder = new TextDecoder();
    let buffer = "";

    const processLine = (line: string) => {
      if (!line.startsWith("data: ")) return;
      const jsonStr = line.slice(6).trim();
      if (!jsonStr) return;
      try {
        const event = JSON.parse(jsonStr) as SSEProgressEvent | SSERunStartedEvent;
        if ("type" in event && event.type === "run_started") {
          setRunId(event.run_id);
        } else {
          const progressEvent = event as SSEProgressEvent;
          updateAssessmentProgress(progressEvent.assessment_id, progressEvent.stage);
        }
      } catch {
        // Ignore malformed SSE lines
      }
    };

    const pump = async () => {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() ?? "";
        lines.forEach(processLine);
      }
    };

    await pump();
  }, [setRunId, setPhase, updateAssessmentProgress]);

  const cancel = useCallback(() => {
    readerRef.current?.cancel();
  }, []);

  return { startRun, cancel };
}
```

- [ ] **Step 4: Run the tests**

```bash
cd frontend && npm test -- useSSEPost.test.ts
```

Expected: Both tests PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/hooks/
git commit -m "feat: add useSSEPost hook for reading SSE stream from POST /runs"
```

---

## Task 6: Input Panel

**Files:**
- Create: `frontend/src/components/InputPanel/ControlSetRow.tsx`
- Create: `frontend/src/components/InputPanel/InputPanel.tsx`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/components/InputPanel/InputPanel.test.tsx`:

```typescript
import { render, screen, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { InputPanel } from "./InputPanel";

const mockOnSubmit = vi.fn();

const defaultProps = {
  onSubmit: mockOnSubmit,
  isSubmitting: false,
};

describe("InputPanel", () => {
  beforeEach(() => mockOnSubmit.mockClear());

  it("renders topic and expectations inputs", () => {
    render(<InputPanel {...defaultProps} />);
    expect(screen.getByLabelText(/topic/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/expectations/i)).toBeInTheDocument();
  });

  it("renders 4 control set rows", () => {
    render(<InputPanel {...defaultProps} />);
    const personalities = screen.getAllByLabelText(/personality/i);
    expect(personalities).toHaveLength(4);
  });

  it("renders 3 framework checkboxes all checked by default", () => {
    render(<InputPanel {...defaultProps} />);
    const checkboxes = screen.getAllByRole("checkbox");
    expect(checkboxes).toHaveLength(3);
    checkboxes.forEach((cb) => expect(cb).toBeChecked());
  });

  it("calls onSubmit with form data when submitted", async () => {
    const user = userEvent.setup();
    render(<InputPanel {...defaultProps} />);

    await user.clear(screen.getByLabelText(/topic/i));
    await user.type(screen.getByLabelText(/topic/i), "TCP/IP Networking");
    await user.clear(screen.getByLabelText(/expectations/i));
    await user.type(screen.getByLabelText(/expectations/i), "Test handshake");

    await user.click(screen.getByRole("button", { name: /generate/i }));

    expect(mockOnSubmit).toHaveBeenCalledOnce();
    const payload = mockOnSubmit.mock.calls[0][0];
    expect(payload.topic).toBe("TCP/IP Networking");
    expect(payload.control_sets).toHaveLength(4);
    expect(payload.frameworks).toHaveLength(3);
  });

  it("disables submit when isSubmitting is true", () => {
    render(<InputPanel {...defaultProps} isSubmitting={true} />);
    expect(screen.getByRole("button", { name: /generate/i })).toBeDisabled();
  });
});
```

- [ ] **Step 2: Run to verify it fails**

```bash
cd frontend && npm test -- InputPanel.test.tsx
```
Expected: `Cannot find module './InputPanel'`.

- [ ] **Step 3: Create `frontend/src/components/InputPanel/ControlSetRow.tsx`**

```typescript
import type { ControlSetCreate } from "../../types/api";

interface ControlSetRowProps {
  index: number;
  value: ControlSetCreate;
  onChange: (index: number, updated: ControlSetCreate) => void;
}

const PERSONALITIES = ["formal", "socratic", "encouraging", "challenging"] as const;
const LENGTHS = ["short", "medium", "long"] as const;

export function ControlSetRow({ index, value, onChange }: ControlSetRowProps) {
  const update = (field: keyof ControlSetCreate, fieldValue: string | number) =>
    onChange(index, { ...value, [field]: fieldValue });

  return (
    <div className="control-set-row">
      <span className="row-label">Set {index + 1}</span>

      <label htmlFor={`personality-${index}`}>Personality</label>
      <select
        id={`personality-${index}`}
        value={value.personality}
        onChange={(e) => update("personality", e.target.value)}
      >
        {PERSONALITIES.map((p) => (
          <option key={p} value={p}>{p.charAt(0).toUpperCase() + p.slice(1)}</option>
        ))}
      </select>

      <label htmlFor={`prompt-length-${index}`}>Prompt Length</label>
      <select
        id={`prompt-length-${index}`}
        value={value.prompt_length}
        onChange={(e) => update("prompt_length", e.target.value)}
      >
        {LENGTHS.map((l) => (
          <option key={l} value={l}>{l.charAt(0).toUpperCase() + l.slice(1)}</option>
        ))}
      </select>

      <label htmlFor={`result-length-${index}`}>Result Length</label>
      <select
        id={`result-length-${index}`}
        value={value.result_length}
        onChange={(e) => update("result_length", e.target.value)}
      >
        {LENGTHS.map((l) => (
          <option key={l} value={l}>{l.charAt(0).toUpperCase() + l.slice(1)}</option>
        ))}
      </select>

      <label htmlFor={`action-word-count-${index}`}>Action Words: {value.action_word_count}</label>
      <input
        id={`action-word-count-${index}`}
        type="range"
        min={1}
        max={5}
        value={value.action_word_count}
        onChange={(e) => update("action_word_count", parseInt(e.target.value))}
      />
    </div>
  );
}
```

- [ ] **Step 4: Create `frontend/src/components/InputPanel/InputPanel.tsx`**

```typescript
import { useState } from "react";
import type { RunCreate, ControlSetCreate, Framework } from "../../types/api";
import { ControlSetRow } from "./ControlSetRow";

interface InputPanelProps {
  onSubmit: (payload: RunCreate) => void;
  isSubmitting: boolean;
}

const DEFAULT_CONTROL_SETS: ControlSetCreate[] = [
  { personality: "formal", prompt_length: "short", result_length: "short", action_word_count: 2 },
  { personality: "socratic", prompt_length: "medium", result_length: "medium", action_word_count: 3 },
  { personality: "encouraging", prompt_length: "long", result_length: "medium", action_word_count: 3 },
  { personality: "challenging", prompt_length: "medium", result_length: "long", action_word_count: 4 },
];

const ALL_FRAMEWORKS: Framework[] = ["forge", "openai", "risen"];

export function InputPanel({ onSubmit, isSubmitting }: InputPanelProps) {
  const [topic, setTopic] = useState("");
  const [expectations, setExpectations] = useState("");
  const [mcqCount, setMcqCount] = useState(10);
  const [longAnswerCount, setLongAnswerCount] = useState(3);
  const [controlSets, setControlSets] = useState<ControlSetCreate[]>(DEFAULT_CONTROL_SETS);
  const [frameworks, setFrameworks] = useState<Framework[]>([...ALL_FRAMEWORKS]);

  const updateControlSet = (index: number, updated: ControlSetCreate) => {
    setControlSets((prev) => prev.map((cs, i) => (i === index ? updated : cs)));
  };

  const toggleFramework = (fw: Framework) => {
    setFrameworks((prev) =>
      prev.includes(fw) ? prev.filter((f) => f !== fw) : [...prev, fw]
    );
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onSubmit({
      topic,
      expectations,
      mcq_count: mcqCount,
      long_answer_count: longAnswerCount,
      control_sets: controlSets,
      frameworks,
    });
  };

  return (
    <form onSubmit={handleSubmit} className="input-panel">
      <div className="field">
        <label htmlFor="topic">Topic / Chapter</label>
        <input
          id="topic"
          type="text"
          value={topic}
          onChange={(e) => setTopic(e.target.value)}
          placeholder="e.g. TCP/IP Networking, Chapter 5"
          required
        />
      </div>

      <div className="field">
        <label htmlFor="expectations">Expectations</label>
        <textarea
          id="expectations"
          value={expectations}
          onChange={(e) => setExpectations(e.target.value)}
          placeholder="What should the questions test?"
          rows={3}
          required
        />
      </div>

      <div className="counts">
        <div className="field">
          <label htmlFor="mcq-count">MCQ Count</label>
          <input
            id="mcq-count"
            type="number"
            min={1}
            value={mcqCount}
            onChange={(e) => setMcqCount(parseInt(e.target.value))}
          />
        </div>
        <div className="field">
          <label htmlFor="long-answer-count">Long Answer Count</label>
          <input
            id="long-answer-count"
            type="number"
            min={1}
            value={longAnswerCount}
            onChange={(e) => setLongAnswerCount(parseInt(e.target.value))}
          />
        </div>
      </div>

      <fieldset className="frameworks">
        <legend>Frameworks</legend>
        {ALL_FRAMEWORKS.map((fw) => (
          <label key={fw} className="framework-checkbox">
            <input
              type="checkbox"
              checked={frameworks.includes(fw)}
              onChange={() => toggleFramework(fw)}
            />
            {fw.toUpperCase()}
          </label>
        ))}
      </fieldset>

      <div className="control-sets">
        {controlSets.map((cs, i) => (
          <ControlSetRow key={i} index={i} value={cs} onChange={updateControlSet} />
        ))}
      </div>

      <button type="submit" disabled={isSubmitting || frameworks.length === 0}>
        {isSubmitting ? "Generating..." : "Generate Assessments"}
      </button>
    </form>
  );
}
```

- [ ] **Step 5: Run the tests**

```bash
cd frontend && npm test -- InputPanel.test.tsx
```

Expected: All 5 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/InputPanel/
git commit -m "feat: add InputPanel form with ControlSetRow for run configuration"
```

---

## Task 7: Progress Grid

**Files:**
- Create: `frontend/src/components/ProgressGrid/ProgressGrid.tsx`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/components/ProgressGrid/ProgressGrid.test.tsx`:

```typescript
import { render, screen } from "@testing-library/react";
import { ProgressGrid } from "./ProgressGrid";
import type { AssessmentStatus } from "../../types/api";

const STAGE_ORDER: AssessmentStatus[] = ["prompting", "planning", "validating", "generating", "complete"];

const mockSummaries = [
  { id: 1, framework: "forge" as const, control_set_id: 1, status: "complete" as AssessmentStatus },
  { id: 2, framework: "forge" as const, control_set_id: 2, status: "generating" as AssessmentStatus },
  { id: 3, framework: "openai" as const, control_set_id: 1, status: "planning" as AssessmentStatus },
];

describe("ProgressGrid", () => {
  it("renders one row per assessment", () => {
    render(<ProgressGrid assessments={mockSummaries} progressMap={{}} />);
    const rows = screen.getAllByRole("row");
    expect(rows).toHaveLength(mockSummaries.length);
  });

  it("shows framework and control set in each row", () => {
    render(<ProgressGrid assessments={mockSummaries} progressMap={{}} />);
    expect(screen.getByText(/forge/i)).toBeInTheDocument();
    expect(screen.getByText(/openai/i)).toBeInTheDocument();
  });

  it("shows complete status for assessment 1", () => {
    render(<ProgressGrid assessments={mockSummaries} progressMap={{ 1: "complete" }} />);
    const row = screen.getByTestId("progress-row-1");
    expect(row).toHaveAttribute("data-status", "complete");
  });

  it("uses progressMap stage over initial status when available", () => {
    render(
      <ProgressGrid
        assessments={[{ id: 1, framework: "forge", control_set_id: 1, status: "pending" }]}
        progressMap={{ 1: "generating" }}
      />
    );
    const row = screen.getByTestId("progress-row-1");
    expect(row).toHaveAttribute("data-status", "generating");
  });
});
```

- [ ] **Step 2: Run to verify it fails**

```bash
cd frontend && npm test -- ProgressGrid.test.tsx
```
Expected: `Cannot find module './ProgressGrid'`.

- [ ] **Step 3: Create `frontend/src/components/ProgressGrid/ProgressGrid.tsx`**

```typescript
import type { AssessmentStatus, Framework } from "../../types/api";

interface AssessmentSummary {
  id: number;
  framework: Framework;
  control_set_id: number;
  status: AssessmentStatus;
}

interface ProgressGridProps {
  assessments: AssessmentSummary[];
  progressMap: Record<number, AssessmentStatus>;
}

const STAGES: AssessmentStatus[] = ["prompting", "planning", "validating", "generating", "complete"];

const STAGE_LABELS: Record<AssessmentStatus, string> = {
  pending: "–",
  prompting: "Prompt",
  planning: "Plan",
  validating: "Validate",
  generating: "Generate",
  complete: "✓",
  error: "✗",
};

function StageCell({ stage, currentStage }: { stage: AssessmentStatus; currentStage: AssessmentStatus }) {
  const stageIndex = STAGES.indexOf(stage);
  const currentIndex = STAGES.indexOf(currentStage);

  let state: "done" | "active" | "pending" = "pending";
  if (currentStage === "complete" || stageIndex < currentIndex) state = "done";
  else if (stage === currentStage) state = "active";

  return (
    <span className={`stage-cell stage-${state}`} aria-label={`${stage}: ${state}`}>
      {state === "done" ? "✓" : state === "active" ? "⟳" : "–"}
      {" "}
      {STAGE_LABELS[stage]}
    </span>
  );
}

export function ProgressGrid({ assessments, progressMap }: ProgressGridProps) {
  return (
    <div className="progress-grid">
      {assessments.map((a) => {
        const currentStage = progressMap[a.id] ?? a.status;
        return (
          <div
            key={a.id}
            role="row"
            data-testid={`progress-row-${a.id}`}
            data-status={currentStage}
            className={`progress-row status-${currentStage}`}
          >
            <span className="assessment-label">
              {a.framework.toUpperCase()} / Set {a.control_set_id}
            </span>
            {STAGES.map((stage) => (
              <StageCell key={stage} stage={stage} currentStage={currentStage} />
            ))}
          </div>
        );
      })}
    </div>
  );
}
```

- [ ] **Step 4: Run the tests**

```bash
cd frontend && npm test -- ProgressGrid.test.tsx
```

Expected: All 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/ProgressGrid/
git commit -m "feat: add ProgressGrid component showing per-assessment stage status"
```

---

## Task 8: Question Components

**Files:**
- Create: `frontend/src/components/AssessmentViewer/questions/MCQQuestion.tsx`
- Create: `frontend/src/components/AssessmentViewer/questions/LongAnswerQuestion.tsx`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/components/AssessmentViewer/questions/MCQQuestion.test.tsx`:

```typescript
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MCQQuestion } from "./MCQQuestion";

const mockQuestion = {
  id: 1,
  type: "mcq" as const,
  body: "What does SYN stand for?",
  order: 0,
  options: [
    { id: 1, body: "Synchronize", is_correct: true },
    { id: 2, body: "System", is_correct: false },
    { id: 3, body: "Signal", is_correct: false },
    { id: 4, body: "Send", is_correct: false },
  ],
  model_answer: null,
};

describe("MCQQuestion", () => {
  it("renders the question body", () => {
    render(<MCQQuestion question={mockQuestion} index={0} />);
    expect(screen.getByText(/What does SYN stand for/i)).toBeInTheDocument();
  });

  it("renders all 4 options as radio buttons", () => {
    render(<MCQQuestion question={mockQuestion} index={0} />);
    expect(screen.getAllByRole("radio")).toHaveLength(4);
  });

  it("does not show model answer by default", () => {
    render(<MCQQuestion question={mockQuestion} index={0} />);
    expect(screen.queryByText("Synchronize")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /show model answer/i })).toBeInTheDocument();
  });

  it("shows correct answer after clicking Show model answer", async () => {
    const user = userEvent.setup();
    render(<MCQQuestion question={mockQuestion} index={0} />);
    await user.click(screen.getByRole("button", { name: /show model answer/i }));
    expect(screen.getByText(/Synchronize/i)).toBeInTheDocument();
  });
});
```

Create `frontend/src/components/AssessmentViewer/questions/LongAnswerQuestion.test.tsx`:

```typescript
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { LongAnswerQuestion } from "./LongAnswerQuestion";

const mockQuestion = {
  id: 2,
  type: "long_answer" as const,
  body: "Explain TCP congestion control.",
  order: 1,
  options: [],
  model_answer: { body: "TCP uses slow start, congestion avoidance, fast retransmit, and fast recovery..." },
};

describe("LongAnswerQuestion", () => {
  it("renders the question body", () => {
    render(<LongAnswerQuestion question={mockQuestion} index={1} resultLength="medium" />);
    expect(screen.getByText(/Explain TCP congestion control/i)).toBeInTheDocument();
  });

  it("renders a textarea", () => {
    render(<LongAnswerQuestion question={mockQuestion} index={1} resultLength="medium" />);
    expect(screen.getByRole("textbox")).toBeInTheDocument();
  });

  it("shows word guide based on resultLength", () => {
    render(<LongAnswerQuestion question={mockQuestion} index={1} resultLength="medium" />);
    expect(screen.getByText(/~200 words/i)).toBeInTheDocument();
  });

  it("toggles model answer visibility", async () => {
    const user = userEvent.setup();
    render(<LongAnswerQuestion question={mockQuestion} index={1} resultLength="medium" />);
    expect(screen.queryByText(/slow start/i)).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /show model answer/i }));
    expect(screen.getByText(/slow start/i)).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run to verify they fail**

```bash
cd frontend && npm test -- questions/
```
Expected: Both `Cannot find module` errors.

- [ ] **Step 3: Create `frontend/src/components/AssessmentViewer/questions/MCQQuestion.tsx`**

```typescript
import { useState } from "react";
import type { Question } from "../../../types/api";

interface MCQQuestionProps {
  question: Question;
  index: number;
}

export function MCQQuestion({ question, index }: MCQQuestionProps) {
  const [selected, setSelected] = useState<number | null>(null);
  const [showAnswer, setShowAnswer] = useState(false);

  const correctOption = question.options.find((o) => o.is_correct);

  return (
    <div className="question mcq-question">
      <p className="question-body">
        <strong>Q{index + 1}.</strong> [MCQ] {question.body}
      </p>
      <div className="options" role="radiogroup" aria-label={`Question ${index + 1} options`}>
        {question.options.map((opt) => (
          <label
            key={opt.id}
            className={`option ${showAnswer && opt.is_correct ? "option-correct" : ""}`}
          >
            <input
              type="radio"
              name={`question-${question.id}`}
              value={opt.id}
              checked={selected === opt.id}
              onChange={() => setSelected(opt.id)}
            />
            {opt.body}
          </label>
        ))}
      </div>
      {showAnswer && correctOption && (
        <div className="model-answer">
          <strong>Correct answer:</strong> {correctOption.body}
        </div>
      )}
      <button
        className="toggle-answer"
        onClick={() => setShowAnswer((v) => !v)}
        type="button"
      >
        {showAnswer ? "Hide model answer" : "Show model answer"}
      </button>
    </div>
  );
}
```

- [ ] **Step 4: Create `frontend/src/components/AssessmentViewer/questions/LongAnswerQuestion.tsx`**

```typescript
import { useState } from "react";
import type { Question } from "../../../types/api";

interface LongAnswerQuestionProps {
  question: Question;
  index: number;
  resultLength: string;
}

const WORD_GUIDES: Record<string, string> = {
  short: "~100 words",
  medium: "~200 words",
  long: "~350 words",
};

export function LongAnswerQuestion({ question, index, resultLength }: LongAnswerQuestionProps) {
  const [showAnswer, setShowAnswer] = useState(false);

  return (
    <div className="question long-answer-question">
      <p className="question-body">
        <strong>Q{index + 1}.</strong> [Long Answer] {question.body}
      </p>
      <textarea
        className="answer-textarea"
        placeholder="Write your answer here..."
        rows={6}
        aria-label={`Answer for question ${index + 1}`}
      />
      <span className="word-guide">Word guide: {WORD_GUIDES[resultLength] ?? "~200 words"}</span>
      {showAnswer && question.model_answer && (
        <div className="model-answer">
          <strong>Model answer:</strong>
          <p>{question.model_answer.body}</p>
        </div>
      )}
      <button
        className="toggle-answer"
        onClick={() => setShowAnswer((v) => !v)}
        type="button"
      >
        {showAnswer ? "Hide model answer" : "Show model answer"}
      </button>
    </div>
  );
}
```

- [ ] **Step 5: Run the tests**

```bash
cd frontend && npm test -- questions/
```

Expected: All tests in both files PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/AssessmentViewer/questions/
git commit -m "feat: add MCQQuestion and LongAnswerQuestion components with model answer toggle"
```

---

## Task 9: Comparison Sidebar

**Files:**
- Create: `frontend/src/components/AssessmentViewer/ComparisonSidebar.tsx`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/components/AssessmentViewer/ComparisonSidebar.test.tsx`:

```typescript
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ComparisonSidebar } from "./ComparisonSidebar";

const mockAssessments = [
  { id: 1, framework: "forge" as const, control_set_id: 1, status: "complete" as const, questions: [] },
  { id: 2, framework: "openai" as const, control_set_id: 2, status: "complete" as const, questions: [] },
  { id: 3, framework: "risen" as const, control_set_id: 1, status: "generating" as const, questions: [] },
];

const mockControlSets = [
  { id: 1, personality: "formal", prompt_length: "short", result_length: "short", action_word_count: 2 },
  { id: 2, personality: "socratic", prompt_length: "medium", result_length: "medium", action_word_count: 3 },
];

describe("ComparisonSidebar", () => {
  it("renders one card per non-primary assessment", () => {
    const onSelect = vi.fn();
    render(
      <ComparisonSidebar
        assessments={mockAssessments}
        controlSets={mockControlSets}
        primaryId={1}
        onSelect={onSelect}
      />
    );
    // 2 cards (all except primary id=1)
    expect(screen.getAllByRole("button")).toHaveLength(2);
  });

  it("calls onSelect with assessment id when card is clicked", async () => {
    const user = userEvent.setup();
    const onSelect = vi.fn();
    render(
      <ComparisonSidebar
        assessments={mockAssessments}
        controlSets={mockControlSets}
        primaryId={1}
        onSelect={onSelect}
      />
    );
    const cards = screen.getAllByRole("button");
    await user.click(cards[0]);
    expect(onSelect).toHaveBeenCalledWith(2);
  });

  it("shows framework and control set label on each card", () => {
    render(
      <ComparisonSidebar
        assessments={mockAssessments}
        controlSets={mockControlSets}
        primaryId={1}
        onSelect={vi.fn()}
      />
    );
    expect(screen.getByText(/openai/i)).toBeInTheDocument();
    expect(screen.getByText(/socratic/i)).toBeInTheDocument();
  });

  it("shows first question preview if available", () => {
    const withQuestion = [
      { ...mockAssessments[1], questions: [{ id: 10, type: "mcq" as const, body: "Preview question body", order: 0, options: [], model_answer: null }] },
    ];
    render(
      <ComparisonSidebar
        assessments={[mockAssessments[0], ...withQuestion, mockAssessments[2]]}
        controlSets={mockControlSets}
        primaryId={1}
        onSelect={vi.fn()}
      />
    );
    expect(screen.getByText(/Preview question body/i)).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run to verify it fails**

```bash
cd frontend && npm test -- ComparisonSidebar.test.tsx
```
Expected: `Cannot find module './ComparisonSidebar'`.

- [ ] **Step 3: Create `frontend/src/components/AssessmentViewer/ComparisonSidebar.tsx`**

```typescript
import type { Assessment, ControlSet } from "../../types/api";

interface ComparisonSidebarProps {
  assessments: Assessment[];
  controlSets: ControlSet[];
  primaryId: number | null;
  onSelect: (id: number) => void;
}

export function ComparisonSidebar({ assessments, controlSets, primaryId, onSelect }: ComparisonSidebarProps) {
  const csById = Object.fromEntries(controlSets.map((cs) => [cs.id, cs]));
  const others = assessments.filter((a) => a.id !== primaryId);

  return (
    <aside className="comparison-sidebar">
      {others.map((a) => {
        const cs = csById[a.control_set_id];
        const preview = a.questions[0]?.body ?? null;
        const csLabel = cs
          ? `${cs.personality} / ${cs.prompt_length} / ${cs.action_word_count}w`
          : `Set ${a.control_set_id}`;

        return (
          <button
            key={a.id}
            className={`sidebar-card status-${a.status}`}
            onClick={() => onSelect(a.id)}
            type="button"
            aria-label={`View ${a.framework} ${csLabel} assessment`}
          >
            <div className="card-header">
              <span className="framework-badge">{a.framework.toUpperCase()}</span>
              <span className="cs-summary">{csLabel}</span>
            </div>
            {preview && (
              <p className="question-preview">{preview.length > 80 ? preview.slice(0, 80) + "…" : preview}</p>
            )}
          </button>
        );
      })}
    </aside>
  );
}
```

- [ ] **Step 4: Run the tests**

```bash
cd frontend && npm test -- ComparisonSidebar.test.tsx
```

Expected: All 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/AssessmentViewer/ComparisonSidebar.tsx
git commit -m "feat: add ComparisonSidebar with assessment cards and click-to-swap"
```

---

## Task 10: Primary Panel + Toolbar

**Files:**
- Create: `frontend/src/components/AssessmentViewer/Toolbar.tsx`
- Create: `frontend/src/components/AssessmentViewer/PrimaryPanel.tsx`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/components/AssessmentViewer/Toolbar.test.tsx`:

```typescript
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Toolbar } from "./Toolbar";

describe("Toolbar", () => {
  it("renders Pin, Regenerate, and Export buttons", () => {
    render(<Toolbar assessmentId={1} isPinned={false} onPin={vi.fn()} onRegenerate={vi.fn()} onExport={vi.fn()} />);
    expect(screen.getByRole("button", { name: /pin/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /regenerate/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /export/i })).toBeInTheDocument();
  });

  it("calls onRegenerate when Regenerate is clicked", async () => {
    const user = userEvent.setup();
    const onRegenerate = vi.fn();
    render(<Toolbar assessmentId={1} isPinned={false} onPin={vi.fn()} onRegenerate={onRegenerate} onExport={vi.fn()} />);
    await user.click(screen.getByRole("button", { name: /regenerate/i }));
    expect(onRegenerate).toHaveBeenCalledWith(1);
  });

  it("calls onExport with variant when export option selected", async () => {
    const user = userEvent.setup();
    const onExport = vi.fn();
    render(<Toolbar assessmentId={1} isPinned={false} onPin={vi.fn()} onRegenerate={vi.fn()} onExport={onExport} />);
    await user.click(screen.getByRole("button", { name: /export/i }));
    await user.click(screen.getByRole("menuitem", { name: /student/i }));
    expect(onExport).toHaveBeenCalledWith(1, "student");
  });
});
```

- [ ] **Step 2: Run to verify it fails**

```bash
cd frontend && npm test -- Toolbar.test.tsx
```
Expected: `Cannot find module './Toolbar'`.

- [ ] **Step 3: Create `frontend/src/components/AssessmentViewer/Toolbar.tsx`**

```typescript
import { useState } from "react";

interface ToolbarProps {
  assessmentId: number;
  isPinned: boolean;
  onPin: (id: number) => void;
  onRegenerate: (id: number) => void;
  onExport: (id: number, variant: "student" | "answer_key") => void;
}

export function Toolbar({ assessmentId, isPinned, onPin, onRegenerate, onExport }: ToolbarProps) {
  const [exportMenuOpen, setExportMenuOpen] = useState(false);

  return (
    <div className="toolbar">
      <button
        onClick={() => onPin(assessmentId)}
        className={`btn-pin ${isPinned ? "pinned" : ""}`}
        type="button"
        aria-pressed={isPinned}
        aria-label={isPinned ? "Unpin for export" : "Pin for export"}
      >
        {isPinned ? "📌 Pinned" : "📌 Pin for Export"}
      </button>

      <button
        onClick={() => onRegenerate(assessmentId)}
        className="btn-regenerate"
        type="button"
        aria-label="Regenerate assessment"
      >
        ↺ Regenerate
      </button>

      <div className="export-dropdown">
        <button
          onClick={() => setExportMenuOpen((v) => !v)}
          className="btn-export"
          type="button"
          aria-label="Export PDF"
          aria-haspopup="menu"
          aria-expanded={exportMenuOpen}
        >
          Export PDF ▾
        </button>
        {exportMenuOpen && (
          <ul role="menu" className="export-menu">
            <li role="menuitem">
              <button
                type="button"
                onClick={() => { onExport(assessmentId, "student"); setExportMenuOpen(false); }}
              >
                Student version
              </button>
            </li>
            <li role="menuitem">
              <button
                type="button"
                onClick={() => { onExport(assessmentId, "answer_key"); setExportMenuOpen(false); }}
              >
                Answer key version
              </button>
            </li>
          </ul>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Create `frontend/src/components/AssessmentViewer/PrimaryPanel.tsx`**

```typescript
import type { Assessment, ControlSet } from "../../types/api";
import { MCQQuestion } from "./questions/MCQQuestion";
import { LongAnswerQuestion } from "./questions/LongAnswerQuestion";

interface PrimaryPanelProps {
  assessment: Assessment;
  controlSet: ControlSet | undefined;
}

export function PrimaryPanel({ assessment, controlSet }: PrimaryPanelProps) {
  const sorted = [...assessment.questions].sort((a, b) => a.order - b.order);
  const resultLength = controlSet?.result_length ?? "medium";

  return (
    <main className="primary-panel">
      <div className="panel-header">
        <span className="framework-label">Framework: {assessment.framework.toUpperCase()}</span>
        {controlSet && (
          <span className="control-label">
            Control: {controlSet.personality} / {controlSet.prompt_length} / {controlSet.action_word_count} words
          </span>
        )}
      </div>

      <div className="questions-list">
        {sorted.map((q, i) =>
          q.type === "mcq" ? (
            <MCQQuestion key={q.id} question={q} index={i} />
          ) : (
            <LongAnswerQuestion key={q.id} question={q} index={i} resultLength={resultLength} />
          )
        )}
      </div>
    </main>
  );
}
```

- [ ] **Step 5: Write the PrimaryPanel test**

Create `frontend/src/components/AssessmentViewer/PrimaryPanel.test.tsx`:

```typescript
import { render, screen } from "@testing-library/react";
import { PrimaryPanel } from "./PrimaryPanel";

const mockAssessment = {
  id: 1,
  framework: "forge" as const,
  control_set_id: 1,
  status: "complete" as const,
  questions: [
    { id: 1, type: "mcq" as const, body: "MCQ question?", order: 0, options: [{ id: 1, body: "A", is_correct: true }, { id: 2, body: "B", is_correct: false }, { id: 3, body: "C", is_correct: false }, { id: 4, body: "D", is_correct: false }], model_answer: null },
    { id: 2, type: "long_answer" as const, body: "Long answer question?", order: 1, options: [], model_answer: { body: "Answer here." } },
  ],
};

const mockControlSet = {
  id: 1, personality: "formal", prompt_length: "medium", result_length: "medium", action_word_count: 3,
};

test("renders framework label", () => {
  render(<PrimaryPanel assessment={mockAssessment} controlSet={mockControlSet} />);
  expect(screen.getByText(/FORGE/i)).toBeInTheDocument();
});

test("renders all questions", () => {
  render(<PrimaryPanel assessment={mockAssessment} controlSet={mockControlSet} />);
  expect(screen.getByText(/MCQ question/i)).toBeInTheDocument();
  expect(screen.getByText(/Long answer question/i)).toBeInTheDocument();
});
```

- [ ] **Step 6: Run all new tests**

```bash
cd frontend && npm test -- Toolbar.test.tsx PrimaryPanel.test.tsx
```

Expected: All tests PASS.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/components/AssessmentViewer/Toolbar.tsx frontend/src/components/AssessmentViewer/PrimaryPanel.tsx
git commit -m "feat: add Toolbar with pin/regenerate/export and PrimaryPanel with question rendering"
```

---

## Task 11: Assessment Viewer Layout + App Integration

**Files:**
- Create: `frontend/src/components/AssessmentViewer/AssessmentViewer.tsx`
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/components/AssessmentViewer/AssessmentViewer.test.tsx`:

```typescript
import { render, screen } from "@testing-library/react";
import { AssessmentViewer } from "./AssessmentViewer";

const mockRun = {
  id: 1,
  topic: "TCP/IP",
  expectations: "Test handshake",
  mcq_count: 1,
  long_answer_count: 1,
  created_at: "2026-06-11T00:00:00",
  control_sets: [
    { id: 1, personality: "formal", prompt_length: "medium", result_length: "medium", action_word_count: 3 },
  ],
  assessments: [
    { id: 1, framework: "forge" as const, control_set_id: 1, status: "complete" as const },
    { id: 2, framework: "openai" as const, control_set_id: 1, status: "complete" as const },
  ],
};

const makeAssessment = (id: number, framework: string) => ({
  id,
  framework: framework as "forge",
  control_set_id: 1,
  status: "complete" as const,
  questions: [
    { id: id * 10, type: "mcq" as const, body: `Q from ${framework}`, order: 0, options: [{ id: 100, body: "A", is_correct: true }, { id: 101, body: "B", is_correct: false }, { id: 102, body: "C", is_correct: false }, { id: 103, body: "D", is_correct: false }], model_answer: null },
  ],
});

test("renders primary panel for the primary assessment", () => {
  render(
    <AssessmentViewer
      run={mockRun}
      assessments={{ 1: makeAssessment(1, "forge"), 2: makeAssessment(2, "openai") }}
      primaryAssessmentId={1}
      pinnedIds={[]}
      progressMap={{}}
      onSelectAssessment={vi.fn()}
      onPin={vi.fn()}
      onRegenerate={vi.fn()}
      onExport={vi.fn()}
    />
  );
  expect(screen.getByText(/FORGE/i)).toBeInTheDocument();
  expect(screen.getByText(/Q from forge/i)).toBeInTheDocument();
});

test("renders comparison sidebar with other assessments", () => {
  render(
    <AssessmentViewer
      run={mockRun}
      assessments={{ 1: makeAssessment(1, "forge"), 2: makeAssessment(2, "openai") }}
      primaryAssessmentId={1}
      pinnedIds={[]}
      progressMap={{}}
      onSelectAssessment={vi.fn()}
      onPin={vi.fn()}
      onRegenerate={vi.fn()}
      onExport={vi.fn()}
    />
  );
  // Sidebar shows the other assessments (not the primary)
  expect(screen.getByText(/openai/i)).toBeInTheDocument();
});
```

- [ ] **Step 2: Run to verify it fails**

```bash
cd frontend && npm test -- AssessmentViewer.test.tsx
```
Expected: `Cannot find module './AssessmentViewer'`.

- [ ] **Step 3: Create `frontend/src/components/AssessmentViewer/AssessmentViewer.tsx`**

```typescript
import type { Assessment, AssessmentStatus, Framework, Run } from "../../types/api";
import { ComparisonSidebar } from "./ComparisonSidebar";
import { PrimaryPanel } from "./PrimaryPanel";
import { Toolbar } from "./Toolbar";

interface AssessmentViewerProps {
  run: Run;
  assessments: Record<number, Assessment>;
  primaryAssessmentId: number | null;
  pinnedIds: number[];
  progressMap: Record<number, AssessmentStatus>;
  onSelectAssessment: (id: number) => void;
  onPin: (id: number) => void;
  onRegenerate: (id: number) => void;
  onExport: (id: number, variant: "student" | "answer_key") => void;
}

export function AssessmentViewer({
  run,
  assessments,
  primaryAssessmentId,
  pinnedIds,
  progressMap,
  onSelectAssessment,
  onPin,
  onRegenerate,
  onExport,
}: AssessmentViewerProps) {
  const primaryAssessment = primaryAssessmentId ? assessments[primaryAssessmentId] : null;
  const csById = Object.fromEntries(run.control_sets.map((cs) => [cs.id, cs]));

  // Show all assessments that are loaded in the sidebar
  const loadedAssessments = run.assessments
    .map((a) => assessments[a.id])
    .filter(Boolean) as Assessment[];

  return (
    <div className="assessment-viewer">
      {primaryAssessment && primaryAssessmentId && (
        <Toolbar
          assessmentId={primaryAssessmentId}
          isPinned={pinnedIds.includes(primaryAssessmentId)}
          onPin={onPin}
          onRegenerate={onRegenerate}
          onExport={onExport}
        />
      )}
      <div className="viewer-body">
        <ComparisonSidebar
          assessments={loadedAssessments}
          controlSets={run.control_sets}
          primaryId={primaryAssessmentId}
          onSelect={onSelectAssessment}
        />
        {primaryAssessment ? (
          <PrimaryPanel
            assessment={primaryAssessment}
            controlSet={csById[primaryAssessment.control_set_id]}
          />
        ) : (
          <div className="loading-panel">Waiting for first assessment to complete…</div>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Run the tests**

```bash
cd frontend && npm test -- AssessmentViewer.test.tsx
```

Expected: Both tests PASS.

- [ ] **Step 5: Wire everything together in `frontend/src/App.tsx`**

```typescript
import { useEffect } from "react";
import { InputPanel } from "./components/InputPanel/InputPanel";
import { ProgressGrid } from "./components/ProgressGrid/ProgressGrid";
import { AssessmentViewer } from "./components/AssessmentViewer/AssessmentViewer";
import { useRunStore } from "./store/useRunStore";
import { useSSEPost } from "./hooks/useSSEPost";
import { getAssessment, regenerateAssessment, exportPdf, downloadBlob } from "./api/client";
import type { RunCreate } from "./types/api";

export default function App() {
  const {
    phase,
    runId,
    runConfig,
    progressMap,
    assessments,
    primaryAssessmentId,
    pinnedAssessmentIds,
    setRunConfig,
    loadAssessment,
    setPrimaryAssessmentId,
    togglePin,
  } = useRunStore();

  const { startRun } = useSSEPost();

  const [fullRun, setFullRun] = useState<import("./types/api").Run | null>(null);

  const handleSubmit = async (payload: RunCreate) => {
    setRunConfig(payload);
    await startRun(payload);
    // After SSE stream ends, fetch the full run (for control set metadata)
    const currentRunId = useRunStore.getState().runId;
    if (currentRunId) {
      const run = await fetch(`/runs/${currentRunId}`).then((r) => r.json());
      setFullRun(run);
    }
  };

  // Auto-load assessments that reach "complete"
  useEffect(() => {
    const completedIds = Object.entries(progressMap)
      .filter(([, stage]) => stage === "complete")
      .map(([id]) => parseInt(id))
      .filter((id) => !assessments[id]);

    completedIds.forEach((id) => {
      getAssessment(id).then(loadAssessment);
    });
  }, [progressMap]);

  // Transition to viewer once first assessment loads
  useEffect(() => {
    if (Object.keys(assessments).length > 0 && phase === "progress") {
      useRunStore.getState().setPhase("viewer");
    }
  }, [assessments, phase]);

  const handleRegenerate = async (id: number) => {
    await regenerateAssessment(id);
  };

  const handleExport = async (id: number, variant: "student" | "answer_key") => {
    const blob = await exportPdf(id, variant);
    downloadBlob(blob, `assessment-${id}-${variant}.pdf`);
  };

  if (phase === "input") {
    return (
      <div className="app">
        <h1>Assessment Generator</h1>
        <InputPanel onSubmit={handleSubmit} isSubmitting={false} />
      </div>
    );
  }

  if (phase === "progress" || (phase === "viewer" && Object.keys(assessments).length === 0)) {
    // During SSE streaming, use loaded assessments or fallback to empty list
    const progressAssessments = fullRun
      ? fullRun.assessments
      : Object.values(assessments).map((a) => ({
          id: a.id, framework: a.framework, control_set_id: a.control_set_id, status: a.status,
        }));
    return (
      <div className="app">
        <h1>Generating Assessments…</h1>
        <ProgressGrid assessments={progressAssessments} progressMap={progressMap} />
      </div>
    );
  }

  if (!fullRun) return <div>Loading run data…</div>;

  return (
    <div className="app">
      <AssessmentViewer
        run={fullRun}
        assessments={assessments}
        primaryAssessmentId={primaryAssessmentId}
        pinnedIds={pinnedAssessmentIds}
        progressMap={progressMap}
        onSelectAssessment={setPrimaryAssessmentId}
        onPin={togglePin}
        onRegenerate={handleRegenerate}
        onExport={handleExport}
      />
    </div>
  );
}
```

- [ ] **Step 6: Run all tests**

```bash
cd frontend && npm test
```

Expected: All tests PASS.

- [ ] **Step 7: Start the dev server and verify the app renders**

```bash
cd frontend && npm run dev
```

Open `http://localhost:5173`. Expected: Input panel renders with form, checkboxes, and control set rows.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/components/AssessmentViewer/AssessmentViewer.tsx frontend/src/App.tsx
git commit -m "feat: add AssessmentViewer layout and wire all components in App.tsx"
```
