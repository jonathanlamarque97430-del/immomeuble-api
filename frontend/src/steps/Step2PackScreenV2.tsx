/**
 * steps/Step2PackScreenV2.tsx — Étape 2/4 « Votre pack LMNP » (API v2)
 *
 * Port fidèle de Step2PackScreen v1 adapté à ProjectPackResponse.
 * Mapping v1 → v2 :
 *   PackScreenResponse       → ProjectPackResponse
 *   pack.pack_summary        → pack.pack  (PackOut)
 *   ps.total_cost_estimated  → pack.pack.total_price
 *   ps.economy_vs_budget     → pack.pack.savings_amount
 *   pack.lmnp_checklist      → pack.pack.lmnp_checklist  (dans PackOut)
 *   cl.global_status         → po.is_lmnp_compliant (bool direct)
 *   cl.categories_covered/missing → lmnp_checklist[].is_covered
 *   pack.property.type_de_bien   → pack.property.property_type
 *   pack.property.surface_totale → pack.property.surface_m2
 *   pack.property.ville          → pack.property.city
 *   room.room_id  → room.id      room.type → room.room_type
 *   room.name     → room.label   room.room_total_cost → room.total_price
 *   item.item_id  → item.id      item.priority/brands → item.tag_type
 */

import React, { useState } from "react";
import type { ApiError } from "../types/immomeuble";
import type {
  PackItemOut,
  ProjectPackResponse,
  RoomOut,
} from "../types/immomeuble.v2";

// ── Props ──────────────────────────────────────────────────────────────────

interface Step2V2Props {
  pack:        ProjectPackResponse | null;
  loading:     boolean;
  error:       ApiError | null;
  onReload:    () => void;
  onBack:      () => void;
  onNext:      () => void;
  loadingNext?: boolean;
}

// ── Helpers ────────────────────────────────────────────────────────────────

function fmtEur(n: number): string {
  return n.toLocaleString("fr-FR", { maximumFractionDigits: 0 }) + "\u202f€";
}

const ROOM_LABEL: Record<string, string> = {
  // Types v2 (generator.py)
  chambre:        "🛏 Chambre",
  chambre_sejour: "🛋 Chambre / Séjour",
  sejour:         "🛋 Séjour",
  cuisine:        "🍳 Cuisine",
  sdb:            "🚿 Salle de bain",
  // Types v1 (compatibilité)
  bedroom:        "🛏 Chambre",
  living_room:    "🛋 Séjour",
  kitchen:        "🍳 Cuisine",
  bathroom:       "🚿 Salle de bain",
  entrance:       "🚪 Entrée",
  office:         "💼 Bureau",
  balcony:        "🌿 Balcon",
  other:          "📦 Autre",
};

// ── Sous-composants ────────────────────────────────────────────────────────

const LmnpBadge: React.FC<{ compliant: boolean }> = ({ compliant }) => (
  <span
    className={`lmnp-badge${compliant ? "" : " lmnp-badge--warn"}`}
    title={compliant
      ? "Tous les meubles et équipements essentiels sont présents pour y vivre au quotidien."
      : "Certaines catégories LMNP ne sont pas encore couvertes."}
  >
    {compliant ? "✓ Conforme LMNP" : "⚠ Conformité partielle"}
  </span>
);

const ItemRow: React.FC<{ item: PackItemOut }> = ({ item }) => {
  const isEssentiel = item.tag_type === "essentiel_lmnp";
  return (
    <li className={`item-row${isEssentiel ? " item-row--mandatory" : ""}`}>
      <div className="item-main">
        <div className="item-info">
          <span className="item-name">{item.name}</span>
          {item.retailer && <span className="item-brand">{item.retailer}</span>}
          {item.reference && <span className="item-ref">Réf.&nbsp;{item.reference}</span>}
        </div>
        <div className="item-right">
          {isEssentiel ? (
            <span className="tag tag-essential" title="Obligatoire légalement — décret 2015-981">
              ✦ Essentiel LMNP
            </span>
          ) : (
            <span className="tag tag-comfort" title="Recommandé pour améliorer l'attractivité">
              ＋ Confort
            </span>
          )}
          <span className="item-qty">&times;{item.quantity}</span>
          <span className="item-price">{fmtEur(item.total_price)}</span>
          {item.product_url && (
            <a href={item.product_url} target="_blank" rel="noopener noreferrer" className="item-link">↗</a>
          )}
        </div>
      </div>
    </li>
  );
};

const RoomCard: React.FC<{ room: RoomOut }> = ({ room }) => {
  const [open, setOpen] = useState(true);
  const label = room.label || ROOM_LABEL[room.room_type] || room.room_type;
  return (
    <div className="room-card">
      <button
        type="button"
        className="room-card__header"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
      >
        <div className="room-card__title">
          <span className="room-name">{label}</span>
          {room.mandatory_items_count > 0 && (
            <span className="room-mandatory-count">
              {room.mandatory_items_count} essentiel{room.mandatory_items_count > 1 ? "s" : ""} LMNP
            </span>
          )}
        </div>
        <div className="room-card__right">
          <span className="room-total">{fmtEur(room.total_price)}</span>
          <span className="room-chevron">{open ? "▼" : "▶"}</span>
        </div>
      </button>
      {open && (
        <ul className="room-items" aria-label={`Articles ${label}`}>
          {room.items.map((item) => (
            <ItemRow key={item.id} item={item} />
          ))}
        </ul>
      )}
    </div>
  );
};

// ── Composant principal ────────────────────────────────────────────────────

