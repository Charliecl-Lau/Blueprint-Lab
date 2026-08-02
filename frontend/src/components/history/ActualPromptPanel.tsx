export function ActualPromptPanel({ prompt }: { prompt: string | null }) {
  return prompt
    ? <pre className="history-actual-prompt">{prompt}</pre>
    : <p>No actual prompt</p>
}
