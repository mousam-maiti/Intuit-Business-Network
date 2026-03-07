import { useState, useEffect, useCallback } from 'react';
import {
  Server, Database, HardDrive, RefreshCw,
  CheckCircle, XCircle, AlertCircle, Zap, BrainCircuit,
} from 'lucide-react';
import { Widget } from '@/components/shared';
import { getInfraMetrics, getConvAgentHealth, getEntityAgentHealth } from '@/api/infra';

// Grafana-inspired dark palette
const G = {
  bg: '#111217',
  surface: '#181B1F',
  card: '#1E2028',
  border: '#2C2F36',
  borderLight: '#363940',
  text: '#D8DEE9',
  textMuted: '#6E7681',
  textDim: '#484D56',
  green: '#73BF69',
  greenDark: '#1A3A20',
  yellow: '#FADE2A',
  yellowDark: '#3D3A1A',
  orange: '#FF9830',
  orangeDark: '#3D2A1A',
  red: '#F2495C',
  redDark: '#3D1A22',
  blue: '#5794F2',
  blueDark: '#1A2A3D',
  purple: '#B877D9',
  purpleDark: '#2A1A3D',
  cyan: '#8AB8FF',
};

function StatusBadge({ status }) {
  const ok = status === 'connected' || status === 'healthy' || status === 'ok';
  const warn = status === 'in-memory' || status === 'unavailable' || status === 'yellow';
  const color = ok ? G.green : warn ? G.orange : G.red;
  const bg = ok ? G.greenDark : warn ? G.orangeDark : G.redDark;
  return (
    <span
      className="inline-flex items-center gap-1.5 text-[10px] px-2 py-0.5 rounded font-medium"
      style={{ backgroundColor: bg, color }}
    >
      <span className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: color }} />
      {status}
    </span>
  );
}

function ElasticBadge({ status }) {
  const colorMap = { green: G.green, yellow: G.yellow, red: G.red };
  const bgMap = { green: G.greenDark, yellow: G.yellowDark, red: G.redDark };
  return (
    <span
      className="inline-flex items-center gap-1.5 text-[10px] px-2 py-0.5 rounded font-medium"
      style={{ backgroundColor: bgMap[status] || G.card, color: colorMap[status] || G.textMuted }}
    >
      <span className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: colorMap[status] || G.textMuted }} />
      {status || 'unknown'}
    </span>
  );
}

function MetricCard({ icon: Icon, label, value, sub, color = G.green }) {
  return (
    <div className="rounded-lg px-4 py-3" style={{ backgroundColor: G.card, border: `1px solid ${G.border}` }}>
      <div className="flex items-center gap-2 mb-1.5">
        <div className="w-7 h-7 rounded flex items-center justify-center" style={{ backgroundColor: color + '20' }}>
          <Icon size={14} style={{ color }} />
        </div>
        <span className="text-[10px] font-medium uppercase tracking-wider" style={{ color: G.textMuted }}>{label}</span>
      </div>
      <div className="text-2xl font-bold font-mono" style={{ color: G.text }}>
        {value ?? '--'}
      </div>
      {sub && <div className="text-[10px] mt-1 font-mono" style={{ color: G.textMuted }}>{sub}</div>}
    </div>
  );
}

function TableRows({ data }) {
  if (!data || typeof data !== 'object') return null;
  return (
    <div className="space-y-0.5">
      {Object.entries(data).map(([key, val]) => (
        <div key={key} className="flex items-center justify-between text-xs py-1.5 px-2 rounded" style={{ ':hover': { backgroundColor: G.surface } }}>
          <span style={{ color: G.textMuted }}>{key.replace(/_/g, ' ')}</span>
          <span className="font-mono font-medium" style={{ color: G.text }}>
            {val === -1 ? <span style={{ color: G.textDim }}>n/a</span> : typeof val === 'number' ? val.toLocaleString() : val}
          </span>
        </div>
      ))}
    </div>
  );
}

