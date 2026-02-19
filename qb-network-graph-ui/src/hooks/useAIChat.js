import { useState, useCallback } from 'react';
import { aiApi } from '@/api';
import { AI_TOOLS } from '@/api/mock/data';
import { config } from '@/config/env';

/**
 * Shared hook for AI chat state — used by both AssistPage and AIPanel.
 * Manages messages, input, typing animation, and tool call sequence.
 */
export function useAIChat() {
  const [msgs, setMsgs] = useState([]);
  const [input, setInput] = useState('');
  const [typing, setTyping] = useState(false);
  const [tools, setTools] = useState([]);

  const send = useCallback(async () => {
    if (!input.trim()) return;
    const userMsg = input;
    setMsgs((p) => [...p, { role: 'user', content: userMsg }]);
    setInput('');
    setTyping(true);
    setTools([]);

    if (config.flags.useMocks) {
      // Animate tool calls one by one
      let i = 0;
      const iv = setInterval(() => {
        if (i < AI_TOOLS.length) {
          setTools((p) => [...p, AI_TOOLS[i]]);
          i++;
        } else {
          clearInterval(iv);
          setTimeout(() => {
            setTyping(false);
            setTools([]);
            setMsgs((p) => [
              ...p,
              {
                role: 'ai',
                content: 'I found 3 vendors that also serve businesses competing with you:',
                entities: ['e3', 'e6', 'e7'],
                followup: 'Metro Supplies Direct has the highest overlap \u2014 they serve both you and BuildRight Inc across 4 commodity categories.',
              },
            ]);
          }, 600);
        }
      }, 700);
    } else {
      try {
        const res = await aiApi.sendAIQuery(userMsg);
        setTyping(false);
        setMsgs((p) => [...p, { role: 'ai', ...res.data.response }]);
      } catch {
        setTyping(false);
        setMsgs((p) => [...p, { role: 'ai', content: 'Sorry, something went wrong. Please try again.' }]);
      }
    }
  }, [input]);

  return { msgs, input, setInput, typing, tools, send };
}
