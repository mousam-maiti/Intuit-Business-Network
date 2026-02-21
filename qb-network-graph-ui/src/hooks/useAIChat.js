import { useState, useCallback, useMemo } from 'react';
import { aiApi } from '@/api';
import { config } from '@/config/env';
import { generateMockResponse, getSuggestions } from '@/api/mock/aiResponses';

/**
 * Shared hook for AI chat state — used by both AssistPage and AIPanel.
 * Manages messages, input, typing animation, and tool call sequence.
 */
export function useAIChat(selectedEntity, currentPage) {
  const [msgs, setMsgs] = useState([]);
  const [input, setInput] = useState('');
  const [typing, setTyping] = useState(false);
  const [tools, setTools] = useState([]);

  const suggestions = useMemo(
    () => getSuggestions(selectedEntity, currentPage),
    [selectedEntity, currentPage]
  );

  const context = useMemo(() => {
    if (!selectedEntity) return null;
    return { entityName: selectedEntity.name, page: currentPage };
  }, [selectedEntity, currentPage]);

  const send = useCallback(async () => {
    if (!input.trim()) return;
    const userMsg = input;
    setMsgs((p) => [...p, { role: 'user', content: userMsg }]);
    setInput('');
    setTyping(true);
    setTools([]);

    if (config.flags.useMocks) {
      const mockCtx = { selectedEntity, currentPage };
      const { tools: mockTools, response } = generateMockResponse(userMsg, mockCtx);

      // Animate tool calls one by one
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
      try {
        const res = await aiApi.sendAIQuery(userMsg, { selectedEntity, currentPage });
        setTyping(false);
        setMsgs((p) => [...p, { role: 'ai', ...res.data.response }]);
      } catch {
        setTyping(false);
        setMsgs((p) => [...p, { role: 'ai', content: 'Sorry, something went wrong. Please try again.' }]);
      }
    }
  }, [input, selectedEntity, currentPage]);

  const clear = useCallback(() => {
    setMsgs([]);
    setInput('');
    setTyping(false);
    setTools([]);
  }, []);

  return { msgs, input, setInput, typing, tools, send, suggestions, context, clear };
}
