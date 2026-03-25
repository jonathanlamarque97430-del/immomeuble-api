/**
 * steps/Step2PackScreen.tsx — Étape 2/4 « Votre pack LMNP »
 *
 * Corrections vs document fourni :
 *   pack.packsummary          → pack.pack_summary
 *   pack.packsummary.lmnpcompliant → pack.pack_summary.lmnp_compliant
 *   pack.packsummary.totalcostestimated → pack.pack_summary.total_cost_estimated
 *   room.roomid               → room.room_id
 *   room.roomtotalcost        → room.room_total_cost
 *   item.itemid               → item.item_id
 *   item.totalprice           → item.total_price
 *   item.islmnpmandatory      → item.is_lmnp_mandatory
 */

import React, { useState } from "react";
import type {
  LmnpStatus,
  PackScreenItem,
  PackScreenResponse,
  PackScreenRoom,
} from "../types/immomeuble";

// ── Props ──────────────────────────────────────────────────────────────────

interface Step2Props {
  pack:   PackScreenResponse | null;
  onBack: () => void;
  onNext: () => void;
  loadingNext?: boolean;
}

// ── Helpers ────────────────────────────────────────────────────────────────

function fmtEur(n: number): string {
  return n.toLocaleString("fr-FR", { maximumFractionDigits: 0 }) + "\u202f€";
}

const PRIORITY_LABEL: Record<string, string> = {
  mandatory:   "Obligatoire LMNP",
  recommended: "Recommandé",
  optional:    "Optionnel",
};

const ROOM_LABEL: Record<string, string> = {
  bedroom:     "🛏 Chambre",
  living_room: "🛋 Séjour",
  kitchen:     "🍳 Cuisine",
  bathroom:    "🚿 Salle de bain",
  entrance:    "🚪 Entrée",
  office:      "💼 Bureau",
  balcony:     "🌿 Balcon",
  other:       "📦 Autre",
};

// ── Sous-composants ────────────────────────────────────────────────────────

const LmnpBadge: React.FC<{ compliant: boolean; status: LmnpStatus; missing: string[] }> = ({
  compliant, status, missing,
}) => {
  const isOk = status === "compliant";
  return (
    <span
      className={`lmnp-badge${isOk ? "" : " lmnp-badge--warn"}`}
      title={isOk
        ? "Tous les meubles et équipements essentiels sont présents pour y vivre au quotidien."
        : `Catégories manquantes\u202f: ${missing.join(", ")}`}
    >
      {isOk ? "✓ Conforme LMNP" : "⚠ Conformité partielle"}
    </span>
  );
};

const ItemRow: React.FC<{ item: PackScreenItem }> = ({ item }) => {
  const brand = item.brands?.[0];
  const brandStr = brand
    ? `${brand.brand}${brand.label ? "\u202f·\u202f" + brand.label : ""}`
    : "";
  const priorityLabel = PRIORITY_LABEL[item.priority] ?? item.priority;
  const isMandatory   = item.is_lmnp_mandatory;

  return (
    <li className={`item-row item-row--${item.priority}${isMandatory ? " item-row--mandatory" : ""}`}>
      <div className="item-main">
        <div className="item-info">
          <span className="item-name">{item.name}</span>
          {brandStr && <span className="item-brand">{brandStr}</span>}
        </div>
        <div className="item-right">
          {/* Tag pédagogique : Essentiel LMNP vs Confort */}
          {isMandatory ? (
            <span className="tag tag-essential" title="Obligatoire légalement — décret 2015-981">
              ✦ Essentiel LMNP
            </span>
          ) : (
            <span className="tag tag-comfort" title="Recommandé pour améliorer l'attractivité et réduire la rotation locataire">
              ＋ Confort
            </span>
          )}
          <span className="item-qty">&times;{item.quantity}</span>
          <span className="item-price">{fmtEur(item.total_price)}</span>
        </div>
      </div>
    </li>
  );
};

const RoomCard: React.FC<{ room: PackScreenRoom }> = ({ room }) => {
  const [open, setOpen] = useState(true);
  const label = ROOM_LABEL[room.type] ?? room.name;
  const mandatoryCount = room.items.filter((i) => i.priority === "mandatory").length;

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
          {mandatoryCount > 0 && (
            <span className="room-mandatory-count">
              {mandatoryCount} obligatoire{mandatoryCount > 1 ? "s" : ""}
            </span>
          )}
        </div>
        <div className="room-card__right">
          <span className="room-total">{fmtEur(room.room_total_cost)}</span>
          <span className="room-chevron">{open ? "▼" : "▶"}</span>
        </div>
      </button>

      {open && (
        <ul className="room-items" aria-label={`Articles ${label}`}>
          {room.items.map((item) => (
            <ItemRow key={item.item_id} item={item} />
          ))}
        </ul>
      )}
    </div>
  );
};

