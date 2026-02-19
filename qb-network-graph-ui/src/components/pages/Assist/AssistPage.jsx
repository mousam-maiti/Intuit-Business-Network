import { Sparkles } from 'lucide-react';
import { QB } from '@/constants/colors';
import { AIChatMessages, AIChatInput } from '@/components/shared';

export default function AssistPage({ chat }) {
  return (
    <div className="flex flex-col h-full">
      <div className="px-6 py-4 border-b bg-white" style={{ borderColor: QB.cardBorder }}>
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-full flex items-center justify-center" style={{ backgroundColor: QB.greenLight }}>
            <Sparkles size={18} style={{ color: QB.green }} />
          </div>
          <div>
            <h1 className="text-xl font-normal" style={{ color: QB.textPrimary }}>Intuit Assist</h1>
            <p className="text-xs" style={{ color: QB.textMuted }}>Network intelligence &middot; Natural language queries across your business graph</p>
          </div>
        </div>
      </div>
      <div className="flex-1 flex flex-col min-h-0 max-w-3xl w-full mx-auto">
        <AIChatMessages msgs={chat.msgs} typing={chat.typing} tools={chat.tools} onSetInput={chat.setInput} />
        <AIChatInput input={chat.input} setInput={chat.setInput} send={chat.send} />
      </div>
    </div>
  );
}
