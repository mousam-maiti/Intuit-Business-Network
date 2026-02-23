import { useState, useCallback, useMemo, useEffect, useRef } from 'react';
import { config } from '@/config/env';
import { generateMockResponse, getSuggestions } from '@/api/mock/aiResponses';

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

function getUserId() {
  return config.currentEntityId || 'user-1';
}

/**
 * Shared hook for AI chat state — used by both AssistPage and AIPanel.
 *
 * When `useMocks` is false, connects to the conversational agent WebSocket
 * at ws://localhost:8082/ws/{session_id}?user_id={user_id}.
 * When `useMocks` is true, uses the mock response generator.
 */
export function useAIChat(selectedEntity, currentPage) {
  const [msgs, setMsgs] = useState([]);
  const [input, setInput] = useState('');
  const [typing, setTyping] = useState(false);
  const [tools, setTools] = useState([]);
  const [sessionTitle, setSessionTitle] = useState(null);

  const wsRef = useRef(null);
  const reconnectTimer = useRef(null);
  const pingTimer = useRef(null);

  const suggestions = useMemo(
    () => getSuggestions(selectedEntity, currentPage),
    [selectedEntity, currentPage]
  );

  const context = useMemo(() => {
    if (!selectedEntity) return null;
    return { entityName: selectedEntity.name, page: currentPage };
  }, [selectedEntity, currentPage]);

  // ── WebSocket lifecycle (non-mock mode) ─────────────────
  const connectWs = useCallback(() => {
    if (config.flags.useMocks) return;

    const sid = getSessionId();
    const uid = getUserId();
    const url = `${config.api.chatWsUrl}/${sid}?user_id=${uid}`;

    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => {
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
            // Replace if same tool already exists (running → done), else append
            const idx = prev.findIndex((t) => t.name === data.name && t.status === 'running');
            if (data.status === 'done' || data.status === 'error') {
              if (idx >= 0) {
                const copy = [...prev];
                copy[idx] = { name: data.name, label: data.label, status: data.status };
                return copy;
              }
              return [...prev, { name: data.name, label: data.label, status: data.status }];
            }
            return [...prev, { name: data.name, label: data.label }];
          });
          break;

        case 'response':
          setTyping(false);
          setTools([]);
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
          break;

        case 'error':
          setTyping(false);
          setTools([]);
          setMsgs((prev) => [...prev, {
            role: 'ai',
            content: data.message || 'Sorry, something went wrong. Please try again.',
          }]);
          break;

        case 'context_cleared':
          setMsgs([]);
          setTools([]);
          setTyping(false);
          break;

        case 'pong':
          break; // keepalive ack

        default:
          break;
      }
    };

    ws.onclose = () => {
      clearInterval(pingTimer.current);
      // Reconnect after 3s unless we intentionally closed
      if (wsRef.current) {
        reconnectTimer.current = setTimeout(connectWs, 3000);
      }
    };

    ws.onerror = () => {
      // onclose will fire after onerror, triggering reconnect
    };
  }, []);

  // Connect on mount, disconnect on unmount
  useEffect(() => {
    if (!config.flags.useMocks) {
      connectWs();
    }
    return () => {
      clearTimeout(reconnectTimer.current);
      clearInterval(pingTimer.current);
      if (wsRef.current) {
        const ws = wsRef.current;
        wsRef.current = null; // prevent reconnect
        ws.close();
      }
    };
  }, [connectWs]);

  // ── Send message ────────────────────────────────────────
  const send = useCallback(async () => {
    if (!input.trim()) return;
    const userMsg = input;
    setMsgs((p) => [...p, { role: 'user', content: userMsg }]);
    setInput('');
    setTyping(true);
    setTools([]);

    if (config.flags.useMocks) {
      // Mock mode — unchanged
      const mockCtx = { selectedEntity, currentPage };
      const { tools: mockTools, response } = generateMockResponse(userMsg, mockCtx);

      let i = 0;
      const iv = setInterval(() => {
        if (i < mockTools.length) {
          const tool = mockTools[i];
          i++;
          setTools((p) => [...p, tool]);
        } else {
          clearInterval(iv);
          setTimeout(() => {
            setTyping(false);
            setTools([]);
            setMsgs((p) => [...p, { role: 'ai', ...response }]);
          }, 600);
        }
      }, 700);
    } else {
      // WebSocket mode — send message to conversational agent
      const ws = wsRef.current;
      if (!ws || ws.readyState !== WebSocket.OPEN) {
        setTyping(false);
        setMsgs((p) => [...p, {
          role: 'ai',
          content: 'Connection lost. Reconnecting...',
        }]);
        connectWs();
        return;
      }

      ws.send(JSON.stringify({
        type: 'message',
        content: userMsg,
        context: selectedEntity ? { selectedEntity, currentPage } : undefined,
      }));
      // Response arrives via ws.onmessage → tool_call* → response
    }
  }, [input, selectedEntity, currentPage, connectWs]);

  // ── Clear chat ──────────────────────────────────────────
  const clear = useCallback(() => {
    if (!config.flags.useMocks) {
      // Send clear_context over WebSocket
      const ws = wsRef.current;
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: 'clear_context' }));
        return; // state will be cleared when we receive context_cleared event
      }
    }
    // Mock mode or WS not connected — clear locally
    setMsgs([]);
    setInput('');
    setTyping(false);
    setTools([]);
  }, []);

  return { msgs, input, setInput, typing, tools, send, suggestions, context, clear, sessionTitle };
}
