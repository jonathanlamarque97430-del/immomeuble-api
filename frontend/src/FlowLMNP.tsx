/**
 * FlowLMNP.tsx — Orchestrateur 4 étapes IMMOMEUBLE
 *
 * v2 : branche Step2PackScreenV2 quand le flow utilise /projects (createProjectV2).
 *      Flow v1 (/packs) conservé intact en parallèle.
 *
 * Logique de bascule :
 *   packV2 !== null  → Step2PackScreenV2 + getProjectMerchantsV2
 *   packV2 === null  → Step2PackScreen v1 + fetchMerchantBreakdown (inchangé)
 *
 * Corrections vs document fourni :
 *   packScreen.packid          → packScreen.pack_id
 *   merchantsError: string     → merchantsError: ApiError | null
 *   onBack: handleBackToStep3  → onBack: handleBackToStep2 (étape 4 revient à 3, pas 2)
 */

import React, { useState } from "react";

// ── Types v1 ──────────────────────────────────────────────────────────────────
import type {
  ApiError,
  MerchantBreakdownResponse,
  PackScreenResponse,
} from "./types/immomeuble";

// ── Types v2 ──────────────────────────────────────────────────────────────────
import type {
  ProjectCreateInput,
  ProjectPackResponse,
  RetailersResponse,
} from "./types/immomeuble.v2";

// ── API v1 ────────────────────────────────────────────────────────────────────
import {
  fetchMerchantBreakdown,
  createProjectV2,
  getProjectMerchantsV2,
} from "./api/immomeuble";

// ── Composants ────────────────────────────────────────────────────────────────
import { Step1PropertyForm }    from "./steps/Step1PropertyForm";
import { Step2PackScreen }      from "./steps/Step2PackScreen";
import { Step2PackScreenV2 }    from "./steps/Step2PackScreenV2";
import { Step3MerchantsScreen } from "./steps/Step3MerchantsScreen";
import { Step4RecapScreen }     from "./steps/Step4RecapScreen";

// ── Types ─────────────────────────────────────────────────────────────────────

type Step = 1 | 2 | 3 | 4;

// ── Stepper ───────────────────────────────────────────────────────────────────

const STEP_LABELS: Record<Step, string> = {
  1: "Description",
  2: "Votre pack",
  3: "Enseignes",
  4: "Récap",
};

const Stepper: React.FC<{ current: Step }> = ({ current }) => (
  <nav className="stepper" aria-label="Étapes du flux">
    {([1, 2, 3, 4] as Step[]).map((n) => {
      const status = n < current ? "done" : n === current ? "active" : "pending";
      return (
        <React.Fragment key={n}>
          <div
            className={`step step--${status}`}
            aria-current={n === current ? "step" : undefined}
          >
            <div className="step-num">{status === "done" ? "✓" : n}</div>
            <span className="step-label">{STEP_LABELS[n]}</span>
          </div>
          {n < 4 && <div className="step-sep" aria-hidden="true" />}
        </React.Fragment>
      );
    })}
  </nav>
);

// ── FlowLMNP ──────────────────────────────────────────────────────────────────

