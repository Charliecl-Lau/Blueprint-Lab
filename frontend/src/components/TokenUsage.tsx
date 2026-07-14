import type { TokenUsage as TokenUsageData } from '../types'

function value(number: number | null) {
  return number === null ? 'Not reported' : number.toLocaleString()
}

export function TokenUsage({ usage }: { usage?: TokenUsageData }) {
  if (!usage) return <p className="usage-state">Token usage is loading.</p>
  if (usage.recording_state === 'not_recorded') {
    return (
      <section className="token-usage" aria-label="Token usage">
        <h3>End-to-end token usage</h3>
        <p className="usage-state">Not recorded.</p>
      </section>
    )
  }

  return (
    <section className="token-usage" aria-label="Token usage">
      <div className="usage-heading">
        <h3>End-to-end token usage</h3>
        {usage.recording_state === 'in_progress' && (
          <span className="usage-state">In progress</span>
        )}
      </div>
      <dl>
        <div><dt>Input</dt><dd>{value(usage.input_tokens)}</dd></div>
        <div><dt>Output</dt><dd>{value(usage.output_tokens)}</dd></div>
        <div><dt>Total</dt><dd>{value(usage.total_tokens)}</dd></div>
        <div><dt>Model calls</dt><dd>{value(usage.model_calls)}</dd></div>
      </dl>
      {usage.stages.length > 0 && (
        <details>
          <summary>Usage by stage</summary>
          {usage.stages.map((stage) => (
            <dl className="stage-usage" key={stage.stage}>
              <div><dt>Stage</dt><dd>{stage.stage.replaceAll('_', ' ')}</dd></div>
              <div><dt>Input</dt><dd>{value(stage.input_tokens)}</dd></div>
              <div><dt>Output</dt><dd>{value(stage.output_tokens)}</dd></div>
              <div><dt>Total</dt><dd>{value(stage.total_tokens)}</dd></div>
              <div><dt>Model calls</dt><dd>{stage.model_calls}</dd></div>
              {stage.cached_content_tokens !== undefined && (
                <div><dt>Cached content</dt><dd>{stage.cached_content_tokens}</dd></div>
              )}
              {stage.reasoning_tokens !== undefined && (
                <div><dt>Reasoning</dt><dd>{stage.reasoning_tokens}</dd></div>
              )}
            </dl>
          ))}
        </details>
      )}
    </section>
  )
}
