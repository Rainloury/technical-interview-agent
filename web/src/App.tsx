import { Navigate, Route, Routes } from "react-router-dom";

import { ProtectedRoute } from "./auth/ProtectedRoute";
import { PublicOnlyRoute } from "./auth/PublicOnlyRoute";
import { AppShell } from "./components/AppShell";
import { ForgotPasswordPage } from "./pages/ForgotPasswordPage";
import { HistoryPage } from "./pages/HistoryPage";
import { LoginPage } from "./pages/LoginPage";
import { NotFoundPage } from "./pages/NotFoundPage";
import { QaDetailPage } from "./pages/QaDetailPage";
import { QaPage } from "./pages/QaPage";
import { RegisterPage } from "./pages/RegisterPage";
import { ResumeDetailPage } from "./pages/ResumeDetailPage";
import { ResumeUploadPage } from "./pages/ResumeUploadPage";
import { ResetPasswordPage } from "./pages/ResetPasswordPage";
import { WorkspacePage } from "./pages/WorkspacePage";

export function App() {
  return (
    <Routes>
      <Route element={<PublicOnlyRoute />}>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/register" element={<RegisterPage />} />
        <Route path="/forgot-password" element={<ForgotPasswordPage />} />
      </Route>
      <Route path="/reset-password" element={<ResetPasswordPage />} />

      <Route element={<ProtectedRoute />}>
        <Route element={<AppShell />}>
          <Route path="/workspace" element={<WorkspacePage />} />
          <Route path="/history" element={<HistoryPage />} />
          <Route path="/qa" element={<QaPage />} />
          <Route path="/qa/:id" element={<QaDetailPage />} />
          <Route path="/resumes/new" element={<ResumeUploadPage />} />
          <Route path="/resumes/:id" element={<ResumeDetailPage />} />
        </Route>
      </Route>

      <Route path="/" element={<Navigate to="/workspace" replace />} />
      <Route path="*" element={<NotFoundPage />} />
    </Routes>
  );
}
