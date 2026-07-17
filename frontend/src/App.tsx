import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { InputPanelPage } from './pages/InputPanelPage'
import { ProgressPage } from './pages/ProgressPage'
import { AssessmentViewerPage } from './pages/AssessmentViewerPage'
import { AssessmentGradingPage } from './pages/AssessmentGradingPage'

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<InputPanelPage />} />
        <Route path="/runs/:runId/progress" element={<ProgressPage />} />
        <Route path="/experiments/:experimentId/viewer/:runId?" element={<AssessmentViewerPage />} />
        <Route path="/assessments/:assessmentId/questions/:questionId/grade" element={<AssessmentGradingPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  )
}
