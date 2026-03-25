/**
 * steps/Step4RecapScreen.tsx — Étape 4/4 « Récapitulatif projet & ROI »
 *
 * Corrections vs document fourni :
 *   merchants.summary.totalamount         → summary.total_amount
 *   pack.packsummary.totalcostestimated   → pack.pack_summary.total_cost_estimated
 *
 * Placeholder — enrichi en v0.5 avec KPIs, lien partage, ROI estimé.
 */

import React from "react";
import type {
  MerchantBreakdownResponse,
  PackScreenResponse,
} from "../types/immomeuble";

// ── Props ──────────────────────────────────────────────────────────────────

interface Step4Props {
  pack:      PackScreenResponse | null;
  merchants: MerchantBreakdownResponse | null;
  onBack:    () => void;
}

// ── Helpers ────────────────────────────────────────────────────────────────

function fmtEur(n: number): string {
  return n.toLocaleString("fr-FR", { maximumFractionDigits: 0 }) + "\u202f€";
}

// ── Composant ──────────────────────────────────────────────────────────────

export const Step4RecapScreen: React.FC<Step4Props> = ({
  pack, merchants, onBack,
}) => {
  // Source de vérité : summary.total_amount si disponible, sinon pack_summary
  const total =
    merchants?.summary.total_amount ??
    pack?.pack_summary.total_cost_estimated ??
    0;

  const ps = pack?.pack_summary;
  const cl = pack?.lmnp_checklist;

  return (
    <div className="step4">
      <header className="step4-header">
        <h1>Récapitulatif projet &amp; ROI</h1>
        <p>Synthèse du pack, budget global et éléments clés pour votre décision.</p>
      </header>

      {/* ── KPI principal : total ── */}
      <section className="recap-kpis" aria-label="Indicateurs clés">
        <div className="kpi-card kpi-card--primary">
          <div className="kpi-label">Montant total du pack</div>
          <div className="kpi-value">{fmtEur(total)}</div>
          {ps && (
            <div className="kpi-sub">
              Budget&nbsp;: {fmtEur(ps.economy_vs_budget >= 0 ? total + ps.economy_vs_budget : total - Math.abs(ps.economy_vs_budget))} max
            </div>
          )}
        </div>

        {/* Répartition enseignes */}
        {merchants && (
          <div className="kpi-card">
            <div className="kpi-label">Répartition par enseigne</div>
            <ul className="recap-merchants">
              {merchants.merchants.map((m) => (
                <li key={m.merchant_name} className="recap-merchant-row">
                  <span>{m.merchant_name}</span>
                  <span>{fmtEur(m.merchant_subtotal)}</span>
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* Conformité LMNP */}
        {cl && (
          <div className="kpi-card">
            <div className="kpi-label">Conformité LMNP</div>
            <div className={`kpi-status kpi-status--${cl.global_status}`}>
              {cl.global_status === "compliant"
                ? "✓ Conforme décret LMNP"
                : cl.global_status === "ok_with_minor_missing"
                ? "⚠ Conforme avec éléments mineurs manquants"
                : "✗ Non conforme"}
            </div>
            {cl.categories_missing.length > 0 && (
              <ul className="kpi-missing">
                {cl.categories_missing.map((cat) => (
                  <li key={cat}>{cat}</li>
                ))}
              </ul>
            )}
          </div>
        )}

        {/* Lien partage (Phase 3) */}
        {pack && (
          <div className="kpi-card">
            <div className="kpi-label">Lien partage projet</div>
            <p className="kpi-packid">
              Pack&nbsp;#{pack.pack_id.slice(0, 8)}…
            </p>
            <button
              type="button"
              className="btn-secondary"
              onClick={() =>
                navigator.clipboard
                  ?.writeText(`/packs/${pack.pack_id}`)
                  .catch(() => {})
              }
            >
              🔗 Copier le lien
            </button>
          </div>
        )}
      </section>

      {/* Placeholder KPIs Phase 3 */}
      <section className="recap-placeholder" aria-label="KPIs à venir">
        <p className="placeholder-note">
          🔜 Prochaine version&nbsp;: estimation ROI, amortissement mobilier,
          loyer de marché estimé, export PDF.
        </p>
      </section>

      <footer className="step4-footer">
        <span className="step-indicator">Étape 4 / 4</span>
        <button type="button" className="btn-secondary" onClick={onBack}>
          ← Retour aux enseignes
        </button>
      </footer>
    </div>
  );
};
