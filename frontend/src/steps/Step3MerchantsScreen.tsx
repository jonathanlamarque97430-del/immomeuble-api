import React from "react";
import type {
  ApiError,
  LmnpStatus,
  MerchantBlock,
  MerchantBreakdownResponse,
  MerchantItem,
  PackScreenResponse,
} from "../types/immomeuble";

interface Step3Props {
  pack:      PackScreenResponse | null;
  merchants: MerchantBreakdownResponse | null;
  loading:   boolean;
  error:     ApiError | null;
  onReload:  () => void;
  onBack:    () => void;
  onNext:    () => void;
}

function computeEssentielVsConfort(
  pack: PackScreenResponse | null,
  merchant: MerchantBlock
): { essentiels: number; confort: number } {
  if (!pack) return { essentiels: 0, confort: 0 };

  const index = new Map<string, boolean>();
  for (const room of pack.rooms) {
    for (const item of room.items) {
      index.set(item.item_id, item.is_lmnp_mandatory);
    }
  }

  let essentiels = 0;
  let confort    = 0;
  for (const mi of merchant.items) {
    if (index.get(mi.item_id) === true) {
      essentiels++;
    } else {
      confort++;
    }
  }
  return { essentiels, confort };
}

function fmtEur(n: number): string {
  return n.toLocaleString("fr-FR", { maximumFractionDigits: 0 }) + "\u202f€";
}

const LMNP_LABELS: Record<string, string> = {
  couchage:           "Couchage (lit + matelas)",
  occultation:        "Occultation (rideaux)",
  rangements:         "Rangements",
  plaques_cuisson:    "Plaques de cuisson",
  four_ou_microondes: "Four / micro-ondes",
  refrigerateur:      "Réfrigérateur",
  vaisselle:          "Vaisselle & couverts",
  ustensiles_cuisine: "Ustensiles de cuisine",
  table_chaises:      "Table + chaises",
  luminaires:         "Luminaires",
  entretien:          "Matériel d'entretien",
  equipements_sdb:    "Équipements SDB",
};

function lmnpLabel(cat: string): string {
  return LMNP_LABELS[cat] ?? cat;
}

const LmnpBadge: React.FC<{ status: LmnpStatus; missing: string[] }> = ({
  status, missing,
}) => {
  if (status === "compliant") {
    return (
      <span className="lmnp-badge">
        ✓ Conforme décret LMNP (meubles et équipements essentiels présents).
      </span>
    );
  }
  return (
    <span className="lmnp-badge lmnp-badge--warn">
      À compléter&nbsp;: {missing.map(lmnpLabel).join(", ")}
    </span>
  );
};

const MerchantItemRow: React.FC<{ item: MerchantItem }> = ({ item }) => (
  <li className="merchant-item">
    <div className="merchant-item__main">
      <div className="merchant-item__info">
        <span className="merchant-item__room">{item.room_name}</span>
        <span className="merchant-item__name">{item.item_name}</span>
        {item.reference && (
          <span className="merchant-item__ref">Réf.&nbsp;{item.reference}</span>
        )}
      </div>
      <div className="merchant-item__right">
        <span className="merchant-item__price">{fmtEur(item.total_price)}</span>
        <span className="merchant-item__qty">
          &times;{item.quantity}&nbsp;·&nbsp;{fmtEur(item.unit_price)}/u.
        </span>
        {item.url ? (
          <a
            href={item.url}
            target="_blank"
            rel="noopener noreferrer"
            className="merchant-item__link"
          >
            ↗ Voir le produit
          </a>
        ) : (
          <span className="merchant-item__link merchant-item__link--wip">
            ↗ Lien bientôt
          </span>
        )}
      </div>
    </div>
  </li>
);