function DarkPanel({ title, children }) {
  return (
    <div className="rounded-lg overflow-hidden" style={{ backgroundColor: G.card, border: `1px solid ${G.border}` }}>
      <div className="px-4 py-2.5" style={{ borderBottom: `1px solid ${G.border}` }}>
        <span className="text-[10px] font-semibold uppercase tracking-wider" style={{ color: G.textMuted }}>{title}</span>
      </div>
      <div className="px-4 py-3">
        {children}
      </div>
    </div>
  );
}

function ServiceCard({ name, port, status, detail }) {
  const ok = status === 'connected' || status === 'healthy' || status === 'ok';
  const Icon = ok ? CheckCircle : status === 'unknown' ? AlertCircle : XCircle;
  const color = ok ? G.green : status === 'unknown' ? G.orange : G.red;
  return (
    <div className="rounded-lg px-3 py-3" style={{ backgroundColor: G.surface, border: `1px solid ${G.border}` }}>
      <div className="flex items-center gap-2">
        <Icon size={14} style={{ color }} />
        <span className="text-xs font-medium" style={{ color: G.text }}>{name}</span>
      </div>
      <div className="flex items-center justify-between mt-1.5">
        <span className="text-[10px] font-mono" style={{ color: G.textDim }}>:{port}</span>
        <StatusBadge status={status} />
      </div>
      {detail && <div className="text-[10px] mt-1 font-mono" style={{ color: G.textMuted }}>{detail}</div>}
    </div>
  );
}

function MiniStat({ label, value, color = G.text }) {
  return (
    <div className="text-center px-2 py-2.5 rounded" style={{ backgroundColor: G.surface }}>
      <div className="text-sm font-bold font-mono" style={{ color }}>{value}</div>
      <div className="text-[10px]" style={{ color: G.textMuted }}>{label}</div>
    </div>
  );
}

function fmtNum(n) {
  if (n == null) return '--';
  if (n >= 1000000) return `${(n / 1000000).toFixed(1)}M`;
  if (n >= 1000) return `${(n / 1000).toFixed(1)}K`;
  return n.toLocaleString();
}

