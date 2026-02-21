import { lazy, Suspense } from 'react';
import { createBrowserRouter, useOutletContext } from 'react-router-dom';
import AppLayout from '@/components/AppLayout';

// Lazy-load pages for route-based code splitting
const DashboardPage = lazy(() => import('@/components/pages/Dashboard/DashboardPage'));
const NetworkPage = lazy(() => import('@/components/pages/Network/NetworkPage'));
const SearchPage = lazy(() => import('@/components/pages/Search/SearchPage'));
const ConnectionsPage = lazy(() => import('@/components/pages/Connections/ConnectionsPage'));
const ReviewPage = lazy(() => import('@/components/pages/Review/ReviewPage'));
const AssistPage = lazy(() => import('@/components/pages/Assist/AssistPage'));

function LazyWrap({ children }) {
  return (
    <Suspense fallback={<div className="flex items-center justify-center h-full text-sm" style={{ color: '#8C8C8C' }}>Loading…</div>}>
      {children}
    </Suspense>
  );
}

// Bridge wrappers — consume Outlet context and map to page props
function DashboardWrapper() {
  const { goTo } = useOutletContext();
  return <LazyWrap><DashboardPage onNavigate={goTo} /></LazyWrap>;
}

function NetworkWrapper() {
  const { selectedEntity, setSelectedEntity, privacy, goTo } = useOutletContext();
  return (
    <LazyWrap>
      <NetworkPage
        selectedEntity={selectedEntity}
        onSelect={setSelectedEntity}
        onOpenAI={() => goTo('assist', selectedEntity)}
        privacy={privacy}
      />
    </LazyWrap>
  );
}

function SearchWrapper() {
  const { setSelectedEntity, goTo } = useOutletContext();
  return <LazyWrap><SearchPage onSelect={(ent) => { setSelectedEntity(ent); goTo('network'); }} /></LazyWrap>;
}

function ConnectionsWrapper() {
  const { goTo } = useOutletContext();
  return <LazyWrap><ConnectionsPage onNavigate={goTo} /></LazyWrap>;
}

function ReviewWrapper() {
  return <LazyWrap><ReviewPage /></LazyWrap>;
}

function AssistWrapper() {
  const { chat, setSelectedEntity } = useOutletContext();
  return <LazyWrap><AssistPage chat={chat} onResetEntity={setSelectedEntity} /></LazyWrap>;
}

export const router = createBrowserRouter([
  {
    path: '/',
    element: <AppLayout />,
    children: [
      { index: true,        element: <DashboardWrapper /> },
      { path: 'network',    element: <NetworkWrapper /> },
      { path: 'search',     element: <SearchWrapper /> },
      { path: 'connections', element: <ConnectionsWrapper /> },
      { path: 'review',     element: <ReviewWrapper /> },
      { path: 'assist',     element: <AssistWrapper /> },
    ],
  },
]);