const MerchantCard: React.FC<{
  merchant: MerchantBlock;
  pack:     PackScreenResponse | null;
}> = ({ merchant, pack }) => {
  const { essentiels, confort } = computeEssentielVsConfort(pack, merchant);

  return (
    <div className="merchant-card">
      <header className="merchant-card__header">
        <div className="merchant-card__title-row">
          <h3 className="merchant-name">{merchant.merchant_name}</h3>
          <span className="merchant-count">
            {merchant.items.length}&nbsp;article{merchant.items.length > 1 ? "s" : ""}
          </span>
        </div>
        <div className="merchant-kpis">
          {essentiels > 0 && (
            <span className="tag tag-essential">
              ✦&nbsp;{essentiels}&nbsp;essentiel{essentiels > 1 ? "s" : ""}&nbsp;LMNP
            </span>
          )}
          {confort > 0 && (
            <span className="tag tag-comfort">
              ＋&nbsp;{confort}&nbsp;confort
            </span>
          )}
        </div>
      </header>

      <ul className="merchant-items" aria-label={`Articles ${merchant.merchant_name}`}>
        {merchant.items.map((item) => (
          <MerchantItemRow key={item.item_id} item={item} />
        ))}
      </ul>

      <footer className="merchant-card__footer">
        <div>
          <span className="merchant-subtotal-label">
            Sous-total {merchant.merchant_name}
          </span>
          <span className="merchant-subtotal">{fmtEur(merchant.merchant_subtotal)}</span>
        </div>
        <button
          type="button"
          className="btn-secondary"
          onClick={() => alert(`Panier ${merchant.merchant_name} — disponible en Phase 3`)}
          title="Bientôt : export direct vers le site marchand."
        >
          🛒 Voir le panier
        </button>
      </footer>
    </div>
  );
};

export const Step3MerchantsScreen: React.FC<Step3Props> = ({
  pack, merchants, loading, error, onReload, onBack, onNext,
}) => {
  const hasData = !!merchants;
  const summary = merchants?.summary;

  return (
    <div className="step3">
      <header className="step3-header">
        <h1>Sourcing par enseigne</h1>
        <p>Sous-total et liste d'articles par marchand — prêt à commander.</p>
      </header>

      {pack && (
        <div className="context-bar">
          <span>
            {pack.property.type_de_bien}
            &nbsp;·&nbsp;
            {pack.property.surface_totale}
            &nbsp;m²&nbsp;·&nbsp;
            {pack.property.ville}
          </span>
          <span className="context-bar__sep" />
          <span className="context-bar__total">
            {fmtEur(pack.pack_summary.total_cost_estimated)}
          </span>
        </div>
      )}

      {loading && (
        <div className="loading-state" role="status" aria-live="polite">
          <span className="spinner" />
          Chargement des enseignes (quelques secondes)…
        </div>
      )}

      {!loading && error && (
        <div className="error-box" role="alert">
          <h2>Impossible d'afficher les enseignes</h2>
          <p>{error.message}</p>
          <div className="error-box__actions">
            <button type="button" className="btn-primary" onClick={onReload}>
              ↻ Réessayer
            </button>
            <button type="button" className="btn-secondary" onClick={onBack}>
              ← Retour au pack
            </button>
          </div>
        </div>
      )}

      {!loading && !error && !hasData && (
        <section className="empty-state" aria-label="Aucune donnée">
          <p>
            Revenez à l'étape 2 pour générer d'abord un pack,
            puis accédez au détail par enseigne.
          </p>
          <p className="empty-stats">— enseignes · — articles</p>
          <span className="lmnp-badge">✓ Conforme LMNP</span>
        </section>
      )}

      {!loading && !error && hasData && summary && (
        <>
          <section className="merchants-summary" aria-label="Résumé enseignes">
            <p className="merchants-total">
              {fmtEur(summary.total_amount)}&nbsp;·&nbsp;
              {summary.total_merchants}&nbsp;enseigne{summary.total_merchants > 1 ? "s" : ""}&nbsp;·&nbsp;
              {summary.total_items}&nbsp;article{summary.total_items > 1 ? "s" : ""}&nbsp;·&nbsp;
              {summary.total_merchants}&nbsp;commande{summary.total_merchants > 1 ? "s" : ""}
            </p>
            <LmnpBadge
              status={summary.lmnp_status}
              missing={summary.lmnp_missing_categories}
            />
          </section>

          <section className="pack-legend" aria-label="Légende des tags">
            <strong>Lecture&nbsp;:</strong>{" "}
            <span className="tag tag-essential">✦ Essentiel LMNP</span>
            {" "} = obligatoire légalement,{" "}
            <span className="tag tag-comfort">＋ Confort</span>
            {" "} = recommandé pour mieux louer et limiter la rotation.
          </section>

          <section className="merchants-list" aria-label="Enseignes">
            {merchants!.merchants.map((m) => (
              <MerchantCard key={m.merchant_name} merchant={m} pack={pack} />
            ))}
          </section>
        </>
      )}

      <footer className="step3-footer">
        <span className="step-indicator">Étape 3 / 4</span>
        <div className="step3-footer__actions">
          <button type="button" className="btn-secondary" onClick={onBack}>
            ← Retour au pack
          </button>
          <button
            type="button"
            className="btn-primary"
            onClick={onNext}
            disabled={!hasData}
          >
            Récapitulatif →
          </button>
        </div>
      </footer>
    </div>
  );
};
