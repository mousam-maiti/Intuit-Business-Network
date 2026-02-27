import { useState, useEffect } from 'react';
import { Outlet, useNavigate, useLocation } from 'react-router-dom';
import {
  Search, Home, Globe, ClipboardCheck, Sparkles,
  Menu, Building2, History,
} from 'lucide-react';
import { QB } from '@/constants/colors';
import { ROUTES, viewToPath } from '@/config/routes';
import { ACME_ENTITY, config } from '@/config/env';
import { getPendingMatches } from '@/api/matching';
import { getEntity } from '@/api/entities';
import { getAlerts, dismissAlert } from '@/api/alerts';
import { useAIChat } from '@/hooks/useAIChat';
import { AIPanel, AlertBanner } from '@/components/shared';
import { wsManager } from '@/api/websocket';

const SIDEBAR_ICONS = {
  dashboard: <Home size={18} />,
  network: <Globe size={18} />,
  search: <Search size={18} />,
  review: <ClipboardCheck size={18} />,
  lineage: <History size={18} />,
  assist: <Sparkles size={18} />,
};

export default function AppLayout() {
  const navigate = useNavigate();
  const location = useLocation();

  const [aiOpen, setAiOpen] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [selectedEntity, setSelectedEntity] = useState(ACME_ENTITY);
  const [alerts, setAlerts] = useState([]);
  const [pendingCount, setPendingCount] = useState(0);

  useEffect(() => {
    getPendingMatches().then(r => setPendingCount(r.data.length)).catch(() => {});
  }, []);

  useEffect(() => {
    getEntity(config.currentEntityId).then(r => {
      if (r.data) setSelectedEntity(r.data);
    }).catch(() => {});
  }, []);

  // Poll alerts every 5 seconds
  useEffect(() => {
    const fetchAlerts = () => {
      getAlerts().then(r => {
        const newAlerts = r.data || [];
        setAlerts(newAlerts);
        // Refresh pending count when a merge_review alert arrives
        if (newAlerts.some(a => a.type === 'merge_review')) {
          getPendingMatches().then(r2 => setPendingCount(r2.data.length)).catch(() => {});
        }
      }).catch(() => {});
    };
    fetchAlerts();
    const interval = setInterval(fetchAlerts, 5000);
    return () => clearInterval(interval);
  }, []);

  // Current active route id — computed before useAIChat so it can be passed as context
  const activeId = ROUTES.find((r) => r.path === location.pathname)?.id || 'dashboard';

  const chat = useAIChat(selectedEntity, activeId);

  const handleAction = (action, payload = {}) => {
    // Normalize payload keys — LLM may send snake_case or camelCase
    const page = payload.page || payload.view || '';
    const entityId = payload.entityId || payload.entity_id || '';
    const entityName = payload.entityName || payload.entity_name || payload.name || '';
    const query = payload.query || payload.question || '';

    switch (action) {
      case 'navigate': {
        // Match against route IDs or paths
        const path = viewToPath[page] || viewToPath[page.toLowerCase().replace(/[\s_]/g, '')] ||
          ROUTES.find(r => r.label.toLowerCase().includes(page.toLowerCase()))?.path || '/';
        navigate(path);
        setAiOpen(false);
        break;
      }
      case 'select_entity': {
        if (entityId) {
          navigate(viewToPath.network || '/network');
          setAiOpen(false);
          getEntity(entityId).then(r => {
            if (r.data) setSelectedEntity(r.data);
            else setSelectedEntity({ id: entityId, name: entityName || entityId });
          }).catch(() => {
            setSelectedEntity({ id: entityId, name: entityName || entityId });
          });
        }
        break;
      }
      case 'ask':
        chat.setInput(query);
        break;
    }
  };

  // Attach onAction to chat so components can access it
  chat.onAction = handleAction;

  const handleDismissAlert = (id) => {
    setAlerts(prev => prev.filter(a => a.id !== id));
    dismissAlert(id).catch(() => {});
  };

  const handleAlertAction = (alert) => {
    if (alert.type === 'merge_review') {
      navigate('/review');
      handleDismissAlert(alert.id);
    }
  };

  // Connect WebSocket on mount
  useEffect(() => {
    wsManager.connect();
    return () => wsManager.disconnect();
  }, []);

  const goTo = (id, entity) => {
    setSelectedEntity(entity || ACME_ENTITY);
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
                  {pendingCount}
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
            <div className="flex items-center gap-1.5 text-xs font-medium px-2.5 py-1.5 rounded" style={{ backgroundColor: QB.greenLight, color: QB.greenDark }}>
              <Building2 size={13} />
              {config.currentEntityName}
            </div>
          </div>
        </header>

        {alerts.map(a => (
          <AlertBanner key={a.id} alert={a} onDismiss={handleDismissAlert} onAction={handleAlertAction} />
        ))}

        {/* Page content via React Router Outlet */}
        <main className="flex-1 min-h-0 overflow-hidden">
          <Outlet context={{ selectedEntity, setSelectedEntity, chat, goTo }} />
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
