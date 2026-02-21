import { useState, useEffect, useRef } from 'react';
import { Outlet, useNavigate, useLocation } from 'react-router-dom';
import {
  Search, Home, Globe, UserPlus, ClipboardCheck, Sparkles,
  Menu,
} from 'lucide-react';
import { QB } from '@/constants/colors';
import { ROUTES, viewToPath } from '@/config/routes';
import { PENDING_MATCHES, ENTITIES } from '@/api/mock/data';
import { useAIChat } from '@/hooks/useAIChat';
import { AIPanel, MergeNotification } from '@/components/shared';
import { wsManager } from '@/api/websocket';

const SIDEBAR_ICONS = {
  dashboard: <Home size={18} />,
  network: <Globe size={18} />,
  search: <Search size={18} />,
  connections: <UserPlus size={18} />,
  review: <ClipboardCheck size={18} />,
  assist: <Sparkles size={18} />,
};

export default function AppLayout() {
  const navigate = useNavigate();
  const location = useLocation();

  const [aiOpen, setAiOpen] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [privacy, setPrivacy] = useState(false);
  const [selectedEntity, setSelectedEntity] = useState(ENTITIES[0]);
  const [showMergeNotif, setShowMergeNotif] = useState(true);

  // Current active route id — computed before useAIChat so it can be passed as context
  const activeId = ROUTES.find((r) => r.path === location.pathname)?.id || 'dashboard';

  const chat = useAIChat(selectedEntity, activeId);

  const handleAction = (action, payload) => {
    switch (action) {
      case 'navigate':
        navigate(viewToPath[payload.page] || '/');
        setAiOpen(false);
        break;
      case 'select_entity': {
        const entity = ENTITIES.find((e) => e.id === payload.entityId);
        if (entity) setSelectedEntity(entity);
        break;
      }
      case 'ask':
        chat.setInput(payload.query);
        break;
    }
  };

  // Attach onAction to chat so components can access it
  chat.onAction = handleAction;

  // Dismiss notification on route change
  const prevRoute = useRef(activeId);
  useEffect(() => {
    if (activeId !== prevRoute.current) {
      setShowMergeNotif(false);
      prevRoute.current = activeId;
    }
  }, [activeId]);

  // Auto-dismiss notification after 10 seconds
  useEffect(() => {
    if (!showMergeNotif) return;
    const t = setTimeout(() => setShowMergeNotif(false), 10000);
    return () => clearTimeout(t);
  }, [showMergeNotif]);

  // Connect WebSocket on mount
  useEffect(() => {
    wsManager.connect();
    return () => wsManager.disconnect();
  }, []);

  const goTo = (id, entity) => {
    setSelectedEntity(entity || ENTITIES[0]);
    navigate(viewToPath[id] || '/');
    setAiOpen(false);
  };

  return (
    <div className="flex h-screen overflow-hidden" style={{ backgroundColor: QB.contentBg }}>
      {/* ── SIDEBAR ── */}
      <div className="flex shrink-0">
        {/* Icon rail */}
        <div className="sidebar-rail">
          <div className="w-9 h-9 rounded-full flex items-center justify-center mb-3 overflow-hidden">
            <img src="/logo.png" alt="Logo" className="w-full h-full object-cover" />
          </div>
          {ROUTES.map((route) => (
            <button
              key={route.id}
              onClick={() => goTo(route.id)}
              className="relative w-10 h-10 rounded flex items-center justify-center transition-colors"
              style={{
                backgroundColor: activeId === route.id ? QB.sidebarActive : 'transparent',
                color: activeId === route.id ? 'white' : '#8B949E',
              }}
              title={route.label}
            >
              {SIDEBAR_ICONS[route.id]}
              {route.id === 'review' && (
                <span className="absolute -top-0.5 -right-0.5 w-4 h-4 rounded-full text-white text-[9px] flex items-center justify-center font-bold" style={{ backgroundColor: QB.orange }}>
                  {PENDING_MATCHES.length}
                </span>
              )}
            </button>
          ))}
        </div>

        {/* Secondary text panel */}
        <div className={`sidebar-panel flex flex-col${sidebarCollapsed ? ' collapsed' : ''}`}>
          <div className="text-xs font-semibold px-2 py-1.5 mb-1" style={{ color: QB.green }}>Business network</div>
          {ROUTES.map((route) => (
            <button
              key={route.id}
              onClick={() => goTo(route.id)}
              className={'sidebar-item' + (activeId === route.id ? ' active' : '')}
            >
              {route.id === 'assist' && <Sparkles size={12} />}
              {route.label}
            </button>
          ))}
        </div>
      </div>

      {/* ── MAIN AREA ── */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Top bar */}
        <header className="topbar">
          <div className="flex items-center gap-3">
            <Menu size={18} style={{ color: QB.textMuted }} className="cursor-pointer" onClick={() => setSidebarCollapsed(!sidebarCollapsed)} />
          </div>
          <div className="flex items-center gap-3">
            <button
              onClick={() => setAiOpen(!aiOpen)}
              className="flex items-center gap-1.5 text-xs px-2.5 py-1.5 rounded transition-colors"
              style={{ backgroundColor: aiOpen ? QB.greenLight : 'transparent', color: aiOpen ? QB.greenDark : QB.textMuted }}
            >
              <Sparkles size={13} /> Intuit Assist
            </button>
            <div className="flex items-center gap-2 text-xs" style={{ color: QB.textMuted }}>
              Privacy
              <button onClick={() => setPrivacy(!privacy)} className="w-9 h-5 rounded-full relative transition-colors" style={{ backgroundColor: privacy ? QB.green : '#D0D5DD' }}>
                <span className="absolute top-0.5 w-4 h-4 rounded-full bg-white shadow transition-transform" style={{ left: privacy ? '18px' : '2px' }} />
              </button>
            </div>
          </div>
        </header>

        {showMergeNotif && <MergeNotification onDismiss={() => setShowMergeNotif(false)} />}

        {/* Page content via React Router Outlet */}
        <main className="flex-1 min-h-0 overflow-hidden">
          <Outlet context={{ selectedEntity, setSelectedEntity, privacy, chat, goTo }} />
        </main>
      </div>

      {/* AI slide-over panel */}
      {activeId !== 'assist' && aiOpen && <div className="fixed inset-0 bg-black/10 z-40" onClick={() => setAiOpen(false)} />}
      {activeId !== 'assist' && (
        <AIPanel
          open={aiOpen && activeId !== 'assist'}
          onClose={() => setAiOpen(false)}
          chat={chat}
          onGoFullPage={() => goTo('assist')}
        />
      )}
    </div>
  );
}
