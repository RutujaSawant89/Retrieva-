import { QueryClientProvider } from '@tanstack/react-query'
import { Link, Route, BrowserRouter, Routes } from 'react-router'
import { Toaster } from 'sonner'

import { AppShell } from '@/components/layout/AppShell'
import { RedirectIfAuthenticated, RequireAuth, RequirePermission } from '@/components/layout/guards'
import { Button } from '@/components/ui/button'
import { TooltipProvider } from '@/components/ui/overlays'
import { EmptyState } from '@/components/ui/primitives'
import { AuthProvider } from '@/contexts/AuthContext'
import { ThemeProvider, useTheme } from '@/contexts/ThemeContext'
import { AdminPage } from '@/pages/admin/AdminPage'
import { ChatPage } from '@/pages/chat/ChatPage'
import { CollectionsPage } from '@/pages/collections/CollectionsPage'
import { DocumentDetailPage } from '@/pages/documents/DocumentDetailPage'
import { DocumentsPage } from '@/pages/documents/DocumentsPage'
import { SearchPage } from '@/pages/SearchPage'
import { LoginPage } from '@/pages/auth/LoginPage'
import { RegisterPage } from '@/pages/auth/RegisterPage'
import { DashboardPage } from '@/pages/DashboardPage'
import { LandingPage } from '@/pages/LandingPage'
import { SettingsPage } from '@/pages/SettingsPage'
import { createQueryClient } from '@/queryClient'

function ThemedToaster() {
  const { resolved } = useTheme()
  return <Toaster theme={resolved} position="bottom-right" richColors closeButton />
}

function NotFound() {
  return (
    <EmptyState
      className="h-full"
      title="Page not found"
      description="The page you are looking for does not exist."
      action={
        <Button asChild variant="secondary">
          <Link to="/">Go home</Link>
        </Button>
      }
    />
  )
}

export function AppRoutes() {
  return (
    <Routes>
      <Route path="/" element={<LandingPage />} />
      <Route
        path="/login"
        element={
          <RedirectIfAuthenticated>
            <LoginPage />
          </RedirectIfAuthenticated>
        }
      />
      <Route
        path="/register"
        element={
          <RedirectIfAuthenticated>
            <RegisterPage />
          </RedirectIfAuthenticated>
        }
      />
      <Route element={<RequireAuth />}>
        <Route path="/app" element={<AppShell />}>
          <Route index element={<DashboardPage />} />
          <Route path="chat" element={<ChatPage />} />
          <Route path="chat/:conversationId" element={<ChatPage />} />
          <Route path="search" element={<SearchPage />} />
          <Route path="documents" element={<DocumentsPage />} />
          <Route path="documents/:documentId" element={<DocumentDetailPage />} />
          <Route path="collections" element={<CollectionsPage />} />
          <Route path="collections/:collectionId" element={<CollectionsPage />} />
          <Route path="settings" element={<SettingsPage />} />
          <Route
            path="admin"
            element={
              <RequirePermission permission="members:manage">
                <AdminPage />
              </RequirePermission>
            }
          />
          <Route path="*" element={<NotFound />} />
        </Route>
      </Route>
      <Route path="*" element={<NotFound />} />
    </Routes>
  )
}

const queryClient = createQueryClient()

export default function App() {
  return (
    <ThemeProvider>
      <QueryClientProvider client={queryClient}>
        <AuthProvider>
          <TooltipProvider>
            <BrowserRouter>
              <AppRoutes />
            </BrowserRouter>
            <ThemedToaster />
          </TooltipProvider>
        </AuthProvider>
      </QueryClientProvider>
    </ThemeProvider>
  )
}
