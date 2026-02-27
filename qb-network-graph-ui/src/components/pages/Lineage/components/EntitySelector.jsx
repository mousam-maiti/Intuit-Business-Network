import { useState, useRef, useEffect } from 'react';
import { Building2, ChevronDown, Search } from 'lucide-react';
import { QB } from '@/constants/colors';
import { getIndustry } from '@/constants/industries';

/**
 * Typeahead dropdown to select an entity for lineage viewing.
 */
export function EntitySelector({ entities, selectedId, onSelect }) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const ref = useRef(null);

  useEffect(() => {
    const handleClick = (e) => {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false);
    };
    document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, []);

  const selected = entities.find((e) => e.id === selectedId);
  const filtered = query
    ? entities.filter((e) => e.name.toLowerCase().includes(query.toLowerCase()))
    : entities;

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-2 px-3 py-2 rounded-lg text-xs border transition-colors"
        style={{
          backgroundColor: QB.cardBg,
          borderColor: open ? QB.green : QB.cardBorder,
          color: QB.textPrimary,
          minWidth: 240,
        }}
      >
        <Building2 size={13} style={{ color: QB.textMuted }} />
        <span className="flex-1 text-left truncate">
          {selected ? selected.name : 'Select entity...'}
        </span>
        <ChevronDown size={13} style={{ color: QB.textMuted }} />
      </button>

      {open && (
        <div
          className="absolute top-full left-0 mt-1 w-72 rounded-lg shadow-lg overflow-hidden z-30"
          style={{ backgroundColor: QB.cardBg, border: '1px solid ' + QB.cardBorder }}
        >
          {/* Search input */}
          <div className="flex items-center gap-2 px-3 py-2 border-b" style={{ borderColor: QB.cardBorder }}>
            <Search size={12} style={{ color: QB.textMuted }} />
            <input
              autoFocus
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search entities..."
              className="flex-1 text-xs bg-transparent focus:outline-none"
              style={{ color: QB.textPrimary }}
            />
          </div>

          {/* Options */}
          <div className="max-h-48 overflow-y-auto">
            {filtered.length === 0 ? (
              <div className="px-3 py-4 text-xs text-center" style={{ color: QB.textMuted }}>
                No entities found
              </div>
            ) : (
              filtered.map((e) => {
                const ind = getIndustry(e.industry);
                const isActive = e.id === selectedId;
                return (
                  <button
                    key={e.id}
                    onClick={() => { onSelect(e.id); setOpen(false); setQuery(''); }}
                    className="w-full flex items-center gap-2.5 px-3 py-2 text-xs text-left transition-colors hover:bg-gray-50"
                    style={{
                      backgroundColor: isActive ? QB.greenLight : 'transparent',
                      color: QB.textPrimary,
                    }}
                  >
                    <div
                      className="w-6 h-6 rounded flex items-center justify-center shrink-0"
                      style={{ backgroundColor: ind.color + '15' }}
                    >
                      <Building2 size={11} style={{ color: ind.color }} />
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="font-medium truncate">{e.name}</div>
                      <div className="text-[10px]" style={{ color: QB.textMuted }}>{ind.label}</div>
                    </div>
                  </button>
                );
              })
            )}
          </div>
        </div>
      )}
    </div>
  );
}
