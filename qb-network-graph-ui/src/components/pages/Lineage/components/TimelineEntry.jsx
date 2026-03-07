import { useState } from 'react';
import { ChevronDown, ChevronRight, Clock, Zap, Brain, Cpu, RotateCcw } from 'lucide-react';
import { QB } from '@/constants/colors';
import { ScoreBar } from '@/components/shared';
import { DecisionBadge, getDecisionColor } from './DecisionBadge';
import { EvaluationChain } from './EvaluationChain';
import { FieldDiff } from './FieldDiff';

const TRIGGER_LABELS = {
  LAYER_1_EIN: 'EIN',
  AI_AGENT_EMBEDDING: 'Embedding',
  AI_AGENT_LLM: 'LLM',
  RE_EVALUATION: 'Re-eval',
};

const TRIGGER_ICONS = {
  LAYER_1_EIN: Zap,
  AI_AGENT_EMBEDDING: Cpu,
  AI_AGENT_LLM: Brain,
  RE_EVALUATION: Clock,
};

/**
 * Single timeline card with collapsed + expanded states.
 * Vertical line connector on the left edge.
 */
export function TimelineEntry({ entry, isExpanded, onToggle, onRestore, isFirst, isLast }) {
  const [openSection, setOpenSection] = useState(null);
  const dotColor = getDecisionColor(entry.decision);
  const TriggerIcon = TRIGGER_ICONS[entry.trigger_type] || Zap;
  const date = new Date(entry.created_at);

  const toggleSection = (section) => {
    setOpenSection((prev) => (prev === section ? null : section));
  };

  const hasFieldChanges = entry.golden_record_before || entry.golden_record_after;
  const hasDimensionScores = entry.dimension_scores && Object.values(entry.dimension_scores).some((v) => v > 0);
  const hasEvalChain = entry.evaluation_chain && entry.evaluation_chain.length > 0;

  return (
    <div className="flex gap-3 pb-4">
      {/* Vertical line + dot */}
      <div className="flex flex-col items-center shrink-0 w-4">
        {!isFirst && <div className="w-px" style={{ height: 8, backgroundColor: QB.cardBorder }} />}
        {isFirst && <div style={{ height: 8 }} />}
        <div className="w-3 h-3 rounded-full shrink-0" style={{ backgroundColor: dotColor }} />
        {!isLast && <div className="w-px flex-1" style={{ backgroundColor: QB.cardBorder }} />}
        {isLast && <div className="flex-1" />}
      </div>

      {/* Card */}
      <div
        className="flex-1 rounded-lg transition-shadow cursor-pointer"
        style={{
          backgroundColor: QB.cardBg,
          border: '1px solid ' + (isExpanded ? QB.green + '40' : QB.cardBorder),
          boxShadow: isExpanded ? '0 2px 8px rgba(0,0,0,0.06)' : 'none',
        }}
        onClick={onToggle}
      >
        {/* Collapsed header — always visible */}
        <div className="px-3 py-2.5">
          <div className="flex items-center gap-2 mb-1">
            <span className="text-[10px]" style={{ color: QB.textMuted }}>
              {date.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })}
              {' '}
              {date.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' })}
            </span>
            <DecisionBadge decision={entry.decision} />
            <span
              className="inline-flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded"
              style={{ backgroundColor: '#F0F1F3', color: QB.textSecondary }}
            >
              <TriggerIcon size={9} />
              {TRIGGER_LABELS[entry.trigger_type] || entry.trigger_type}
            </span>
            <span className="text-[11px] font-medium" style={{ color: entry.confidence >= 0.80 ? QB.green : entry.confidence >= 0.50 ? QB.orange : QB.textMuted }}>
              {Math.round(entry.confidence * 100)}%
            </span>
            <div className="flex-1" />
            {isExpanded ? <ChevronDown size={14} style={{ color: QB.textMuted }} /> : <ChevronRight size={14} style={{ color: QB.textMuted }} />}
          </div>

          {/* Reasoning text */}
          <div
            className={'text-[11px] leading-relaxed' + (isExpanded ? '' : ' line-clamp-2')}
            style={{ color: QB.textSecondary }}
          >
            {entry.reasoning}
          </div>

          {/* Key factor pills */}
          <div className="flex flex-wrap gap-1 mt-1.5">
            {(entry.key_factors || []).map((f, i) => (
              <span
                key={i}
                className="text-[10px] px-1.5 py-0.5 rounded"
                style={{ backgroundColor: QB.greenLight, color: QB.greenDark }}
              >
                {f}
              </span>
            ))}
          </div>
        </div>

        {/* Expanded sections */}
        {isExpanded && (
          <div className="border-t px-3 py-2" style={{ borderColor: QB.cardBorder }} onClick={(e) => e.stopPropagation()}>
            {/* Section toggles */}
            {hasDimensionScores && (
              <div className="mb-2">
                <button
                  className="flex items-center gap-1.5 text-[11px] font-medium w-full text-left py-1"
                  style={{ color: QB.textPrimary }}
                  onClick={() => toggleSection('scores')}
                >
                  {openSection === 'scores' ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
                  DIMENSION SCORES
                </button>
                {openSection === 'scores' && (
                  <div className="pl-5 space-y-1 mt-1">
                    <ScoreBar label="Identity" score={entry.dimension_scores.identity} />
                    <ScoreBar label="Industry" score={entry.dimension_scores.industry} />
                    <ScoreBar label="Location" score={entry.dimension_scores.location} />
                    <ScoreBar label="Commodity" score={entry.dimension_scores.commodity} />
                    <ScoreBar label="Behavioral" score={entry.dimension_scores.behavioral} />
                  </div>
                )}
              </div>
            )}

            {hasEvalChain && (
              <div className="mb-2">
                <button
                  className="flex items-center gap-1.5 text-[11px] font-medium w-full text-left py-1"
                  style={{ color: QB.textPrimary }}
                  onClick={() => toggleSection('chain')}
                >
                  {openSection === 'chain' ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
                  EVALUATION CHAIN ({entry.evaluation_chain.length} steps)
                </button>
                {openSection === 'chain' && (
                  <div className="pl-5 mt-1">
                    <EvaluationChain steps={entry.evaluation_chain} />
                  </div>
                )}
              </div>
            )}

            {hasFieldChanges && (
              <div className="mb-2">
                <button
                  className="flex items-center gap-1.5 text-[11px] font-medium w-full text-left py-1"
                  style={{ color: QB.textPrimary }}
                  onClick={() => toggleSection('diff')}
                >
                  {openSection === 'diff' ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
                  FIELD CHANGES
                </button>
                {openSection === 'diff' && (
                  <div className="pl-5 mt-1">
                    <FieldDiff before={entry.golden_record_before} after={entry.golden_record_after} />
                  </div>
                )}
              </div>
            )}

            {/* Metadata footer + restore */}
            <div className="flex items-center gap-3 mt-2 pt-2 border-t text-[10px]" style={{ borderColor: QB.cardBorder, color: QB.textMuted }}>
              <span>Candidates: {entry.candidates_evaluated}</span>
              <span>LLM: {entry.llm_calls}</span>
              <span>Embed: {entry.embedding_calls}</span>
              <span>{entry.total_duration_ms}ms</span>
              {entry.absorbed_golden_id && (
                <span className="px-1.5 py-0.5 rounded" style={{ backgroundColor: QB.purpleLight, color: QB.purpleDark }}>
                  Absorbed {entry.absorbed_golden_id}
                </span>
              )}
              <div className="flex-1" />
              {entry.golden_record_after && (
                <button
                  onClick={() => onRestore?.(entry)}
                  className="flex items-center gap-1 px-2 py-1 rounded text-[10px] font-medium transition-colors hover:opacity-80"
                  style={{ backgroundColor: QB.purpleLight, color: QB.purpleDark }}
                >
                  <RotateCcw size={9} /> Restore to this state
                </button>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
