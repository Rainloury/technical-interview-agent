import { lazy, Suspense } from "react";
import { Navigate, Route, Routes } from "react-router-dom";

import { usePageViews } from "@/app/analytics";
import { ProtectedRoute } from "@/features/auth/ProtectedRoute";
import { PublicOnlyRoute } from "@/features/auth/PublicOnlyRoute";
import { AppShell } from "@/app/AppShell";
import { FullPageState } from "@/shared/ui/FullPageState";

const ForgotPasswordPage = lazy(() =>
  import("@/features/auth/ForgotPasswordPage").then((module) => ({
    default: module.ForgotPasswordPage,
  })),
);
const DocumentsPage = lazy(() =>
  import("@/features/documents/DocumentsPage").then((module) => ({
    default: module.DocumentsPage,
  })),
);
const HistoryPage = lazy(() =>
  import("@/features/history/HistoryPage").then((module) => ({
    default: module.HistoryPage,
  })),
);
const InterviewDetailPage = lazy(() =>
  import("@/features/interviews/InterviewDetailPage").then((module) => ({
    default: module.InterviewDetailPage,
  })),
);
const InterviewPage = lazy(() =>
  import("@/features/interviews/InterviewPage").then((module) => ({
    default: module.InterviewPage,
  })),
);
const LoginPage = lazy(() =>
  import("@/features/auth/LoginPage").then((module) => ({
    default: module.LoginPage,
  })),
);
const NotFoundPage = lazy(() =>
  import("@/app/NotFoundPage").then((module) => ({
    default: module.NotFoundPage,
  })),
);
const QaDetailPage = lazy(() =>
  import("@/features/qa/QaDetailPage").then((module) => ({
    default: module.QaDetailPage,
  })),
);
const QaPage = lazy(() =>
  import("@/features/qa/QaPage").then((module) => ({ default: module.QaPage })),
);
const RegisterPage = lazy(() =>
  import("@/features/auth/RegisterPage").then((module) => ({
    default: module.RegisterPage,
  })),
);
const ResetPasswordPage = lazy(() =>
  import("@/features/auth/ResetPasswordPage").then((module) => ({
    default: module.ResetPasswordPage,
  })),
);
const ResumeDetailPage = lazy(() =>
  import("@/features/resumes/ResumeDetailPage").then((module) => ({
    default: module.ResumeDetailPage,
  })),
);
const ResumeUploadPage = lazy(() =>
  import("@/features/resumes/ResumeUploadPage").then((module) => ({
    default: module.ResumeUploadPage,
  })),
);
const ReviewPage = lazy(() =>
  import("@/features/reviews/ReviewPage").then((module) => ({
    default: module.ReviewPage,
  })),
);
const WorkspacePage = lazy(() =>
  import("@/features/workspace/WorkspacePage").then((module) => ({
    default: module.WorkspacePage,
  })),
);

export function App() {
  usePageViews();

  return (
    <Suspense fallback={<FullPageState title="正在加载页面" />}>
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
            <Route path="/documents" element={<DocumentsPage />} />
            <Route path="/interviews" element={<InterviewPage />} />
            <Route path="/interviews/:id" element={<InterviewDetailPage />} />
            <Route path="/reviews" element={<ReviewPage />} />
            <Route path="/resumes/new" element={<ResumeUploadPage />} />
            <Route path="/resumes/:id" element={<ResumeDetailPage />} />
          </Route>
        </Route>

        <Route path="/" element={<Navigate to="/workspace" replace />} />
        <Route path="*" element={<NotFoundPage />} />
      </Routes>
    </Suspense>
  );
}
