import { useState, useEffect } from 'react';
import { Sparkles, Plus, MessageSquare, ChevronLeft } from 'lucide-react';
import { QB } from '@/constants/colors';
import { ACME_ENTITY } from '@/config/env';
import { AIChatMessages, AIChatInput } from '@/components/shared';

function timeAgo(dateStr) {
  if (!dateStr) return '';
  const d = new Date(dateStr);
  const now = new Date();
  const sec = Math.floor((now - d) / 1000);
  if (sec < 60) return 'Just now';
  if (sec < 3600) { const m = Math.floor(sec / 60); return `${m}m ago`; }
  if (sec < 86400) { const h = Math.floor(sec / 3600); return `${h}h ago`; }
  const days = Math.floor(sec / 86400);
  if (days < 7) return `${days}d ago`;
  return d.toLocaleDateString();
}

export default function AssistPage({ chat, onResetEntity }) {
  const [sidebarOpen, setSidebarOpen] = useState(false);

  useEffect(() => {
    if (sidebarOpen) chat.refreshSessions();
  }, [sidebarOpen]); // eslint-disable-line react-hooks/exhaustive-deps

  const handleSwitchSession = (sessionId) => {
    chat.switchSession(sessionId);
    setSidebarOpen(false);
  };

  const handleNewSession = () => {
    chat.newSession();
    setSidebarOpen(false);
    onResetEntity?.(ACME_ENTITY);
  };

  return (
    <div className="flex h-full">
      {/* Session history sidebar */}
      <div
        className="border-r bg-white flex flex-col transition-all duration-200 overflow-hidden"
        style={{
          width: sidebarOpen ? 260 : 0,
          minWidth: sidebarOpen ? 260 : 0,
          borderColor: QB.cardBorder,
        }}
      >
        <div className="px-3 py-3 border-b flex items-center justify-between" style={{ borderColor: QB.cardBorder }}>
          <span className="text-xs font-semibold uppercase tracking-wide" style={{ color: QB.textMuted }}>
            History
          </span>
          <button
            onClick={handleNewSession}
            className="flex items-center gap-1 text-[11px] px-2 py-1 rounded font-medium transition-colors hover:shadow-sm"
            style={{ backgroundColor: QB.greenLight, color: QB.green }}
          >
            <Plus size={11} /> New chat
          </button>
        </div>
        <div className="flex-1 overflow-y-auto">
          {chat.sessions.length === 0 && (
            <div className="px-3 py-6 text-center text-xs" style={{ color: QB.textMuted }}>
              No previous conversations
            </div>
          )}
          {chat.sessions.map((s) => {
            const isActive = s.session_id === chat.activeSessionId;
            return (
              <button
                key={s.session_id}
                onClick={() => handleSwitchSession(s.session_id)}
                className="w-full text-left px-3 py-2.5 border-b transition-colors hover:bg-gray-50"
                style={{
                  borderColor: QB.cardBorder,
                  backgroundColor: isActive ? QB.greenLight : undefined,
                }}
              >
                <div className="flex items-start gap-2">
                  <MessageSquare
                    size={13}
                    className="mt-0.5 flex-shrink-0"
                    style={{ color: isActive ? QB.green : QB.textMuted }}
                  />
                  <div className="min-w-0 flex-1">
                    <div
                      className="text-xs font-medium truncate"
                      style={{ color: isActive ? QB.green : QB.textPrimary }}
                    >
                      {s.title || 'Untitled conversation'}
                    </div>
                    <div className="flex items-center gap-2 mt-0.5">
                      <span className="text-[10px]" style={{ color: QB.textMuted }}>
                        {s.message_count} msg{s.message_count !== 1 ? 's' : ''}
                      </span>
                      <span className="text-[10px]" style={{ color: QB.textMuted }}>
                        {timeAgo(s.updated_at)}
                      </span>
                    </div>
                  </div>
                </div>
              </button>
            );
          })}
        </div>
      </div>

      {/* Main chat area */}
      <div className="flex flex-col flex-1 min-w-0">
        <div className="px-6 py-4 border-b bg-white" style={{ borderColor: QB.cardBorder }}>
          <div className="flex items-center gap-3">
            <button
              onClick={() => setSidebarOpen((v) => !v)}
              className="w-9 h-9 rounded-full flex items-center justify-center transition-colors hover:bg-gray-100"
              style={{ backgroundColor: sidebarOpen ? QB.greenLight : '#F3F4F6' }}
              title={sidebarOpen ? 'Hide history' : 'Show history'}
            >
              {sidebarOpen
                ? <ChevronLeft size={16} style={{ color: QB.green }} />
                : <Sparkles size={18} style={{ color: QB.green }} />
              }
            </button>
            <div className="flex-1">
              <div className="flex items-center gap-2">
                <h1 className="text-xl font-normal" style={{ color: QB.textPrimary }}>Intuit Assist</h1>
                <span
                  className="flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded-full font-medium"
                  style={{
                    backgroundColor: chat.connected ? QB.greenLight : '#FEE2E2',
                    color: chat.connected ? QB.green : QB.red,
                  }}
                >
                  <span
                    className="w-1.5 h-1.5 rounded-full"
                    style={{ backgroundColor: chat.connected ? QB.green : QB.red }}
                  />
                  {chat.connected ? 'Connected' : 'Disconnected'}
                </span>
              </div>
              <p className="text-xs" style={{ color: QB.textMuted }}>
                {chat.sessionTitle || 'Network intelligence \u00B7 Natural language queries across your business graph'}
              </p>
            </div>
            <button
              onClick={handleNewSession}
              className="flex items-center gap-1.5 text-xs px-3 py-2 rounded font-medium transition-colors hover:shadow-sm"
              style={{ backgroundColor: QB.greenLight, color: QB.green }}
            >
              <Plus size={11} /> New chat
            </button>
          </div>
        </div>
        <div className="flex-1 flex flex-col min-h-0 max-w-3xl w-full mx-auto">
          <AIChatMessages msgs={chat.msgs} typing={chat.typing} tools={chat.tools} onSetInput={chat.setInput} suggestions={chat.suggestions} context={chat.context} onAction={chat.onAction} />
          <AIChatInput input={chat.input} setInput={chat.setInput} send={chat.send} />
        </div>
      </div>
    </div>
  );
}