export const Step2PackScreenV2: React.FC<Step2V2Props> = ({
  pack, loading, error, onReload, onBack, onNext, loadingNext = false,
}) => {
  const hasPack    = !!pack;
  const po         = pack?.pack;
  const prop       = pack?.property;
  const cl         = pack?.pack.lmnp_checklist;
  const covered    = cl?.filter((c) => c.is_covered)  ?? [];
  const missing    = cl?.filter((c) => !c.is_covered) ?? [];
  const savings    = po?.savings_amount  ?? null;
  const savingsPct = po?.savings_percent ?? null;
  const isOverBudget = savings !== null && savings < 0;

  return (
    <div className="step2">
      <header className="step2-header">
        <div>
          <h1>Votre pack LMNP</h1>
          <p>Liste détaillée, pièce par pièce, avec le socle légal LMNP et des options de confort.</p>
          {hasPack && prop && (
            <p className="pack-title-label">
              {prop.property_type} {prop.surface_m2}&nbsp;m²
              {prop.city ? ` · ${prop.city}` : ""}
              {" · "}{prop.budget_level}
              {prop.tenant_profile ? ` · ${prop.tenant_profile}` : ""}
            </p>
          )}
        </div>
        <div className="step2-header__badges">
          {hasPack && po && <LmnpBadge compliant={po.is_lmnp_compliant} />}
        </div>
      </header>

      {loading && (
        <div className="loading-state" role="status" aria-live="polite">
          <span className="spinner" /> Génération du pack en cours…
        </div>
      )}

      {!loading && error && (
        <div className="error-box" role="alert">
          <h2>Impossible de générer le pack</h2>
          <p>{error.message}</p>
          <div className="error-box__actions">
            <button type="button" className="btn-primary" onClick={onReload}>↻ Réessayer</button>
            <button type="button" className="btn-secondary" onClick={onBack}>← Retour</button>
          </div>
        </div>
      )}

      {/* ── Résumé coût ── */}
      {hasPack && po && !loading && !error && (
        <section className="cost-summary" aria-label="Résumé budget">
          <div className="cost-main">
            <span className="cost-value">{fmtEur(po.total_price)}</span>
            <span className="cost-label">Coût total estimé</span>
            <small>Basé sur des prix publics d'enseignes nationales.</small>
            <small className="cost-reassurance">
              Les éléments <strong>Essentiel LMNP</strong> couvrent le décret 2015-981.
              Les éléments <strong>Confort</strong> facilitent la location et justifient un meilleur loyer.
            </small>
          </div>
          {savings !== null && prop?.budget_max && (
            <div className="cost-economy">
              {!isOverBudget ? (
                <span className="economy-ok">
                  ✓&nbsp;Économie de {fmtEur(Math.abs(savings))}
                  {savingsPct !== null && <>&nbsp;({Math.abs(savingsPct).toFixed(1)}&nbsp;%)</>}
                </span>
              ) : (
                <span className="economy-over">⚠&nbsp;Dépassement de {fmtEur(Math.abs(savings))}</span>
              )}
              <small>Budget&nbsp;: {fmtEur(prop.budget_min ?? 0)}–{fmtEur(prop.budget_max)}</small>
            </div>
          )}
        </section>
      )}

      {/* ── Pièces ── */}
      {!loading && !error && (
      <section className="rooms-section" aria-label="Liste par pièce">
        {!hasPack ? (
          <p className="empty-state">Générez un pack à l'étape 1 pour voir la liste détaillée.</p>
        ) : (
          <>
            {po!.rooms.map((room) => (
              <RoomCard key={room.id} room={room} />
            ))}

            {/* Légende Essentiel / Confort */}
            <section className="pack-legend" aria-label="Légende des tags">
              <strong>Lecture des tags&nbsp;:</strong>{" "}
              <span className="tag tag-essential">✦ Essentiel LMNP</span>
              {" "}= obligatoire légalement (décret 2015-981),{" "}
              <span className="tag tag-comfort">＋ Confort</span>
              {" "}= recommandé pour améliorer l'attractivité et réduire la rotation.
            </section>

            <p className="rooms-hint">Cette base suffit pour un dossier LMNP complet.</p>
          </>
        )}
      </section>
      )}

      {/* ── Checklist LMNP v2 ── */}
      {hasPack && !loading && !error && (covered.length > 0 || missing.length > 0) && (
        <section className="lmnp-checklist" aria-label="Conformité LMNP">
          <h3>Conformité LMNP — décret 2015-981</h3>
          <ul>
            {covered.map((c) => (
              <li key={c.code} className="lmnp-cat lmnp-cat--ok">
                <span className="lmnp-dot lmnp-dot--ok" /> {c.label}
              </li>
            ))}
            {missing.map((c) => (
              <li key={c.code} className="lmnp-cat lmnp-cat--miss">
                <span className="lmnp-dot lmnp-dot--miss" /> {c.label}
              </li>
            ))}
          </ul>
        </section>
      )}

      <footer className="step2-footer">
        <span className="step-indicator">Étape 2 / 4</span>
        <div className="step2-footer__actions">
          <button type="button" className="btn-secondary" onClick={onBack}>
            ← Modifier les informations
          </button>
          <div>
            <button
              type="button"
              className="btn-primary"
              onClick={onNext}
              disabled={!hasPack || loadingNext || loading}
            >
              {loadingNext ? "Chargement…" : "Voir les enseignes →"}
            </button>
            <p className="action-hint">Répartition du pack par marchand (IKEA, But, etc.).</p>
          </div>
        </div>
      </footer>
    </div>
  );
};
