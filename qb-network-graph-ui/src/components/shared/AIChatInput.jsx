import { Send } from 'lucide-react';
import { QB } from '@/constants/colors';

export function AIChatInput({ input, setInput, send }) {
  return (
    <div className="p-4 border-t bg-white" style={{ borderColor: QB.cardBorder }}>
      <div className="flex gap-2">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && send()}
          placeholder="Ask about your network..."
          className="flex-1 px-4 py-2.5 rounded border text-sm focus:outline-none"
          style={{ borderColor: QB.cardBorder, color: QB.textPrimary }}
        />
        <button
          onClick={send}
          disabled={!input.trim()}
          className="px-4 py-2.5 rounded text-white text-sm disabled:opacity-30 flex items-center gap-1.5"
          style={{ backgroundColor: QB.green }}
        >
          <Send size={14} /> Send
        </button>
      </div>
      <div className="flex items-center gap-3 mt-2 text-[10px]" style={{ color: QB.textMuted }}>
        <span>Powered by 6 MCP tool servers</span>
        <span>&middot;</span>
        <span>Agent Gateway + LLM orchestration</span>
      </div>
    </div>
  );
}
