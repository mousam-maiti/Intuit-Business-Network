import { useState, useEffect, useMemo } from 'react';
import { Building2, GitBranch, Activity, Unlink, DollarSign, AlertTriangle, Info } from 'lucide-react';
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer, PieChart, Pie, Cell } from 'recharts';
import { QB } from '@/constants/colors';
import { getIndustry } from '@/constants/industries';
import { fmt } from '@/utils/format';
import { getEntities } from '@/api/entities';
import { getAllRelationships, getMonthlyVolume } from '@/api/relationships';
import { getPendingMatches } from '@/api/matching';
import { Widget } from '@/components/shared';

export default function DashboardPage({ onNavigate, selectedEntity }) {
  const [entities, setEntities] = useState([]);
  const [relationships, setRelationships] = useState([]);
  const [volume, setVolume] = useState([]);
  const [pendingCount, setPendingCount] = useState(0);

  useEffect(() => {
    getEntities().then(r => setEntities(r.data));
    getAllRelationships().then(r => setRelationships(r.data));
    getPendingMatches().then(r => setPendingCount(r.data.length));
  }, []);

  useEffect(() => {
    if (selectedEntity?.id) {
      getMonthlyVolume(selectedEntity.id).then(r => setVolume(r.data));
    }
  }, [selectedEntity?.id]);

  const totalEntities = entities.length;
  const totalRels = relationships.length;
  const activeRels = relationships.filter((r) => r.status === 'active').length;
  const dormantRels = relationships.filter((r) => r.status === 'dormant').length;
  const totalVol = relationships.reduce((s, r) => s + r.volume, 0);

  const sectorData = useMemo(() => {
    const m = {};
    entities.forEach((e) => { const sec = getIndustry(e.industry).sector; m[sec] = (m[sec] || 0) + 1; });
    return Object.entries(m).map(([name, value]) => ({ name, value }));
  }, [entities]);
  const sectorColors = ['#2CA01C', '#7C3AED', '#7c3aed', '#0077C5', '#E8710A', '#dc2626'];

  const typeData = [
    { name: 'Vendors', value: relationships.filter((r) => r.source === selectedEntity?.id).length },
    { name: 'Clients', value: relationships.filter((r) => r.target === selectedEntity?.id).length },
  ];

  const topHubs = useMemo(() =>
    [...entities].sort((a, b) => (b.vendors + b.clients) - (a.vendors + a.clients)).slice(0, 3),
  [entities]);

  return (
    <div className="flex flex-col h-full overflow-y-auto">
      <div className="px-6 py-4">
        <h1 className="text-xl font-normal" style={{ color: QB.textPrimary }}>Network dashboard</h1>
        <p className="text-xs mt-1" style={{ color: QB.textMuted }}>Overview of your business network health and activity</p>
      </div>
      <div className="px-6 pb-6 space-y-4">
        {/* KPI row */}
        <div className="grid grid-cols-5 gap-3">
          {[
            { label: 'Businesses', value: totalEntities, icon: <Building2 size={16} />, color: QB.green },
            { label: 'Relationships', value: totalRels, icon: <GitBranch size={16} />, color: QB.purple },
            { label: 'Active', value: activeRels, icon: <Activity size={16} />, color: QB.green },
            { label: 'Dormant', value: dormantRels, icon: <Unlink size={16} />, color: QB.dormant },
            { label: 'Total volume', value: fmt(totalVol), icon: <DollarSign size={16} />, color: QB.link },
          ].map((kpi, i) => (
            <Widget key={i}>
              <div className="flex items-center gap-3">
                <div className="w-9 h-9 rounded flex items-center justify-center" style={{ backgroundColor: kpi.color + '12' }}>
                  <span style={{ color: kpi.color }}>{kpi.icon}</span>
                </div>
                <div className="space-y-1">
                  <div className="text-[10px]" style={{ color: QB.textMuted }}>{kpi.label}</div>
                  <div className="text-lg font-semibold leading-none" style={{ color: QB.textPrimary }}>{kpi.value}</div>
                </div>
              </div>
            </Widget>
          ))}
        </div>

        <div className="grid grid-cols-3 gap-4">
          <Widget title="INDUSTRY DISTRIBUTION">
            <div className="h-40 flex items-center justify-center">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart><Pie data={sectorData} dataKey="value" cx="50%" cy="50%" innerRadius={35} outerRadius={60} paddingAngle={2}>
                  {sectorData.map((_, i) => <Cell key={i} fill={sectorColors[i % sectorColors.length]} />)}
                </Pie><Tooltip contentStyle={{ fontSize: 11 }} /></PieChart>
              </ResponsiveContainer>
            </div>
            <div className="flex flex-wrap gap-x-3 gap-y-1 mt-1">
              {sectorData.map((s, i) => (
                <span key={i} className="text-[10px] flex items-center gap-1" style={{ color: QB.textSecondary }}>
                  <span className="w-2 h-2 rounded-full" style={{ backgroundColor: sectorColors[i % sectorColors.length] }} /> {s.name} ({s.value})
                </span>
              ))}
            </div>
          </Widget>

          <Widget title="RELATIONSHIP TYPES">
            <div className="h-40 flex items-center justify-center">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart><Pie data={typeData} dataKey="value" cx="50%" cy="50%" innerRadius={35} outerRadius={60} paddingAngle={3}>
                  <Cell fill={QB.purple} /><Cell fill={QB.green} />
                </Pie><Tooltip contentStyle={{ fontSize: 11 }} /></PieChart>
              </ResponsiveContainer>
            </div>
            <div className="flex gap-4 justify-center mt-1">
              <span className="text-[10px] flex items-center gap-1" style={{ color: QB.purpleDark }}><span className="w-2 h-2 rounded-full" style={{ backgroundColor: QB.purple }} /> Vendors ({typeData[0].value})</span>
              <span className="text-[10px] flex items-center gap-1" style={{ color: QB.greenDark }}><span className="w-2 h-2 rounded-full" style={{ backgroundColor: QB.green }} /> Clients ({typeData[1].value})</span>
            </div>
          </Widget>

          <Widget title="TRANSACTION VOLUME TREND">
            <div className="h-44">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={volume}>
                  <XAxis dataKey="month" tick={{ fontSize: 10, fill: QB.textMuted }} axisLine={false} tickLine={false} />
                  <YAxis tick={{ fontSize: 10, fill: QB.textMuted }} axisLine={false} tickLine={false} width={30} />
                  <Tooltip contentStyle={{ fontSize: 11 }} />
                  <Area type="monotone" dataKey="vol" stroke={QB.green} fill={QB.greenLight} strokeWidth={2} />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </Widget>
        </div>

        <Widget title="TOP HUB ENTITIES" action={<button onClick={() => onNavigate('network')} className="text-[10px]" style={{ color: QB.link }}>View network &rarr;</button>}>
          <div className="space-y-2">
            {topHubs.map((e, i) => {
              const ind = getIndustry(e.industry);
              return (
                <div key={e.id} className="flex items-center gap-3 py-1.5">
                  <span className="text-xs font-semibold w-5 text-center" style={{ color: QB.textMuted }}>#{i + 1}</span>
                  <div className="w-7 h-7 rounded flex items-center justify-center" style={{ backgroundColor: ind.color + '12' }}><Building2 size={12} style={{ color: ind.color }} /></div>
                  <div className="flex-1 min-w-0">
                    <div className="text-sm font-medium truncate" style={{ color: QB.textPrimary }}>{e.name}</div>
                    <div className="text-[10px]" style={{ color: QB.textMuted }}>{ind.label} &middot; {e.city}, {e.state}</div>
                  </div>
                  <div className="text-right"><div className="text-xs font-semibold" style={{ color: QB.textPrimary }}>{e.vendors + e.clients}</div><div className="text-[10px]" style={{ color: QB.textMuted }}>connections</div></div>
                  <div className="text-right"><div className="text-xs font-semibold" style={{ color: QB.textPrimary }}>{fmt(e.volume)}</div><div className="text-[10px]" style={{ color: QB.textMuted }}>volume/yr</div></div>
                </div>
              );
            })}
          </div>
        </Widget>

        <div className="grid grid-cols-2 gap-4">
          <Widget title="PENDING ACTIONS">
            <div className="space-y-2">
              <div className="flex items-center gap-3 text-xs py-2 border-b" style={{ borderColor: '#F0F0F0' }}>
                <div className="w-6 h-6 rounded-full flex items-center justify-center" style={{ backgroundColor: QB.orangeLight }}><AlertTriangle size={11} style={{ color: QB.orange }} /></div>
                <span className="flex-1" style={{ color: QB.textPrimary }}>{pendingCount} matches awaiting review</span>
                <button onClick={() => onNavigate('review')} className="text-[10px] font-medium" style={{ color: QB.link }}>Review</button>
              </div>
              <div className="flex items-center gap-3 text-xs py-2">
                <div className="w-6 h-6 rounded-full flex items-center justify-center" style={{ backgroundColor: QB.purpleLight }}><Info size={11} style={{ color: QB.purple }} /></div>
                <span className="flex-1" style={{ color: QB.textPrimary }}>{dormantRels} dormant relationships</span>
                <button onClick={() => onNavigate('network')} className="text-[10px] font-medium" style={{ color: QB.link }}>View</button>
              </div>
            </div>
          </Widget>
          <Widget title="ENTITY RESOLUTION STATS">
            <div className="grid grid-cols-3 gap-3 py-2">
              {[
                { label: 'Tier 1 auto', value: '82%', sub: 'Deterministic', color: QB.green },
                { label: 'Tier 2 AI', value: '15%', sub: 'Persona match', color: QB.orange },
                { label: 'Manual', value: '3%', sub: 'Human review', color: QB.red },
              ].map((s, i) => (
                <div key={i} className="text-center py-2 rounded" style={{ backgroundColor: '#F4F5F7' }}>
                  <div className="text-base font-semibold" style={{ color: s.color }}>{s.value}</div>
                  <div className="text-[10px] font-medium" style={{ color: QB.textPrimary }}>{s.label}</div>
                  <div className="text-[9px]" style={{ color: QB.textMuted }}>{s.sub}</div>
                </div>
              ))}
            </div>
          </Widget>
        </div>
      </div>
    </div>
  );
}
