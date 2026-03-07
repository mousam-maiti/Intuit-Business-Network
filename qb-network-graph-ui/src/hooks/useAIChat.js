import { useState, useCallback, useMemo, useEffect, useRef } from 'react';
import { config } from '@/config/env';
import { listSessions, getSessionMessages } from '@/api/chat';

/**
 * Generate contextual chat suggestions based on entity + page.
 */
function getSuggestions(entity, page) {
  const name = entity?.name || 'this entity';
  const base = [
    `Summarize ${name}`,
    `What risks are associated with ${name}?`,
  ];
  switch (page) {
    case 'network':
      return [...base, `Show key connections for ${name}`, 'Which vendors overlap?'];
    case 'search':
      return [...base, 'Find similar entities', 'Search by industry'];
    case 'connections':
      return [...base, `What new connections were detected for ${name}?`, 'Show manual connections'];
    case 'review':
      return [...base, 'Show pending matches', 'Explain matching confidence'];
    default:
      return [...base, 'Show dashboard summary', 'Any anomalies today?'];
  }
}

/**
 * Generate a session ID and persist it in sessionStorage so
 * refreshes keep the same session until the tab closes.
 */
function getSessionId() {
  let sid = sessionStorage.getItem('chat_session_id');
  if (!sid) {
    sid = crypto.randomUUID?.() || `s-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
    sessionStorage.setItem('chat_session_id', sid);
  }
  return sid;
}

function setSessionId(sid) {
  sessionStorage.setItem('chat_session_id', sid);
}

function getUserId() {
  return config.currentEntityId || 'user-1';
}

/**
 * Shared hook for AI chat state — used by both AssistPage and AIPanel.
 *
 * Connects to the conversational agent WebSocket
 * at ws://localhost:8082/ws/{session_id}?user_id={user_id}.
 */
export function useAIChat(selectedEntity, currentPage) {
  const [msgs, setMsgs] = useState([]);
  const [input, setInput] = useState('');
  const [typing, setTyping] = useState(false);
  const [tools, setTools] = useState([]);
  const [thoughts, setThoughts] = useState([]);
  const [sessionTitle, setSessionTitle] = useState(null);
  const [connected, setConnected] = useState(false);
  const [sessions, setSessions] = useState([]);
  const [activeSessionId, setActiveSessionId] = useState(getSessionId());

  const wsRef = useRef(null);
  const reconnectTimer = useRef(null);
  const pingTimer = useRef(null);
  const historyLoaded = useRef(false);
  const activeSessionRef = useRef(activeSessionId);
  const connectWsRef = useRef(null);

  const suggestions = useMemo(
    () => getSuggestions(selectedEntity, currentPage),
    [selectedEntity, currentPage]
  );

  const context = useMemo(() => {
    if (!selectedEntity) return null;
    return { entityName: selectedEntity.name, page: currentPage };
  }, [selectedEntity, currentPage]);

  // ── Load session list ────────────────────────────────────
  const refreshSessions = useCallback(async () => {
    try {
      const res = await listSessions(getUserId());
      setSessions(res.data || []);
    } catch {
      // silently fail
    }
  }, []);

  // ── Restore history from backend ─────────────────────────
  const loadHistory = useCallback(async (sessionId) => {
    try {
      const res = await getSessionMessages(sessionId);
      const messages = (res.data || []).map((m) => {
        const msg = {
          role: m.role === 'assistant' ? 'ai' : m.role,
          content: m.content,
        };
        // Restore rich payload from metadata (entities, table, chart, scores, etc.)
        if (m.role === 'assistant' && m.metadata) {
          const md = typeof m.metadata === 'string' ? JSON.parse(m.metadata) : m.metadata;
          if (md.entities) msg.entities = md.entities;
          if (md.table) msg.table = md.table;
          if (md.chart) msg.chart = md.chart;
          if (md.scores) msg.scores = md.scores;
          if (md.signals) msg.signals = md.signals;
          if (md.actions) msg.actions = md.actions;
          if (md.followup) msg.followup = md.followup;
        }
        return msg;
      });
      if (messages.length > 0) {
        setMsgs(messages);
      }
    } catch {
      // no history available
    }
  }, []);

  // ── WebSocket lifecycle ─────────────────────────────────
  const connectWs = useCallback((sessionId) => {
    // Close existing connection
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
    clearTimeout(reconnectTimer.current);
    clearInterval(pingTimer.current);

    const sid = sessionId || getSessionId();
    activeSessionRef.current = sid;

    const uid = getUserId();
    const url = `${config.api.chatWsUrl}/${sid}?user_id=${uid}`;

    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => {
      setConnected(true);
      // Restore history on first connect for this session
      if (!historyLoaded.current) {
        historyLoaded.current = true;
        loadHistory(sid);
      }
      // Refresh session list
      refreshSessions();
      // Start keepalive pings every 30s
      pingTimer.current = setInterval(() => {
        if (ws.readyState === WebSocket.OPEN) {
          ws.send(JSON.stringify({ type: 'ping' }));
        }
      }, 30000);
    };

    ws.onmessage = (event) => {
      let data;
      try { data = JSON.parse(event.data); } catch { return; }

      switch (data.type) {
        case 'session_info':
          if (data.title) setSessionTitle(data.title);
          break;

        case 'tool_call':
          setTools((prev) => {
            if (data.status === 'done' || data.status === 'error') {
              // Find the last "running" entry for this tool and replace it
              const idx = prev.findLastIndex((t) => t.name === data.name && t.status === 'running');
              if (idx >= 0) {
                const copy = [...prev];
                copy[idx] = { name: data.name, label: data.label, status: data.status };
                return copy;
              }
              return [...prev, { name: data.name, label: data.label, status: data.status }];
            }
            return [...prev, { name: data.name, label: data.label, status: 'running' }];
          });
          break;

        case 'thought':
          setThoughts(prev => [...prev, { text: data.text, step: data.step }]);
          break;

        case 'response':
          setTyping(false);
          setTools([]);
          setThoughts([]);
          setMsgs((prev) => [...prev, {
            role: 'ai',
            content: data.content || '',
            entities: data.entities,
            table: data.table,
            chart: data.chart,
            scores: data.scores,
            signals: data.signals,
            actions: data.actions,
            followup: data.followup,
          }]);
          // Refresh sessions to update message count / title
          refreshSessions();
          break;

        case 'error':
          setTyping(false);
          setTools([]);
          setThoughts([]);
          setMsgs((prev) => [...prev, {
            role: 'ai',
            content: data.message || 'Sorry, something went wrong. Please try again.',
          }]);
          break;

        case 'context_cleared':
          setMsgs([]);
          setTools([]);
          setThoughts([]);
          setTyping(false);
          break;

        case 'pong':
          break; // keepalive ack

        default:
          break;
      }
    };

    ws.onclose = () => {
      setConnected(false);
      clearInterval(pingTimer.current);
      // Only reconnect if this ws is still the active one (not replaced by a newer connection)
      if (wsRef.current === ws) {
        const currentSid = activeSessionRef.current;
        reconnectTimer.current = setTimeout(() => connectWsRef.current(currentSid), 3000);
      }
    };

    ws.onerror = () => {
      // onclose will fire after onerror, triggering reconnect
    };
  }, [loadHistory, refreshSessions]);

  // Keep ref to latest connectWs for reconnect timer and mount effect
  connectWsRef.current = connectWs;

  // Connect on mount, disconnect on unmount
  useEffect(() => {
    connectWsRef.current(activeSessionId);
    return () => {
      clearTimeout(reconnectTimer.current);
      clearInterval(pingTimer.current);
      if (wsRef.current) {
        const ws = wsRef.current;
        wsRef.current = null; // prevents reconnect since onclose checks wsRef.current === ws
        ws.close();
      }
    };
  }, []);  // eslint-disable-line react-hooks/exhaustive-deps

  // ── Switch session ───────────────────────────────────────
  const switchSession = useCallback(async (sessionId) => {
    // Clear current state
    setMsgs([]);
    setTools([]);
    setThoughts([]);
    setTyping(false);
    setSessionTitle(null);
    historyLoaded.current = false;

    // Update session ID
    setSessionId(sessionId);
    setActiveSessionId(sessionId);

    // Reconnect WS to the new session
    connectWs(sessionId);
  }, [connectWs]);

  // ── New session ──────────────────────────────────────────
  const newSession = useCallback(() => {
    const sid = crypto.randomUUID?.() || `s-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
    switchSession(sid);
  }, [switchSession]);

  // ── Send message ────────────────────────────────────────
  const send = useCallback(async () => {
    if (!input.trim()) return;
    const userMsg = input;
    setMsgs((p) => [...p, { role: 'user', content: userMsg }]);
    setInput('');
    setTyping(true);
    setTools([]);
    setThoughts([]);

    // WebSocket mode — send message to conversational agent
    const ws = wsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) {
      setTyping(false);
      setMsgs((p) => [...p, {
        role: 'ai',
        content: 'Connection lost. Reconnecting...',
      }]);
      connectWs(activeSessionId);
      return;
    }

    ws.send(JSON.stringify({
      type: 'message',
      content: userMsg,
      context: selectedEntity ? { selectedEntity, currentPage } : undefined,
    }));
    // Response arrives via ws.onmessage → tool_call* → response
  }, [input, selectedEntity, currentPage, connectWs, activeSessionId]);

  // ── Clear chat ──────────────────────────────────────────
  const clear = useCallback(() => {
    // Send clear_context over WebSocket
    const ws = wsRef.current;
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: 'clear_context' }));
      return; // state will be cleared when we receive context_cleared event
    }
    // WS not connected — clear locally
    setMsgs([]);
    setInput('');
    setTyping(false);
    setTools([]);
  }, []);

  return {
    msgs, input, setInput, typing, tools, thoughts, send, suggestions, context,
    clear, sessionTitle, connected,
    sessions, activeSessionId, switchSession, newSession, refreshSessions,
  };
}
