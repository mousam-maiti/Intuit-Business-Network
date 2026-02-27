import { useState, useEffect } from 'react';
import {
  Plus, X, Check, XCircle, Zap, Building2, Tag, MapPin,
  UserPlus, Sparkles, Receipt, Activity, Layers, Target,
  FileText, ChevronDown, Loader2,
} from 'lucide-react';
import { QB } from '@/constants/colors';
import { getIndustry } from '@/constants/industries';
import { resolveEntity } from '@/api/matching';
import { addConnection } from '@/api/connections';
import { ScoreBar } from './ScoreBar';

export function AddConnectionModal({ open, onClose, onConnectionAdded }) {
  const [name, setName] = useState("");
  const [ein, setEin] = useState("");
  const [contactName, setContactName] = useState("");
  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("");
  const [website, setWebsite] = useState("");
  const [category, setCategory] = useState("");
  const [address, setAddress] = useState("");
  const [city, setCity] = useState("");
  const [state, setState] = useState("");
  const [zip, setZip] = useState("");
  const [commodity, setCommodity] = useState("");
  const [expectedVolume, setExpectedVolume] = useState("");
  const [paymentTerms, setPaymentTerms] = useState("");
  const [connType, setConnType] = useState("vendor");
  const [resolving, setResolving] = useState(false);
  const [tier, setTier] = useState(null);
  const [manualConfirmed, setManualConfirmed] = useState(false);
  const [selectedCandidate, setSelectedCandidate] = useState(null);
  const [showMoreFields, setShowMoreFields] = useState(false);
  const [resolveResult, setResolveResult] = useState(null);

  const resetManual = () => {
    setName(""); setEin(""); setContactName(""); setEmail(""); setPhone(""); setWebsite("");
    setCategory(""); setAddress(""); setCity(""); setState(""); setZip(""); setCommodity("");
    setExpectedVolume(""); setPaymentTerms(""); setManualConfirmed(false); setTier(null);
    setSelectedCandidate(null); setShowMoreFields(false); setResolveResult(null);
    onClose();
  };

  const handleConfirm = async (candidate) => {
    setSelectedCandidate(candidate);
    try {
      const payload = {
        connType,
        entity: candidate || undefined,
        name, ein, contactName, email, phone, website, category,
        address, city, state, zip, commodity, expectedVolume, paymentTerms,
      };
      const result = await addConnection(payload);
      setManualConfirmed(true);
      if (onConnectionAdded) onConnectionAdded(result.data);
    } catch {
      setManualConfirmed(true);
    }
  };

  const filledFields = [name, ein, contactName, email, category, address, city, state, commodity, expectedVolume].filter(Boolean).length;
  const resolutionQuality = filledFields <= 1 ? "low" : filledFields <= 4 ? "medium" : "high";

  useEffect(() => {
    if (!open) return;
    if (ein.length >= 9 || name.length > 3) {
      setResolving(true); setTier(null); setManualConfirmed(false); setSelectedCandidate(null);
      resolveEntity({ name, ein, city, state, industry: category }).then(r => {
        setResolving(false);
        const data = r.data;
        setTier(data.tier);
        if (data.tier === 1) {
          setResolveResult({ match: data.match, confidence: data.confidence, scores: data.scores, latency: data.latency });
        } else if (data.tier === 2) {
          setResolveResult({ candidates: data.candidates, latency: data.latency });
        }
      }).catch(() => { setResolving(false); setTier(null); });
    } else { setResolving(false); setTier(null); }
  }, [open, name, ein, city, state, category]);

  const tier1Match = resolveResult?.match;
  const tier1Scores = resolveResult?.scores || {};
  const tier2Candidates = resolveResult?.candidates || [];

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center pt-12" onClick={resetManual}>
      <div className="absolute inset-0 bg-black/30" />
      <div className="relative bg-white rounded-lg shadow-2xl w-full max-w-xl max-h-[85vh] flex flex-col" style={{ borderColor: QB.cardBorder }}
        onClick={e => e.stopPropagation()}>

        {/* Modal header */}
        <div className="flex items-center justify-between px-6 py-4 border-b shrink-0" style={{ borderColor: QB.cardBorder }}>
          <div>
            <h2 className="text-base font-medium" style={{ color: QB.textPrimary }}>Add connection</h2>
            <p className="text-[10px] mt-0.5" style={{ color: QB.textMuted }}>For prospective or off-platform relationships</p>
          </div>
          <button onClick={resetManual} className="p-1.5 rounded hover:bg-gray-100"><X size={16} style={{ color: QB.textMuted }} /></button>
        </div>

        {/* Modal body */}
        <div className="flex-1 overflow-y-auto px-6 py-4">
          {manualConfirmed ? (
            <div className="text-center py-8 space-y-3">
              <div className="w-14 h-14 mx-auto rounded-full flex items-center justify-center" style={{ backgroundColor: QB.greenLight }}><Check size={24} style={{ color: QB.green }} /></div>
              <div>
                <h2 className="text-base font-medium" style={{ color: QB.textPrimary }}>Connection added</h2>
                <p className="text-xs mt-1" style={{ color: QB.textMuted }}>
                  {selectedCandidate ? selectedCandidate.name : name} has been linked as your {connType}.
                </p>
                <p className="text-[10px] mt-1" style={{ color: QB.textMuted }}>
                  Entity resolution is running in the background. You will see an alert when it completes.
                </p>
              </div>
              <div className="flex gap-3 justify-center">
                <button onClick={resetManual}
                  className="text-xs px-4 py-2 rounded border" style={{ borderColor: QB.cardBorder, color: QB.textSecondary }}>Close</button>
              </div>
            </div>
          ) : (
            <div className="space-y-4">
              {/* Pipeline explainer */}
              <div className="flex items-center gap-4 py-2 px-3 rounded text-[10px]" style={{ backgroundColor: "#F9FAFB", color: QB.textMuted }}>
                <span className="flex items-center gap-1"><FileText size={10} /> You fill form</span>
                <span>{"\u2192"}</span>
                <span className="flex items-center gap-1"><Receipt size={10} /> Writes to QB MySQL</span>
                <span>{"\u2192"}</span>
                <span className="flex items-center gap-1"><Activity size={10} /> CDC picks up</span>
                <span>{"\u2192"}</span>
                <span className="flex items-center gap-1" style={{ color: QB.green }}><Check size={10} /> Same pipeline</span>
              </div>

              {/* Vendor / Client toggle */}
              <div className="flex gap-2">
                <button onClick={() => setConnType("vendor")} className="flex-1 py-2 rounded text-sm font-medium"
                  style={{ backgroundColor: connType === "vendor" ? QB.purple : "white", color: connType === "vendor" ? "white" : QB.textSecondary, border: connType === "vendor" ? "none" : "1px solid " + QB.cardBorder }}>
                  Vendor
                </button>
                <button onClick={() => setConnType("client")} className="flex-1 py-2 rounded text-sm font-medium"
                  style={{ backgroundColor: connType === "client" ? QB.green : "white", color: connType === "client" ? "white" : QB.textSecondary, border: connType === "client" ? "none" : "1px solid " + QB.cardBorder }}>
                  Client
                </button>
              </div>

              {/* Resolution quality indicator */}
              <div className="flex items-center gap-2 px-3 py-2 rounded text-[10px]" style={{
                backgroundColor: resolutionQuality === "high" ? QB.greenLight + "60" : resolutionQuality === "medium" ? QB.orangeLight : "#F4F5F7",
                color: resolutionQuality === "high" ? QB.greenDark : resolutionQuality === "medium" ? QB.orange : QB.textMuted
              }}>
                <div className="flex gap-0.5">
                  {[0, 1, 2].map(i => (
                    <div key={i} className="w-4 h-1.5 rounded-full" style={{
                      backgroundColor: i === 0 ? (filledFields >= 1 ? (resolutionQuality === "high" ? QB.green : resolutionQuality === "medium" ? QB.orange : QB.dormant) : "#DDD")
                        : i === 1 ? (filledFields >= 3 ? (resolutionQuality === "high" ? QB.green : QB.orange) : "#DDD")
                        : (filledFields >= 5 ? QB.green : "#DDD")
                    }} />
                  ))}
                </div>
                <span>
                  {filledFields === 0 ? "Fill in fields to improve entity resolution accuracy" :
                    resolutionQuality === "high" ? "Excellent \u2014 " + filledFields + " fields filled, high-confidence matching likely" :
                    resolutionQuality === "medium" ? "Good \u2014 " + filledFields + " fields filled, adding EIN or address improves matching" :
                    "Minimal \u2014 add more details for better matching"}
                </span>
              </div>

              {/* IDENTITY */}
              <div>
                <div className="text-[10px] font-semibold tracking-wider mb-2 flex items-center gap-1.5" style={{ color: QB.textMuted, letterSpacing: "0.08em" }}>
                  <Building2 size={10} /> IDENTITY
                </div>
                <div className="space-y-3">
                  <div>
                    <label className="text-xs mb-1 block" style={{ color: QB.textSecondary }}>Business name</label>
                    <input value={name} onChange={e => setName(e.target.value)} placeholder="e.g. Bob's Plumbing LLC" className="w-full px-3 py-2.5 rounded border text-sm focus:outline-none" style={{ borderColor: QB.cardBorder, color: QB.textPrimary }} />
                  </div>
                  <div className="flex gap-3">
                    <div className="flex-1">
                      <label className="text-xs mb-1 flex items-center gap-1" style={{ color: QB.textSecondary }}>
                        EIN / Tax ID
                        <span className="text-[9px] px-1 rounded" style={{ backgroundColor: QB.greenLight, color: QB.greenDark }}>instant match</span>
                      </label>
                      <input value={ein} onChange={e => setEin(e.target.value)} placeholder="XX-XXXXXXX" className="w-full px-3 py-2.5 rounded border text-sm focus:outline-none font-mono" style={{ borderColor: QB.cardBorder, color: QB.textPrimary }} />
                    </div>
                    <div className="flex-1">
                      <label className="text-xs mb-1 block" style={{ color: QB.textSecondary }}>Contact person</label>
                      <input value={contactName} onChange={e => setContactName(e.target.value)} placeholder="Bob Smith" className="w-full px-3 py-2.5 rounded border text-sm focus:outline-none" style={{ borderColor: QB.cardBorder, color: QB.textPrimary }} />
                    </div>
                  </div>
                  <div className="flex gap-3">
                    <div className="flex-1">
                      <label className="text-xs mb-1 block" style={{ color: QB.textSecondary }}>Email</label>
                      <input value={email} onChange={e => setEmail(e.target.value)} placeholder="bob@bobsplumbing.com" className="w-full px-3 py-2.5 rounded border text-sm focus:outline-none" style={{ borderColor: QB.cardBorder, color: QB.textPrimary }} />
                    </div>
                    <div className="flex-1">
                      <label className="text-xs mb-1 block" style={{ color: QB.textSecondary }}>Phone</label>
                      <input value={phone} onChange={e => setPhone(e.target.value)} placeholder="(512) 555-0100" className="w-full px-3 py-2.5 rounded border text-sm focus:outline-none" style={{ borderColor: QB.cardBorder, color: QB.textPrimary }} />
                    </div>
                  </div>
                </div>
              </div>

              {/* INDUSTRY & COMMODITIES */}
              <div>
                <div className="text-[10px] font-semibold tracking-wider mb-2 flex items-center gap-1.5" style={{ color: QB.textMuted, letterSpacing: "0.08em" }}>
                  <Tag size={10} /> INDUSTRY & COMMODITIES
                </div>
                <div className="space-y-3">
                  <div>
                    <label className="text-xs mb-1 block" style={{ color: QB.textSecondary }}>Category / Industry</label>
                    <input value={category} onChange={e => setCategory(e.target.value)} placeholder="Plumbing, Electrical, IT Services..." className="w-full px-3 py-2.5 rounded border text-sm focus:outline-none" style={{ borderColor: QB.cardBorder, color: QB.textPrimary }} />
                    <div className="text-[10px] mt-0.5" style={{ color: QB.textMuted }}>Free text {"\u2014"} mapped to NAICS code by classification pipeline</div>
                  </div>
                  <div>
                    <label className="text-xs mb-1 block" style={{ color: QB.textSecondary }}>
                      {connType === "vendor" ? "What are you buying from them?" : "What are you selling to them?"}
                    </label>
                    <input value={commodity} onChange={e => setCommodity(e.target.value)}
                      placeholder={connType === "vendor" ? "e.g. PVC pipes, water heaters, fixtures" : "e.g. Structural design, permits, civil plans"}
                      className="w-full px-3 py-2.5 rounded border text-sm focus:outline-none" style={{ borderColor: QB.cardBorder, color: QB.textPrimary }} />
                    <div className="text-[10px] mt-0.5" style={{ color: QB.textMuted }}>Feeds the persona commodity vector for matching</div>
                  </div>
                </div>
              </div>

              {/* LOCATION */}
              <div>
                <div className="text-[10px] font-semibold tracking-wider mb-2 flex items-center gap-1.5" style={{ color: QB.textMuted, letterSpacing: "0.08em" }}>
                  <MapPin size={10} /> LOCATION
                </div>
                <div className="space-y-3">
                  <div>
                    <label className="text-xs mb-1 block" style={{ color: QB.textSecondary }}>Street address</label>
                    <input value={address} onChange={e => setAddress(e.target.value)} placeholder="123 Main St" className="w-full px-3 py-2.5 rounded border text-sm focus:outline-none" style={{ borderColor: QB.cardBorder, color: QB.textPrimary }} />
                  </div>
                  <div className="flex gap-3">
                    <div className="flex-[2]">
                      <label className="text-xs mb-1 block" style={{ color: QB.textSecondary }}>City</label>
                      <input value={city} onChange={e => setCity(e.target.value)} placeholder="Austin" className="w-full px-3 py-2.5 rounded border text-sm focus:outline-none" style={{ borderColor: QB.cardBorder, color: QB.textPrimary }} />
                    </div>
                    <div className="flex-1">
                      <label className="text-xs mb-1 block" style={{ color: QB.textSecondary }}>State</label>
                      <input value={state} onChange={e => setState(e.target.value)} placeholder="TX" maxLength={2} className="w-full px-3 py-2.5 rounded border text-sm focus:outline-none" style={{ borderColor: QB.cardBorder, color: QB.textPrimary }} />
                    </div>
                    <div className="flex-1">
                      <label className="text-xs mb-1 block" style={{ color: QB.textSecondary }}>ZIP</label>
                      <input value={zip} onChange={e => setZip(e.target.value)} placeholder="78701" maxLength={5} className="w-full px-3 py-2.5 rounded border text-sm focus:outline-none" style={{ borderColor: QB.cardBorder, color: QB.textPrimary }} />
                    </div>
                  </div>
                </div>
              </div>

              {/* BEHAVIORAL (collapsed) */}
              <div>
                <button onClick={() => setShowMoreFields(!showMoreFields)} className="flex items-center gap-1.5 text-xs w-full" style={{ color: QB.link }}>
                  <ChevronDown size={12} style={{ transform: showMoreFields ? "rotate(180deg)" : "none", transition: "transform 0.2s" }} />
                  {showMoreFields ? "Hide" : "Show"} additional fields (website, volume, terms)
                </button>
                {showMoreFields && (
                  <div className="mt-3 space-y-3">
                    <div className="text-[10px] font-semibold tracking-wider mb-2 flex items-center gap-1.5" style={{ color: QB.textMuted, letterSpacing: "0.08em" }}>
                      <Activity size={10} /> BEHAVIORAL
                    </div>
                    <div>
                      <label className="text-xs mb-1 block" style={{ color: QB.textSecondary }}>Website</label>
                      <input value={website} onChange={e => setWebsite(e.target.value)} placeholder="https://bobsplumbing.com" className="w-full px-3 py-2.5 rounded border text-sm focus:outline-none" style={{ borderColor: QB.cardBorder, color: QB.textPrimary }} />
                    </div>
                    <div className="flex gap-3">
                      <div className="flex-1">
                        <label className="text-xs mb-1 block" style={{ color: QB.textSecondary }}>Expected volume</label>
                        <input value={expectedVolume} onChange={e => setExpectedVolume(e.target.value)} placeholder="e.g. $5,000/month" className="w-full px-3 py-2.5 rounded border text-sm focus:outline-none" style={{ borderColor: QB.cardBorder, color: QB.textPrimary }} />
                      </div>
                      <div className="flex-1">
                        <label className="text-xs mb-1 block" style={{ color: QB.textSecondary }}>Payment terms</label>
                        <select value={paymentTerms} onChange={e => setPaymentTerms(e.target.value)} className="w-full px-3 py-2.5 rounded border text-sm focus:outline-none" style={{ borderColor: QB.cardBorder, color: paymentTerms ? QB.textPrimary : QB.textMuted }}>
                          <option value="">Select...</option>
                          <option value="due_on_receipt">Due on receipt</option>
                          <option value="net_15">Net 15</option>
                          <option value="net_30">Net 30</option>
                          <option value="net_60">Net 60</option>
                        </select>
                      </div>
                    </div>
                  </div>
                )}
              </div>

              {/* Entity resolution results */}
              {resolving && (
                <div className="flex items-center gap-2 py-3 text-sm" style={{ color: QB.textMuted }}>
                  <Loader2 size={14} className="animate-spin" style={{ color: QB.green }} /> Running entity resolution...
                </div>
              )}

              {/* Tier 1 match */}
              {tier === 1 && !resolving && tier1Match && (
                <div className="space-y-3 pt-3 border-t" style={{ borderColor: QB.cardBorder }}>
                  <div className="flex items-center gap-2 text-xs">
                    <Zap size={12} style={{ color: QB.green }} />
                    <span className="font-medium" style={{ color: QB.green }}>
                      {ein.length >= 9 ? "EIN match \u2014 exact identity" : "Already in the network!"}
                    </span>
                    <span style={{ color: QB.textMuted }}>{"\u2014"} Tier 1 {ein.length >= 9 ? "EIN lookup" : "deterministic match"} in {resolveResult?.latency || "---"}</span>
                  </div>
                  <div className="p-4 rounded border-2 space-y-3" style={{ borderColor: QB.green + "40", backgroundColor: QB.greenLight + "30" }}>
                    <div className="flex items-start justify-between">
                      <div>
                        <div className="text-sm font-medium" style={{ color: QB.textPrimary }}>{tier1Match.name}</div>
                        <div className="text-xs" style={{ color: QB.textMuted }}>{getIndustry(tier1Match.industry).label} {"\u00B7"} {tier1Match.city}, {tier1Match.state} {"\u00B7"} {(tier1Match.vendors || 0) + (tier1Match.clients || 0)} connections</div>
                        <div className="text-[10px] mt-1" style={{ color: QB.textMuted }}>Also known as: {(tier1Match.variants || []).map(v => '"' + v + '"').join(", ")}</div>
                      </div>
                      <span className="text-xl font-bold" style={{ color: QB.green }}>{resolveResult?.confidence ? Math.round(resolveResult.confidence * 100) : 0}%</span>
                    </div>
                    <div className="space-y-1.5">
                      <ScoreBar label="Name" score={tier1Scores.name} />
                      <ScoreBar label="Industry" score={tier1Scores.industry} />
                      <ScoreBar label="Location" score={tier1Scores.location} />
                      <ScoreBar label="Commodity" score={tier1Scores.commodity} />
                    </div>
                    <div className="flex gap-2 pt-2">
                      <button onClick={() => handleConfirm(tier1Match)} className="flex-1 py-2.5 rounded text-sm font-medium text-white flex items-center justify-center gap-1.5" style={{ backgroundColor: QB.green }}>
                        <Check size={14} /> Add as my {connType}
                      </button>
                      <button onClick={() => handleConfirm(null)} className="flex-1 py-2.5 rounded text-sm border flex items-center justify-center gap-1.5" style={{ borderColor: QB.cardBorder, color: QB.textSecondary }}>
                        <XCircle size={14} /> Different business
                      </button>
                    </div>
                  </div>
                </div>
              )}

              {/* Tier 2 candidates */}
              {tier === 2 && !resolving && (
                <div className="space-y-3 pt-3 border-t" style={{ borderColor: QB.cardBorder }}>
                  <div className="flex items-center gap-2 text-xs">
                    <Sparkles size={12} style={{ color: QB.orange }} />
                    <span className="font-medium" style={{ color: QB.orange }}>Possible matches found</span>
                    <span style={{ color: QB.textMuted }}>{"\u2014"} Tier 2 Milvus search in {resolveResult?.latency || "---"}</span>
                  </div>
                  {tier2Candidates.map((cand, ci) => (
                    <div key={ci} className="p-3 rounded border space-y-2 cursor-pointer hover:shadow-sm transition-shadow"
                      style={{ borderColor: selectedCandidate?.id === cand.entity.id ? QB.orange + "60" : QB.cardBorder, backgroundColor: selectedCandidate?.id === cand.entity.id ? QB.orange + "05" : "white" }}
                      onClick={() => setSelectedCandidate(cand.entity)}>
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <div className="w-7 h-7 rounded flex items-center justify-center" style={{ backgroundColor: getIndustry(cand.entity.industry).color + "12" }}>
                            <Building2 size={12} style={{ color: getIndustry(cand.entity.industry).color }} />
                          </div>
                          <div>
                            <div className="text-sm font-medium" style={{ color: QB.textPrimary }}>{cand.entity.name}</div>
                            <div className="text-[10px]" style={{ color: QB.textMuted }}>{getIndustry(cand.entity.industry).label} {"\u00B7"} {cand.entity.city}, {cand.entity.state}</div>
                          </div>
                        </div>
                        <span className="text-base font-bold" style={{ color: cand.confidence >= 0.7 ? QB.orange : QB.red }}>{Math.round(cand.confidence * 100)}%</span>
                      </div>
                      {selectedCandidate?.id === cand.entity.id && (
                        <button onClick={(e) => { e.stopPropagation(); handleConfirm(selectedCandidate); }}
                          className="w-full py-2 rounded text-xs font-medium text-white flex items-center justify-center gap-1" style={{ backgroundColor: QB.green }}>
                          <Check size={12} /> Add as my {connType}
                        </button>
                      )}
                    </div>
                  ))}
                  <button onClick={() => handleConfirm(null)} className="w-full py-2 rounded text-xs border flex items-center justify-center gap-1.5" style={{ borderColor: QB.cardBorder, color: QB.textSecondary }}>
                    <Plus size={12} /> None {"\u2014"} Create new entity
                  </button>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
