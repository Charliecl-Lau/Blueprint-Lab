import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { evaluationsApi } from '../api/evaluations'
import type {
  CriterionKey,
  Evaluation,
  HumanCriterionPatch,
  HumanEvaluationPatch,
  RecommendedAction,
} from '../types'

type OverallField = 'highest_priority_issue' | 'overall_comments' | 'recommended_action'
type PendingPatch = {
  criteria: Partial<Record<CriterionKey, HumanCriterionPatch>>
  highest_priority_issue?: string | null
  overall_comments?: string | null
  recommended_action?: RecommendedAction | null
}

const emptyPending = (): PendingPatch => ({ criteria: {} })
const hasOwn = (value: object, key: string) => Object.prototype.hasOwnProperty.call(value, key)
const isDirtyPatch = (patch: PendingPatch) => (
  Object.keys(patch.criteria).length > 0
  || hasOwn(patch, 'highest_priority_issue')
  || hasOwn(patch, 'overall_comments')
  || hasOwn(patch, 'recommended_action')
)

function mergeCriterion(evaluation: Evaluation, patch: HumanCriterionPatch): Evaluation {
  const current = evaluation.criteria.find((item) => item.criterion_key === patch.criterion_key)
  const next = {
    score: current?.score ?? null,
    comment: current?.comment ?? null,
    suggested_modification: current?.suggested_modification ?? null,
    issue_flags: current?.issue_flags ?? [],
    justification: current?.justification ?? null,
    strengths: current?.strengths ?? [],
    weaknesses: current?.weaknesses ?? [],
    suggested_improvements: current?.suggested_improvements ?? [],
    suggested_modifications: current?.suggested_modifications ?? [],
    ...patch,
    criterion_key: patch.criterion_key,
  }
  return {
    ...evaluation,
    criteria: current
      ? evaluation.criteria.map((item) => item.criterion_key === patch.criterion_key ? next : item)
      : [...evaluation.criteria, next],
  }
}

function applyPending(evaluation: Evaluation, patch: PendingPatch) {
  let next = evaluation
  Object.values(patch.criteria).forEach((criterion) => {
    if (criterion) next = mergeCriterion(next, criterion)
  })
  if (hasOwn(patch, 'highest_priority_issue')) next = { ...next, highest_priority_issue: patch.highest_priority_issue ?? null }
  if (hasOwn(patch, 'overall_comments')) next = { ...next, overall_comments: patch.overall_comments ?? null }
  if (hasOwn(patch, 'recommended_action')) next = { ...next, recommended_action: patch.recommended_action ?? null }
  return next
}

function mergeServerEvaluation(previous: Evaluation, response: Evaluation) {
  let merged = { ...previous, ...response, criteria: previous.criteria }
  response.criteria.forEach((criterion) => {
    merged = mergeCriterion(merged, criterion)
  })
  return merged
}

function toPayload(revision: number, patch: PendingPatch): HumanEvaluationPatch {
  const payload: HumanEvaluationPatch = { revision }
  const criteria = Object.values(patch.criteria).filter(Boolean) as HumanCriterionPatch[]
  if (criteria.length) payload.criteria = criteria
  if (hasOwn(patch, 'highest_priority_issue')) payload.highest_priority_issue = patch.highest_priority_issue
  if (hasOwn(patch, 'overall_comments')) payload.overall_comments = patch.overall_comments
  if (hasOwn(patch, 'recommended_action')) payload.recommended_action = patch.recommended_action
  return payload
}

