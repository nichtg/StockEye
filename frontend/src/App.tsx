import { lazy } from 'react';
import { Route, Routes } from 'react-router';
import { AppShell } from './components/AppShell';
import { NotFoundView } from './components/NotFoundView';
import { PublicOnly } from './features/auth/PublicOnly';
import { RequireAuth } from './features/auth/RequireAuth';
import { useMe } from './features/auth/useAuth';
import HomePage from './pages/HomePage';
import LoginPage from './pages/LoginPage';
import RegisterPage from './pages/RegisterPage';

// Declarative routing: all data lives in React Query, so route loaders would add nothing here.
const AdminPage = lazy(() => import('./pages/AdminPage'));
const StockPage = lazy(() => import('./pages/StockPage'));

function AdminRoute() {
  const me = useMe();
  // Non-admins get the same view as an unknown URL so the admin area's existence is not revealed.
  return me.data?.role === 'admin' ? <AdminPage /> : <NotFoundView />;
}

export function App() {
  return (
    <Routes>
      <Route element={<PublicOnly />}>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/register" element={<RegisterPage />} />
      </Route>
      <Route element={<RequireAuth />}>
        <Route element={<AppShell />}>
          <Route index element={<HomePage />} />
          <Route path="/stock/:symbol" element={<StockPage />} />
          <Route path="/admin" element={<AdminRoute />} />
          <Route path="*" element={<NotFoundView />} />
        </Route>
      </Route>
    </Routes>
  );
}
