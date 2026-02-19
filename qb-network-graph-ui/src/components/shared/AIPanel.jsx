import { X, ArrowLeft, Sparkles } from 'lucide-react';
import { QB } from '@/constants/colors';
import { AIChatMessages } from './AIChatMessages';
import { AIChatInput } from './AIChatInput';

export function AIPanel({ open, onClose, chat, onGoFullPage }) {
  return (
    <div
      className={'ai-panel ' + (open ? 'open' : 'closed')}
    >
      <div className="flex items-center justify-between px-4 py-3 border-b" style={{ borderColor: QB.cardBorder, backgroundColor: '#F9FAFB' }}>
        <div className="flex items-center gap-2">
          <div className="w-7 h-7 rounded flex items-center justify-center" style={{ backgroundColor: QB.greenLight }}>
            <Sparkles size={14} style={{ color: QB.green }} />
          </div>
          <div>
            <div className="text-sm font-medium" style={{ color: QB.textPrimary }}>Intuit Assist</div>
            <div className="text-[10px]" style={{ color: QB.textMuted }}>Network intelligence</div>
          </div>
        </div>
        <div className="flex items-center gap-1">
          <button
            onClick={() => { onClose(); onGoFullPage(); }}
            className="p-1.5 rounded hover:bg-gray-100"
            title="Open full page"
            style={{ color: QB.textMuted }}
          >
            <ArrowLeft size={14} style={{ transform: 'rotate(135deg)' }} />
          </button>
          <button onClick={onClose} className="p-1.5 rounded hover:bg-gray-100">
            <X size={16} style={{ color: QB.textMuted }} />
          </button>
        </div>
      </div>
      <AIChatMessages msgs={chat.msgs} typing={chat.typing} tools={chat.tools} onSetInput={chat.setInput} />
      <AIChatInput input={chat.input} setInput={chat.setInput} send={chat.send} />
    </div>
  );
}