export function useHumanEvaluationDraft(initialEvaluation: Evaluation | null) {
  const navigate = useNavigate()
  const [serverDraft, setServerDraft] = useState(initialEvaluation)
  const [draft, setDraft] = useState(initialEvaluation)
  const [dirty, setDirty] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const serverRef = useRef(initialEvaluation)
  const pendingRef = useRef<PendingPatch>(emptyPending())
  const saveQueueRef = useRef<Promise<void>>(Promise.resolve())

  /* The server record is loaded after this hook mounts and changes only when the keyed question changes. */
  /* eslint-disable react-hooks/set-state-in-effect */
  useEffect(() => {
    if (!initialEvaluation) return
    serverRef.current = initialEvaluation
    pendingRef.current = emptyPending()
    setServerDraft(initialEvaluation)
    setDraft(initialEvaluation)
    setDirty(false)
  }, [initialEvaluation])
  /* eslint-enable react-hooks/set-state-in-effect */

  const updateCriterion = useCallback((patch: HumanCriterionPatch) => {
    pendingRef.current = {
      ...pendingRef.current,
      criteria: {
        ...pendingRef.current.criteria,
        [patch.criterion_key]: {
          ...pendingRef.current.criteria[patch.criterion_key],
          ...patch,
        },
      },
    }
    setDraft((current) => current ? mergeCriterion(current, patch) : current)
    setDirty(true)
  }, [])

  const updateOverall = useCallback((field: OverallField, value: string | null) => {
    const normalized = field === 'recommended_action' ? value as RecommendedAction | null : value
    pendingRef.current = { ...pendingRef.current, [field]: normalized }
    setDraft((current) => current ? { ...current, [field]: normalized } : current)
    setDirty(true)
  }, [])

  const persistOne = useCallback(() => {
    let result: Evaluation | null = null
    const operation = saveQueueRef.current.then(async () => {
      const server = serverRef.current
      const pending = pendingRef.current
      if (!server || !isDirtyPatch(pending)) {
        result = server
        return
      }
      pendingRef.current = emptyPending()
      setDirty(false)
      setSaving(true)
      setError(null)
      try {
        const response = await evaluationsApi.update(server.id, toPayload(server.revision, pending))
        const canonical = mergeServerEvaluation(server, response)
        serverRef.current = canonical
        setServerDraft(canonical)
        setDraft(applyPending(canonical, pendingRef.current))
        setDirty(isDirtyPatch(pendingRef.current))
        result = canonical
      } catch (cause) {
        pendingRef.current = {
          ...pending,
          ...pendingRef.current,
          criteria: { ...pending.criteria, ...pendingRef.current.criteria },
        }
        setDirty(true)
        setError(cause instanceof Error ? cause.message : 'Unable to save the evaluation draft.')
        throw cause
      } finally {
        setSaving(false)
      }
    })
    saveQueueRef.current = operation.then(() => undefined, () => undefined)
    return operation.then(() => result)
  }, [])

  const saveNow = useCallback(async () => {
    let saved = await persistOne()
    while (isDirtyPatch(pendingRef.current)) saved = await persistOne()
    return saved ?? serverRef.current
  }, [persistOne])

  useEffect(() => {
    if (!dirty) return
    const timer = window.setInterval(() => { void saveNow() }, 30_000)
    return () => window.clearInterval(timer)
  }, [dirty, saveNow])

  useEffect(() => {
    const warn = (event: BeforeUnloadEvent) => {
      if (!isDirtyPatch(pendingRef.current)) return
      event.preventDefault()
      event.returnValue = ''
    }
    window.addEventListener('beforeunload', warn)
    return () => window.removeEventListener('beforeunload', warn)
  }, [])

  const resetUnsaved = useCallback(() => {
    pendingRef.current = emptyPending()
    setDraft(serverRef.current)
    setDirty(false)
    setError(null)
  }, [])

  const finalize = useCallback(async () => {
    const saved = await saveNow()
    if (!saved) return null
    const finalized = await evaluationsApi.finalize(saved.id)
    const canonical = mergeServerEvaluation(saved, finalized)
    serverRef.current = canonical
    setServerDraft(canonical)
    setDraft(canonical)
    return canonical
  }, [saveNow])

  const reopen = useCallback(async () => {
    const current = serverRef.current
    if (!current) return null
    const reopened = mergeServerEvaluation(current, await evaluationsApi.reopen(current.id))
    serverRef.current = reopened
    setServerDraft(reopened)
    setDraft(reopened)
    return reopened
  }, [])

  const navigateWithConfirmation = useCallback((path: string) => {
    if (isDirtyPatch(pendingRef.current) && !window.confirm('You have unsaved grading changes. Leave this assessment?')) return
    navigate(path)
  }, [navigate])

  return {
    serverDraft,
    draft,
    dirty,
    saving,
    error,
    updateCriterion,
    updateOverall,
    saveNow,
    resetUnsaved,
    finalize,
    reopen,
    navigateWithConfirmation,
  }
}