export const FlowLMNP: React.FC = () => {
  // ── State v1 (conservé intact) ─────────────────────────────────────────────
  const [step,       setStep]       = useState<Step>(1);
  const [packScreen, setPackScreen] = useState<PackScreenResponse | null>(null);
  const [merchants,  setMerchants]  = useState<MerchantBreakdownResponse | RetailersResponse | null>(null);

  const [loadingMerchants, setLoadingMerchants] = useState(false);
  const [merchantsError,   setMerchantsError]   = useState<ApiError | null>(null);

  // ── State v2 ───────────────────────────────────────────────────────────────
  // packV2 !== null → le flow courant utilise /projects (API v2)
  const [packV2, setPackV2] = useState<ProjectPackResponse | null>(null);

  // ── Transition 1 → 2 — génération via API v1 (Step1 existant) ─────────────

  function handlePackGenerated(pack: PackScreenResponse) {
    setPackScreen(pack);
    setPackV2(null);          // s'assurer qu'on est en mode v1
    setMerchants(null);
    setMerchantsError(null);
    setStep(2);
  }

  // ── Transition 1 → 2 — génération via API v2 (/projects) ──────────────────
  // Appelé depuis Step1 si on veut tester le flow v2.
  // Actuellement branché sur le bouton "Générer (v2)" — à activer dans Step1.

  const [loadingV2, setLoadingV2] = useState(false);
  const [errorV2,   setErrorV2]   = useState<ApiError | null>(null);

  async function handleGenerateV2(input: ProjectCreateInput) {
    setLoadingV2(true);
    setErrorV2(null);
    try {
      const response = await createProjectV2(input);
      setPackV2(response);
      setPackScreen(null);    // s'assurer qu'on est en mode v2
      setMerchants(null);
      setMerchantsError(null);
      setStep(2);
    } catch (err) {
      setErrorV2(err as ApiError);
    } finally {
      setLoadingV2(false);
    }
  }

  // ── Transition 2 → 3 — compatible v1 et v2 ────────────────────────────────

  async function handleGoToStep3() {
    // Cache : éviter un double-fetch si déjà chargé pour ce projet
    if (packV2 && merchants) {
      setMerchantsError(null);
      setStep(3);
      return;
    }
    if (!packV2 && packScreen && merchants &&
        (merchants as MerchantBreakdownResponse).pack_id === packScreen.pack_id) {
      setMerchantsError(null);
      setStep(3);
      return;
    }

    setLoadingMerchants(true);
    setMerchantsError(null);

    try {
      if (packV2) {
        // Flow v2 : GET /projects/{project_id}/retailers
        const data = await getProjectMerchantsV2(packV2.project_id);
        setMerchants(data);
      } else if (packScreen) {
        // Flow v1 : GET /packs/{pack_id}/merchants (logique existante)
        const data = await fetchMerchantBreakdown(packScreen.pack_id);
        setMerchants(data);
      } else {
        return;   // aucun pack — ne devrait pas arriver
      }
      setStep(3);
    } catch (err) {
      setMerchantsError(err as ApiError);
      setStep(3);   // afficher l'erreur sur l'écran 3
    } finally {
      setLoadingMerchants(false);
    }
  }

  // ── Transitions simples ────────────────────────────────────────────────────

  function handleBackToStep1() { setStep(1); }
  function handleBackToStep2() { setStep(2); }
  function handleBackToStep3() { setStep(3); }   // Step4 revient sur 3
  function handleGoToStep4()   { setStep(4); }

  // ── Render ─────────────────────────────────────────────────────────────────

  return (
    <div className="flow-lmnp">
      <Stepper current={step} />

      {/* Étape 1 — formulaire (inchangé, génère en v1) */}
      {step === 1 && (
        <Step1PropertyForm
          onPackGenerated={handlePackGenerated}
          onPackGeneratedV2={handleGenerateV2}
        />
      )}

      {/* Étape 2 — bascule v1 / v2 selon le pack disponible */}
      {step === 2 && (
        packV2 ? (
          // Flow v2 : ProjectPackResponse depuis /projects
          <Step2PackScreenV2
            pack={packV2}
            loading={loadingV2}
            error={errorV2}
            onReload={() => setStep(1)}
            onBack={handleBackToStep1}
            onNext={handleGoToStep3}
          />
        ) : (
          // Flow v1 : PackScreenResponse depuis /packs (inchangé)
          <Step2PackScreen
            pack={packScreen}
            onBack={handleBackToStep1}
            onNext={handleGoToStep3}
            loadingNext={loadingMerchants}
          />
        )
      )}

      {/* Étape 3 — fonctionne avec merchants v1 ou v2 */}
      {step === 3 && (
        <Step3MerchantsScreen
          pack={packScreen}
          merchants={merchants as MerchantBreakdownResponse | null}
          loading={loadingMerchants}
          error={merchantsError}
          onReload={handleGoToStep3}
          onBack={handleBackToStep2}
          onNext={handleGoToStep4}
        />
      )}

      {/* Étape 4 */}
      {step === 4 && (
        <Step4RecapScreen
          pack={packScreen}
          merchants={merchants as MerchantBreakdownResponse | null}
          onBack={handleBackToStep3}
        />
      )}
    </div>
  );
};