// ── Composant principal ────────────────────────────────────────────────────

export const Step2PackScreen: React.FC<Step2Props> = ({
  pack, onBack, onNext, loadingNext = false,
}) => {
  const hasPack = !!pack;
  const ps      = pack?.pack_summary;
  const cl      = pack?.lmnp_checklist;

  return (
    <div className="step2">
      <header className="step2-header">
        <div>
          <h1>Votre pack LMNP</h1>
          <p>
            Liste détaillée, pièce par pièce, avec le socle légal LMNP et des options de confort déjà sélectionnées.
          </p>
          {hasPack && ps && (
            <p className="pack-title-label">{ps.title}</p>
          )}
        </div>
        <div className="step2-header__badges">
          {hasPack && cl && (
            <LmnpBadge
              compliant={cl.global_status === "compliant"}
              status={cl.global_status}
              missing={cl.categories_missing}
            />
          )}
        </div>
      </header>

      {/* ── Résumé coût ── */}
      {hasPack && ps && (
        <section className="cost-summary" aria-label="Résumé budget">
          <div className="cost-main">
            <span className="cost-value">{fmtEur(ps.total_cost_estimated)}</span>
            <span className="cost-label">Coût total estimé</span>
            <small>Basé sur des prix publics d'enseignes nationales.</small>
            <small className="cost-reassurance">
              Les éléments <strong>Essentiel LMNP</strong> couvrent le décret 2015-981.
              Les éléments <strong>Confort</strong> sont là pour faciliter la location et justifier un meilleur loyer.
            </small>
          </div>
          <div className="cost-economy">
            {ps.economy_vs_budget >= 0 ? (
              <span className="economy-ok">
                ✓&nbsp;Économie de {fmtEur(ps.economy_vs_budget)}&nbsp;
                ({Math.abs(ps.economy_vs_budget_percent).toFixed(1)}&nbsp;%)
              </span>
            ) : (
              <span className="economy-over">
                ⚠&nbsp;Dépassement de {fmtEur(Math.abs(ps.economy_vs_budget))}
              </span>
            )}
            <small>Budget&nbsp;: {fmtEur(pack!.property.budget_min)}–{fmtEur(pack!.property.budget_max)}</small>
          </div>
        </section>
      )}

      {/* ── Pièces ── */}
      <section className="rooms-section" aria-label="Liste par pièce">
        {!hasPack ? (
          <p className="empty-state">
            Générez un pack à l'étape 1 pour voir ici la liste détaillée des pièces et des articles.
          </p>
        ) : (
          <>
            {pack!.rooms.map((room) => (
              <RoomCard key={room.room_id} room={room} />
            ))}

            {/* Légende Essentiel / Confort */}
            <section className="pack-legend" aria-label="Légende des tags">
              <strong>Lecture des tags&nbsp;:</strong>{" "}
              <span className="tag tag-essential">✦ Essentiel LMNP</span>
              {" "}= obligatoire légalement (décret 2015-981),{" "}
              <span className="tag tag-comfort">＋ Confort</span>
              {" "}= recommandé pour améliorer l'attractivité et réduire la rotation.
            </section>

            <p className="rooms-hint">
              Vous pouvez affiner plus tard, mais cette base suffit pour un dossier LMNP complet.
            </p>
          </>
        )}
      </section>

      {/* ── Checklist LMNP (sidebar ou bas de page) ── */}
      {hasPack && cl && (cl.categories_covered.length > 0 || cl.categories_missing.length > 0) && (
        <section className="lmnp-checklist" aria-label="Conformité LMNP">
          <h3>Conformité LMNP</h3>
          <ul>
            {cl.categories_covered.map((cat) => (
              <li key={cat} className="lmnp-cat lmnp-cat--ok">
                <span className="lmnp-dot lmnp-dot--ok" /> {cat}
              </li>
            ))}
            {cl.categories_missing.map((cat) => (
              <li key={cat} className="lmnp-cat lmnp-cat--miss">
                <span className="lmnp-dot lmnp-dot--miss" /> {cat}
              </li>
            ))}
          </ul>
          {cl.notes && <p className="lmnp-note">{cl.notes}</p>}
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
              disabled={!hasPack || loadingNext}
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
