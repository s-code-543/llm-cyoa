import { ChatsPage } from "../features/admin/ChatsPage";
import { ConfigEditPage, ConfigListPage, ConfigNewPage } from "../features/admin/ConfigPages";
import { ProviderEditPage, ProviderListPage, ProviderNewPage } from "../features/admin/ProvidersPage";
import { ModelBrowserPage, ModelListPage } from "../features/admin/ModelsPage";
import { DifficultyEditPage, DifficultyListPage, DifficultyNewPage } from "../features/admin/DifficultyPage";
import { VoicePage } from "../features/admin/VoicePage";
import { BrowserRouter, Route, Routes, useLocation } from "react-router";
import { ChatPage } from "../features/chat/ChatPage";
import { HomePage } from "../features/home/HomePage";
import { AdminHome } from "../features/admin/AdminHome";
import { AdminLayout } from "../features/admin/AdminLayout";
import { AuditDetailPage, AuditPage } from "../features/admin/AuditPage";
import { PromptEditPage, PromptListPage, PromptNewPage } from "../features/admin/PromptsPage";
import { LoginPage } from "../features/session/LoginPage";
import { SessionProvider } from "../features/session/SessionProvider";
import { Layout } from "./Layout";
import { RequirePermission } from "./RequirePermission";

// Remount on every router navigation so ChatPage re-reads its URL parameters.
function ChatRoute() {
  const location = useLocation();
  return <ChatPage key={location.key} />;
}

export function AppRoutes() {
  return (
    <SessionProvider>
      <Routes>
        <Route element={<Layout />}>
          <Route path="login" element={<LoginPage />} />
          <Route
            index
            element={
              <RequirePermission permission="play">
                <HomePage />
              </RequirePermission>
            }
          />
          <Route
            path="chat"
            element={
              <RequirePermission permission="play">
                <ChatRoute />
              </RequirePermission>
            }
          />
          <Route
            path="manage"
            element={
              <RequirePermission permission="admin">
                <AdminLayout />
              </RequirePermission>
            }
          >
            <Route index element={<AdminHome />} />
            <Route path="audit" element={<AuditPage />} />
            <Route path="chats" element={<ChatsPage />} />
            <Route path="audit/:id" element={<AuditDetailPage />} />
            <Route path="prompts" element={<PromptListPage />} />
            <Route path="prompts/new" element={<PromptNewPage />} />
            <Route path="prompts/:id" element={<PromptEditPage />} />
            <Route path="configurations" element={<ConfigListPage />} />
            <Route path="configurations/new" element={<ConfigNewPage />} />
            <Route path="configurations/:id" element={<ConfigEditPage />} />
            <Route path="providers" element={<ProviderListPage />} />
            <Route path="providers/new" element={<ProviderNewPage />} />
            <Route path="providers/:id" element={<ProviderEditPage />} />
            <Route path="providers/:id/models" element={<ModelBrowserPage />} />
            <Route path="models" element={<ModelListPage />} />
            <Route path="difficulty" element={<DifficultyListPage />} />
            <Route path="difficulty/new" element={<DifficultyNewPage />} />
            <Route path="difficulty/:id" element={<DifficultyEditPage />} />
            <Route path="voice" element={<VoicePage />} />
          </Route>
          <Route
            path="*"
            element={
              <main className="page">
                <h1>Page not found</h1>
              </main>
            }
          />
        </Route>
      </Routes>
    </SessionProvider>
  );
}

export const App = () => (
  <BrowserRouter>
    <AppRoutes />
  </BrowserRouter>
);