export default function InfraMonitorPage() {
  const [metrics, setMetrics] = useState(null);
  const [services, setServices] = useState(null);
  const [loading, setLoading] = useState(true);
  const [lastRefresh, setLastRefresh] = useState(null);

  const fetchAll = useCallback(async () => {
    setLoading(true);
    const results = { be: 'ok', convAgent: null, entityAgent: null };

    try {
      const [infraRes, convRes, entityRes] = await Promise.allSettled([
        getInfraMetrics(),
        getConvAgentHealth(),
        getEntityAgentHealth(),
      ]);

      if (infraRes.status === 'fulfilled') {
        setMetrics(infraRes.value);
      } else {
        results.be = 'error';
      }

      if (convRes.status === 'fulfilled') {
        results.convAgent = convRes.value;
      }

      if (entityRes.status === 'fulfilled') {
        results.entityAgent = entityRes.value;
      }
    } catch {
      // handled per-service
    }

    setServices(results);
    setLoading(false);
    setLastRefresh(new Date());
  }, []);

  useEffect(() => {
    fetchAll();
    const interval = setInterval(fetchAll, 30000);
    return () => clearInterval(interval);
  }, [fetchAll]);

  const redis = metrics?.redis;
  const neo4j = metrics?.neo4j;
  const paimon = metrics?.paimon;
  const elastic = metrics?.elasticsearch;
  const kibana = metrics?.kibana;
  const otel = metrics?.otel_collector;
  const conv = services?.convAgent;
  const entity = services?.entityAgent;

  return (
    <div className="flex flex-col h-full overflow-y-auto" style={{ backgroundColor: G.bg }}>
      {/* Header */}
      <div className="px-6 py-4" style={{ borderBottom: `1px solid ${G.border}` }}>
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-lg font-semibold" style={{ color: G.text }}>Infrastructure Monitor</h1>
            <p className="text-[11px] mt-0.5 font-mono" style={{ color: G.textMuted }}>
              Real-time health and metrics
              {lastRefresh && <> &middot; {lastRefresh.toLocaleTimeString()}</>}
              {metrics?.duration_ms != null && <> &middot; {metrics.duration_ms}ms</>}
            </p>
          </div>
          <button
            onClick={fetchAll}
            disabled={loading}
            className="flex items-center gap-1.5 text-[11px] px-3 py-1.5 rounded font-medium transition-colors"
            style={{ backgroundColor: G.greenDark, color: G.green, border: `1px solid ${G.green}40` }}
          >
            <RefreshCw size={11} className={loading ? 'animate-spin' : ''} />
            {loading ? 'Refreshing...' : 'Refresh'}
          </button>
        </div>
      </div>

      <div className="px-6 py-5 space-y-5">
        {/* Service Health */}
        <DarkPanel title="Service Health">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <ServiceCard name="Backend API" port={8087} status={services?.be === 'ok' ? 'connected' : 'error'} detail="REST API + Graph queries" />
            <ServiceCard name="Conv Agent" port={8082} status={conv?.status || 'unknown'} detail={conv?.components?.llm || ''} />
            <ServiceCard name="Entity Agent" port={8085} status={entity?.status || 'unknown'} detail={entity?.components?.llm_model || ''} />
            <ServiceCard name="MCP Server" port={8083} status={conv?.components?.mcp_server || 'unknown'} detail={conv?.components?.mcp_tools ? `${conv.components.mcp_tools} tools` : ''} />
            <ServiceCard name="Elasticsearch" port={9200} status={elastic?.status === 'green' || elastic?.status === 'yellow' ? 'connected' : elastic?.status || 'unknown'} detail={elastic?.cluster_name || ''} />
            <ServiceCard name="Kibana" port={5601} status={kibana?.status === 'available' ? 'connected' : kibana?.status || 'unknown'} detail={kibana?.version ? `v${kibana.version}` : ''} />
            <ServiceCard name="OTEL Collector" port={4317} status={otel?.status || 'unknown'} detail="Traces + Metrics + Logs" />
          </div>
        </DarkPanel>

        {/* Key Metrics */}
        <DarkPanel title="Key Metrics">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <MetricCard icon={Database} label="Entities" value={neo4j?.entities?.active} sub={neo4j?.entities ? `${neo4j.entities.total} total, ${neo4j.entities.merged} merged` : null} color={G.green} />
            <MetricCard icon={Zap} label="Relationships" value={neo4j?.relationships?.total} sub={neo4j?.relationships ? `${neo4j.relationships.buys_from} buys, ${neo4j.relationships.sells_to} sells` : null} color={G.purple} />
            <MetricCard icon={HardDrive} label="Golden Records" value={paimon?.tables?.golden_records} sub={paimon?.tables ? `${paimon.tables.golden_records_active} active` : null} color={G.orange} />
            <MetricCard icon={Server} label="Audit Trail" value={paimon?.tables?.resolution_audit} sub={paimon?.tables ? `${paimon.tables.pending_review} pending review` : null} color={G.blue} />
          </div>
        </DarkPanel>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
          {/* Redis */}
          <DarkPanel title="Redis Cache">
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <StatusBadge status={redis?.status || 'unknown'} />
                {redis?.memory_used_mb != null && (
                  <span className="text-[10px] font-mono" style={{ color: G.textMuted }}>
                    {redis.memory_used_mb} MB / {redis.memory_peak_mb} MB peak
                  </span>
                )}
              </div>
              {redis?.status === 'connected' && (
                <>
                  <div className="grid grid-cols-3 gap-2">
                    <MiniStat label="Total Keys" value={redis.total_keys} color={G.cyan} />
                    <MiniStat label="Hit Rate" value={`${redis.hit_rate}%`} color={redis.hit_rate > 50 ? G.green : G.orange} />
                    <MiniStat label="Hits / Misses" value={`${fmtNum(redis.hits)} / ${fmtNum(redis.misses)}`} />
                  </div>
                  <div className="pt-2" style={{ borderTop: `1px solid ${G.border}` }}>
                    <div className="text-[10px] font-semibold uppercase tracking-wider mb-2" style={{ color: G.textMuted }}>
                      Cached keys by type
                    </div>
                    <div className="grid grid-cols-3 gap-2">
                      {redis.keys_by_type && Object.entries(redis.keys_by_type).map(([k, v]) => (
                        <div key={k} className="flex items-center justify-between text-xs px-2 py-1.5 rounded" style={{ backgroundColor: G.surface }}>
                          <span style={{ color: G.textMuted }}>{k}</span>
                          <span className="font-mono font-medium" style={{ color: v > 0 ? G.green : G.textDim }}>{v}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                </>
              )}
            </div>
          </DarkPanel>

          {/* Neo4j */}
          <DarkPanel title="Neo4j Graph">
            <div className="space-y-3">
              <StatusBadge status={neo4j?.status || 'unknown'} />
              {neo4j?.status === 'connected' && (
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <div className="text-[10px] font-semibold uppercase tracking-wider mb-2" style={{ color: G.textMuted }}>Entities</div>
                    <TableRows data={neo4j.entities} />
                  </div>
                  <div>
                    <div className="text-[10px] font-semibold uppercase tracking-wider mb-2" style={{ color: G.textMuted }}>Relationships</div>
                    <TableRows data={neo4j.relationships} />
                  </div>
                </div>
              )}
            </div>
          </DarkPanel>

          {/* Paimon */}
          <DarkPanel title="Paimon Warehouse">
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <StatusBadge status={paimon?.status || 'unknown'} />
                {paimon?.warehouse && (
                  <span className="text-[10px] font-mono truncate max-w-[200px]" style={{ color: G.textDim }} title={paimon.warehouse}>
                    {paimon.warehouse.split('/').slice(-1)[0]}
                  </span>
                )}
              </div>
              {paimon?.status === 'connected' && <TableRows data={paimon.tables} />}
            </div>
          </DarkPanel>

          {/* Elasticsearch */}
          <DarkPanel title="Elasticsearch">
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <ElasticBadge status={elastic?.status} />
                {elastic?.node_count != null && (
                  <span className="text-[10px] font-mono" style={{ color: G.textMuted }}>
                    {elastic.node_count} node{elastic.node_count !== 1 ? 's' : ''} &middot; {elastic.active_shards} shards
                  </span>
                )}
              </div>
              {elastic?.indices && Object.keys(elastic.indices).length > 0 && (
                <div className="space-y-1">
                  <div className="text-[10px] font-semibold uppercase tracking-wider mb-1" style={{ color: G.textMuted }}>Indices</div>
                  {Object.entries(elastic.indices).map(([name, info]) => (
                    <div key={name} className="flex items-center justify-between text-xs py-1.5 px-2 rounded" style={{ backgroundColor: G.surface }}>
                      <span className="font-mono" style={{ color: G.cyan }}>{name}</span>
                      <div className="flex items-center gap-3">
                        <span className="font-mono font-medium" style={{ color: G.text }}>{fmtNum(info.docs)} docs</span>
                        <span className="font-mono text-[10px]" style={{ color: G.textMuted }}>{info.size}</span>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </DarkPanel>

          {/* OTEL Collector */}
          <DarkPanel title="OTEL Collector">
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <StatusBadge status={otel?.status || 'unknown'} />
                {otel?.status === 'connected' && (
                  <span className="text-[10px] font-mono" style={{ color: G.textMuted }}>
                    gRPC :{otel.grpc_port} &middot; HTTP :{otel.http_port} &middot; Prom :{otel.prometheus_port}
                  </span>
                )}
              </div>
              {otel?.pipeline && Object.keys(otel.pipeline).length > 0 && (
                <>
                  <div className="text-[10px] font-semibold uppercase tracking-wider" style={{ color: G.textMuted }}>Pipeline throughput</div>
                  <div className="grid grid-cols-2 gap-2">
                    {Object.entries(otel.pipeline).map(([k, v]) => (
                      <div key={k} className="flex items-center justify-between text-xs px-2 py-1.5 rounded" style={{ backgroundColor: G.surface }}>
                        <span style={{ color: G.textMuted }}>{k.replace(/_/g, ' ')}</span>
                        <span className="font-mono font-medium" style={{ color: G.green }}>{fmtNum(v)}</span>
                      </div>
                    ))}
                  </div>
                </>
              )}
            </div>
          </DarkPanel>

          {/* LLM Providers */}
          <DarkPanel title="LLM Providers">
            <div className="space-y-3">
              {/* Conv Agent LLM */}
              <div className="rounded px-3 py-2.5" style={{ backgroundColor: G.surface, border: `1px solid ${G.border}` }}>
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-2">
                    <div className="w-6 h-6 rounded flex items-center justify-center" style={{ backgroundColor: G.purple + '20' }}>
                      <BrainCircuit size={12} style={{ color: G.purple }} />
                    </div>
                    <span className="text-xs font-medium" style={{ color: G.text }}>Conversational Agent</span>
                  </div>
                  <StatusBadge status={conv?.components?.llm || 'unknown'} />
                </div>
                <div className="grid grid-cols-2 gap-2">
                  <div className="flex items-center justify-between text-[11px] px-2 py-1 rounded" style={{ backgroundColor: G.card }}>
                    <span style={{ color: G.textMuted }}>provider</span>
                    <span className="font-mono font-medium" style={{ color: G.cyan }}>{conv?.components?.llm_provider || '--'}</span>
                  </div>
                  <div className="flex items-center justify-between text-[11px] px-2 py-1 rounded" style={{ backgroundColor: G.card }}>
                    <span style={{ color: G.textMuted }}>model</span>
                    <span className="font-mono font-medium" style={{ color: G.text }}>{conv?.components?.llm_model || '--'}</span>
                  </div>
                </div>
              </div>

              {/* Entity Agent LLM + Embedding */}
              <div className="rounded px-3 py-2.5" style={{ backgroundColor: G.surface, border: `1px solid ${G.border}` }}>
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-2">
                    <div className="w-6 h-6 rounded flex items-center justify-center" style={{ backgroundColor: G.blue + '20' }}>
                      <BrainCircuit size={12} style={{ color: G.blue }} />
                    </div>
                    <span className="text-xs font-medium" style={{ color: G.text }}>Entity Resolution Agent</span>
                  </div>
                  <StatusBadge status={entity?.components?.llm || 'unknown'} />
                </div>
                <div className="grid grid-cols-2 gap-2">
                  <div className="flex items-center justify-between text-[11px] px-2 py-1 rounded" style={{ backgroundColor: G.card }}>
                    <span style={{ color: G.textMuted }}>provider</span>
                    <span className="font-mono font-medium" style={{ color: G.cyan }}>{entity?.components?.llm_provider || '--'}</span>
                  </div>
                  <div className="flex items-center justify-between text-[11px] px-2 py-1 rounded" style={{ backgroundColor: G.card }}>
                    <span style={{ color: G.textMuted }}>model</span>
                    <span className="font-mono font-medium" style={{ color: G.text }}>{entity?.components?.llm_model || '--'}</span>
                  </div>
                </div>
                <div className="mt-2 pt-2" style={{ borderTop: `1px solid ${G.border}` }}>
                  <div className="text-[10px] font-semibold uppercase tracking-wider mb-1.5" style={{ color: G.textMuted }}>Embedding</div>
                  <div className="grid grid-cols-2 gap-2">
                    <div className="flex items-center justify-between text-[11px] px-2 py-1 rounded" style={{ backgroundColor: G.card }}>
                      <span style={{ color: G.textMuted }}>provider</span>
                      <span className="font-mono font-medium" style={{ color: G.cyan }}>{entity?.components?.embedding_provider || '--'}</span>
                    </div>
                    <div className="flex items-center justify-between text-[11px] px-2 py-1 rounded" style={{ backgroundColor: G.card }}>
                      <span style={{ color: G.textMuted }}>model</span>
                      <span className="font-mono font-medium" style={{ color: G.text }}>{entity?.components?.embedding_model || '--'}</span>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </DarkPanel>
        </div>
      </div>
    </div>
  );
}
