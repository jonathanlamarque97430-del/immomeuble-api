/**
 * PackFlow.tsx — Composant racine du flux 4 étapes IMMOMEUBLE
 *
 * Gère l'état global et les transitions entre étapes :
 *   Étape 1 → POST /packs/generate     → Étape 2
 *   Étape 2 → GET /packs/{id}/merchants → Étape 3
 *   Étape 3 → Récapitulatif             → Étape 4 (à venir)
 */

import React, { useState } from "react";
import type {
  ApiError,
  MerchantBreakdownResponse,
  PackScreenResponse,
} from "./types/immomeuble";
import { fetchMerchantBreakdown } from "./api/immomeuble";
import { Step1PropertyForm } from "./steps/Step1PropertyForm";

type Step = 1 | 2 | 3 | 4;

export const PackFlow: React.FC = () => {
  // ── État global ────────────────────────────────────────────────────────
  const [step,        setStep]        = useState<Step>(1);
  const [packScreen,  setPackScreen]  = useState<PackScreenResponse | null>(null);
  const [merchants,   setMerchants]   = useState<MerchantBreakdownResponse | null>(null);

  // États Étape 3
  const [loadingMerchants, setLoadingMerchants] = useState(false);
  const [merchantsError,   setMerchantsError]   = useState<ApiError | null>(null);

  // ── Transitions ────────────────────────────────────────────────────────

  /** Étape 1 → 2 : appelé par Step1PropertyForm après succès API */
  function onPackGenerated(pack: PackScreenResponse) {
    setPackScreen(pack);
    setMerchants(null);      // invalider le cache merchants si regeneration
    setMerchantsError(null);
    setStep(2);
  }

  /** Étape 2 → 3 : fetch merchants puis navigate */
  async function goToStep3() {
    if (!packScreen) return;

    // Cache : si déjà chargé pour ce pack_id, navigation directe
    if (merchants && merchants.pack_id === packScreen.pack_id) {
      setStep(3);
      return;
    }

    setLoadingMerchants(true);
    setMerchantsError(null);

    try {
      const data = await fetchMerchantBreakdown(packScreen.pack_id);
      setMerchants(data);
      setStep(3);
    } catch (err) {
      setMerchantsError(err as ApiError);
      // On reste sur l'étape 2, erreur affichée dans Step3MerchantsScreen
      setStep(3);
    } finally {
      setLoadingMerchants(false);
    }
  }

  function goBackToStep1() { setStep(1); }
  function goBackToStep2() { setStep(2); }
  function goToStep4()     { setStep(4); }

  // ── Rendu ──────────────────────────────────────────────────────────────

  return (
    <div className="pack-flow">
      <Stepper current={step} />

      {step === 1 && (
        <Step1PropertyForm onPackGenerated={onPackGenerated} />
      )}

      {step === 2 && packScreen && (
        // Step2PackScreen à créer — reçoit packScreen + callbacks
        <Step2Placeholder
          packScreen={packScreen}
          onBack={goBackToStep1}
          onNext={goToStep3}
          loadingNext={loadingMerchants}
        />
      )}

      {step === 3 && (
        // Step3MerchantsScreen à créer
        <Step3Placeholder
          packScreen={packScreen}
          merchants={merchants}
          loading={loadingMerchants}
          error={merchantsError}
          onRetry={goToStep3}
          onBack={goBackToStep2}
          onNext={goToStep4}
        />
      )}

      {step === 4 && (
        <Step4Placeholder onBack={goBackToStep2} />
      )}
    </div>
  );
};

// ── Stepper ────────────────────────────────────────────────────────────────

const STEPS = ["Description", "Votre pack", "Enseignes", "Récap"];

const Stepper: React.FC<{ current: Step }> = ({ current }) => (
  <nav className="stepper" aria-label="Étapes">
    {STEPS.map((label, i) => {
      const n = (i + 1) as Step;
      const state = n < current ? "done" : n === current ? "active" : "pending";
      return (
        <div key={n} className={`step step--${state}`}>
          <div className="step-num">{state === "done" ? "✓" : n}</div>
          <span className="step-label">{label}</span>
        </div>
      );
    })}
  </nav>
);

// ── Placeholders (à remplacer par les vrais composants) ───────────────────

const Step2Placeholder: React.FC<{
  packScreen: PackScreenResponse;
  onBack: () => void;
  onNext: () => void;
  loadingNext: boolean;
}> = ({ packScreen, onBack, onNext, loadingNext }) => (
  <div className="step2">
    <h1>Votre pack LMNP</h1>
    <p><em>— Step2PackScreen à implémenter —</em></p>
    <pre style={{ fontSize: 11, maxHeight: 300, overflow: "auto" }}>
      {JSON.stringify(packScreen.pack_summary, null, 2)}
    </pre>
    <footer>
      <button onClick={onBack}>← Modifier</button>
      <button onClick={onNext} disabled={loadingNext}>
        {loadingNext ? "Chargement…" : "Voir les enseignes →"}
      </button>
    </footer>
  </div>
);

const Step3Placeholder: React.FC<{
  packScreen: PackScreenResponse | null;
  merchants: MerchantBreakdownResponse | null;
  loading: boolean;
  error: ApiError | null;
  onRetry: () => void;
  onBack: () => void;
  onNext: () => void;
}> = ({ packScreen, merchants, loading, error, onRetry, onBack, onNext }) => {
  if (loading) return <div>Chargement des enseignes…</div>;
  if (error) return (
    <div>
      <p>{error.message}</p>
      <button onClick={onRetry}>↻ Réessayer</button>
      <button onClick={onBack}>← Retour au pack</button>
    </div>
  );
  return (
    <div className="step3">
      <h1>Sourcing par enseigne</h1>
      <p><em>— Step3MerchantsScreen à implémenter —</em></p>
      {merchants && (
        <pre style={{ fontSize: 11, maxHeight: 300, overflow: "auto" }}>
          {JSON.stringify(merchants.summary, null, 2)}
        </pre>
      )}
      <footer>
        <button onClick={onBack}>← Retour au pack</button>
        <button onClick={onNext}>Récapitulatif →</button>
      </footer>
    </div>
  );
};

const Step4Placeholder: React.FC<{ onBack: () => void }> = ({ onBack }) => (
  <div className="step4">
    <h1>Récapitulatif projet &amp; ROI</h1>
    <p><em>— Step4RecapScreen à venir (v0.5) —</em></p>
    <button onClick={onBack}>← Retour</button>
  </div>
);
