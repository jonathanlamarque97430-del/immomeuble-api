/**
 * steps/Step1PropertyForm.tsx
 *
 * Formulaire Étape 1/4 — "Décrivez votre bien"
 *
 * Mapping champs HTML → GeneratePackPayload (backend PropertyBase) :
 *   form.type_de_bien             → type_de_bien
 *   form.surface_totale           → surface_totale (float)
 *   form.nb_pieces                → nb_pieces (int)
 *   form.ville                    → localisation_ville
 *   form.code_postal              → localisation_code_postal (4–10 chars)
 *   form.cible_locataire          → cible_locataire  (enum avec underscores)
 *   form.style_souhaite           → style_souhaite   (nullable)
 *   form.type_location            → type_location    (nullable, avec underscore)
 *   form.niveau_gamme             → niveau_gamme
 *   form.budget_min / budget_max  → budget_min / budget_max
 *
 * Corrections vs document fourni :
 *   "jeuneactif"  → "jeune_actif"  (le backend valide avec underscore)
 *   "courteduree" → "courte_duree"
 *   "longueduree" → "longue_duree"
 */

import React, { useCallback, useState } from "react";

import type {
  ApiError,
  CibleLocataire,
  GeneratePackPayload,
  NiveauGamme,
  PackScreenResponse,
  TypeLocation,
} from "../types/immomeuble";
import type {
  ProjectCreateInput,
  ProjectPackResponse,
} from "../types/immomeuble.v2";
import { generatePack, createProjectV2 } from "../api/immomeuble";

// ── Types internes ─────────────────────────────────────────────────────────

interface FormState {
  type_de_bien:    string;
  surface_totale:  string;   // string pour gérer la saisie
  nb_pieces:       string;
  ville:           string;
  code_postal:     string;
  cible_locataire: CibleLocataire;
  style_souhaite:  string;
  type_location:   TypeLocation | "";
  niveau_gamme:    NiveauGamme;
  budget_min:      string;
  budget_max:      string;
}

interface FormErrors {
  surface_totale?:  string;
  nb_pieces?:       string;
  ville?:           string;
  code_postal?:     string;
  budget_min?:      string;
  budget_max?:      string;
}

const INITIAL_STATE: FormState = {
  type_de_bien:    "T2",
  surface_totale:  "45",
  nb_pieces:       "2",
  ville:           "",
  code_postal:     "",
  cible_locataire: "jeune_actif",  // ← underscore obligatoire
  style_souhaite:  "",
  type_location:   "",
  niveau_gamme:    "standard",
  budget_min:      "3000",
  budget_max:      "6000",
};

// Budgets par défaut selon la gamme
const GAMME_BUDGETS: Record<NiveauGamme, { min: number; max: number }> = {
  economique: { min: 1500, max: 3000 },
  standard:   { min: 3000, max: 6000 },
  premium:    { min: 6000, max: 12000 },
};

// ── Props ──────────────────────────────────────────────────────────────────

interface Step1Props {
  onPackGenerated:   (pack: PackScreenResponse) => void;
  onPackGeneratedV2?: (pack: ProjectPackResponse) => void;  // optionnel — active le flow v2
}

// ── Validation locale ──────────────────────────────────────────────────────

function validateForm(form: FormState): FormErrors {
  const errors: FormErrors = {};
  const surf = Number(form.surface_totale);
  if (isNaN(surf) || surf < 5 || surf > 500)
    errors.surface_totale = "Surface : 5 – 500 m²";

  const pieces = Number(form.nb_pieces);
  if (isNaN(pieces) || pieces < 1 || pieces > 10)
    errors.nb_pieces = "1 à 10 pièces";

  if (!form.ville.trim())
    errors.ville = "Ville requise";

  const cp = form.code_postal.trim();
  if (!cp || cp.length < 4 || cp.length > 10)
    errors.code_postal = "Code postal invalide (4–10 caractères)";

  const bmin = Number(form.budget_min);
  const bmax = Number(form.budget_max);
  if (isNaN(bmin) || bmin < 0)
    errors.budget_min = "Budget minimum invalide";
  if (isNaN(bmax) || bmax < 0)
    errors.budget_max = "Budget maximum invalide";
  if (!errors.budget_min && !errors.budget_max && bmax < bmin)
    errors.budget_max = "Budget max doit être ≥ budget min";

  return errors;
}

// ── buildPayload ───────────────────────────────────────────────────────────

function buildPayload(form: FormState): GeneratePackPayload {
  return {
    type_de_bien:             form.type_de_bien,
    surface_totale:           Number(form.surface_totale),
    nb_pieces:                Number(form.nb_pieces),
    localisation_ville:       form.ville.trim(),
    localisation_code_postal: form.code_postal.trim(),
    cible_locataire:          form.cible_locataire,     // "jeune_actif" etc.
    style_souhaite:           form.style_souhaite || null,
    type_location:            (form.type_location as TypeLocation) || null,
    niveau_gamme:             form.niveau_gamme,
    budget_min:               Number(form.budget_min),
    budget_max:               Number(form.budget_max),
  };
}

// ── buildPayloadV2 (API /projects) ─────────────────────────────────────────
// Mapping des champs FormState → PropertyCreateInput (immomeuble.v2.ts)
//   form.type_de_bien  → property_type
//   form.ville         → city
//   form.code_postal   → postal_code
//   form.cible_locataire → tenant_profile
//   form.niveau_gamme  → budget_level

function buildPayloadV2(form: FormState): ProjectCreateInput {
  return {
    property_type:  form.type_de_bien as ProjectCreateInput["property_type"],
    surface_m2:     Number(form.surface_totale),
    rooms_count:    Number(form.nb_pieces),
    city:           form.ville.trim(),
    postal_code:    form.code_postal.trim(),
    tenant_profile: form.cible_locataire as ProjectCreateInput["tenant_profile"],
    rental_type:    (form.type_location as ProjectCreateInput["rental_type"]) || null,
    decor_style:    form.style_souhaite || null,
    budget_level:   form.niveau_gamme as ProjectCreateInput["budget_level"],
    budget_min:     Number(form.budget_min),
    budget_max:     Number(form.budget_max),
  };
}

// ── Composant principal ────────────────────────────────────────────────────

export const Step1PropertyForm: React.FC<Step1Props> = ({ onPackGenerated, onPackGeneratedV2 }) => {
  const [form,           setForm]           = useState<FormState>(INITIAL_STATE);
  const [fieldErrors,    setFieldErrors]    = useState<FormErrors>({});
  const [loading,        setLoading]        = useState(false);
  const [apiError,       setApiError]       = useState<ApiError | null>(null);
  const [showErrorModal, setShowErrorModal] = useState(false);

  // ── Setters ──────────────────────────────────────────────────────────────

  function set<K extends keyof FormState>(key: K, value: FormState[K]) {
    setForm((prev) => ({ ...prev, [key]: value }));
    // Effacer l'erreur du champ modifié
    setFieldErrors((prev) => ({ ...prev, [key]: undefined }));
  }

  const selectGamme = useCallback((gamme: NiveauGamme) => {
    const { min, max } = GAMME_BUDGETS[gamme];
    setForm((prev) => ({
      ...prev,
      niveau_gamme: gamme,
      budget_min:   String(min),
      budget_max:   String(max),
    }));
  }, []);

  // ── Submit ───────────────────────────────────────────────────────────────

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();

    const errors = validateForm(form);
    if (Object.keys(errors).length > 0) {
      setFieldErrors(errors);
      return;
    }

    setLoading(true);
    setApiError(null);

    try {
      const payload = buildPayload(form);
      const pack    = await generatePack(payload);
      onPackGenerated(pack);
    } catch (err) {
      const apiErr = err as ApiError;
      setApiError(apiErr);
      setShowErrorModal(true);
    } finally {
      setLoading(false);
    }
  }

  async function handleRetry() {
    setShowErrorModal(false);
    // Déclencher manuellement sans passer par l'event form
    setLoading(true);
    setApiError(null);
    try {
      const payload = buildPayload(form);
      const pack    = await generatePack(payload);
      onPackGenerated(pack);
    } catch (err) {
      const apiErr = err as ApiError;
      setApiError(apiErr);
      setShowErrorModal(true);
    } finally {
      setLoading(false);
    }
  }

  // ── Submit v2 (/projects) ───────────────────────────────────────────────

  const [loadingV2, setLoadingV2] = useState(false);
  const [apiErrorV2, setApiErrorV2] = useState<ApiError | null>(null);

  async function handleSubmitV2() {
    const errors = validateForm(form);
    if (Object.keys(errors).length > 0) {
      setFieldErrors(errors);
      return;
    }
    if (!onPackGeneratedV2) return;

    setLoadingV2(true);
    setApiErrorV2(null);
    try {
      const payload  = buildPayloadV2(form);
      const response = await createProjectV2(payload);
      onPackGeneratedV2(response);
    } catch (err) {
      setApiErrorV2(err as ApiError);
    } finally {
      setLoadingV2(false);
    }
  }

  // ── Render ───────────────────────────────────────────────────────────────

  return (
    <div className="step1">
      <header className="step1-header">
        <h1>Décrivez votre bien</h1>
        <p>Générez en 10 secondes un pack LMNP complet, optimisé pour votre bien.</p>
      </header>

      <form onSubmit={handleSubmit} noValidate className="step1-form">
        <section className="card">
          <h2>Caractéristiques du bien &amp; budget mobilier</h2>
          <p className="card-desc">
            Ces informations permettent de dimensionner le pack et de vérifier la conformité LMNP.
          </p>

          {/* ── Type de bien ── */}
          <Field label="Type de bien *">
            <select
              value={form.type_de_bien}
              onChange={(e) => set("type_de_bien", e.target.value)}
            >
              <option value="studio">Studio</option>
              <option value="T1">T1</option>
              <option value="T2">T2</option>
              <option value="T3">T3</option>
              <option value="T4+">T4+</option>
              <option value="coloc">Colocation</option>
            </select>
            <small>Sélectionnez le type principal du lot à meubler.</small>
          </Field>

          {/* ── Surface ── */}
          <Field label="Surface (m²) *" error={fieldErrors.surface_totale}>
            <input
              type="number"
              min={5}
              max={500}
              value={form.surface_totale}
              onChange={(e) => set("surface_totale", e.target.value)}
            />
            <small>Surface habitable approximative.</small>
          </Field>

          {/* ── Nb pièces ── */}
          <Field label="Nombre de pièces *" error={fieldErrors.nb_pieces}>
            <input
              type="number"
              min={1}
              max={10}
              value={form.nb_pieces}
              onChange={(e) => set("nb_pieces", e.target.value)}
            />
            <small>Hors cuisine et salle de bain.</small>
          </Field>

          {/* ── Ville ── */}
          <Field label="Ville *" error={fieldErrors.ville}>
            <input
              type="text"
              value={form.ville}
              placeholder="Paris…"
              onChange={(e) => set("ville", e.target.value)}
            />
          </Field>

          {/* ── Code postal ── */}
          <Field label="Code postal *" error={fieldErrors.code_postal}>
            <input
              type="text"
              maxLength={10}
              value={form.code_postal}
              placeholder="75011"
              onChange={(e) => set("code_postal", e.target.value)}
            />
          </Field>

          {/* ── Cible locataire ── */}
          <Field label="Cible locataire *">
            <select
              value={form.cible_locataire}
              onChange={(e) => set("cible_locataire", e.target.value as CibleLocataire)}
            >
              {/* Valeurs avec underscores — obligatoire pour le backend */}
              <option value="etudiant">Étudiant</option>
              <option value="jeune_actif">Jeune actif</option>
              <option value="famille">Famille</option>
              <option value="courte_duree">Courte durée / Airbnb</option>
              <option value="professionnel">Professionnel</option>
            </select>
            <small>Nous adaptons le pack au profil de votre locataire cible.</small>
          </Field>

          {/* ── Style déco (optionnel) ── */}
          <Field label="Style déco">
            <select
              value={form.style_souhaite}
              onChange={(e) => set("style_souhaite", e.target.value)}
            >
              <option value="">— Aucune préférence —</option>
              <option value="contemporain">Contemporain</option>
              <option value="scandinave">Scandinave</option>
              <option value="industriel">Industriel</option>
              <option value="boheme">Bohème</option>
              <option value="minimaliste">Minimaliste</option>
            </select>
          </Field>

          {/* ── Type de location (optionnel) ── */}
          <Field label="Type de location">
            <select
              value={form.type_location}
              onChange={(e) => set("type_location", (e.target.value as TypeLocation) || "")}
            >
              <option value="">— Non précisé —</option>
              {/* Valeurs avec underscores — obligatoire pour le backend */}
              <option value="longue_duree">Longue durée</option>
              <option value="courte_duree">Courte durée</option>
            </select>
          </Field>

          {/* ── Niveau de gamme ── */}
          <div className="field-group">
            <label className="field-label">Niveau de gamme *</label>
            <div className="gamme-cards">
              {(
                [
                  { value: "economique", label: "Budget",   range: "1 500 – 3 000 €", desc: "Conformité LMNP, entrée de gamme." },
                  { value: "standard",   label: "Standard", range: "3 000 – 6 000 €", desc: "Confort optimal, rotation réduite." },
                  { value: "premium",    label: "Premium",  range: "6 000 – 12 000 €",desc: "Différenciation, loyer supérieur." },
                ] as const
              ).map(({ value, label, range, desc }) => (
                <GammeCard
                  key={value}
                  label={label}
                  description={desc}
                  range={range}
                  selected={form.niveau_gamme === value}
                  onSelect={() => selectGamme(value)}
                />
              ))}
            </div>
          </div>

          {/* ── Budget indicatif (slider + min/max) ── */}
          <div className="field-group">
            <label className="field-label">Budget mobilier indicatif</label>
            <div className="budget-range">
              <Field label="Min (€)" error={fieldErrors.budget_min} inline>
                <input
                  type="number"
                  min={0}
                  max={15000}
                  value={form.budget_min}
                  onChange={(e) => set("budget_min", e.target.value)}
                />
              </Field>
              <span className="budget-sep">–</span>
              <Field label="Max (€)" error={fieldErrors.budget_max} inline>
                <input
                  type="number"
                  min={0}
                  max={15000}
                  value={form.budget_max}
                  onChange={(e) => set("budget_max", e.target.value)}
                />
              </Field>
            </div>
            <small>
              Nous ajusterons le contenu du pack pour rester dans cette enveloppe,
              tout en respectant la conformité LMNP.
            </small>
          </div>
        </section>

        <footer className="step1-footer">
          <button type="submit" className="btn-primary" disabled={loading}>
            {loading
              ? <><span className="spinner" /> Génération en cours…</>
              : "✦ Générer mon pack LMNP →"}
          </button>

          {/* Bouton v2 — visible uniquement si le flow v2 est branché */}
          {onPackGeneratedV2 && (
            <button
              type="button"
              className="btn-secondary"
              disabled={loadingV2}
              onClick={handleSubmitV2}
              title="Génère le pack via /projects (API v2 adaptative)"
            >
              {loadingV2
                ? <><span className="spinner" /> v2 en cours…</>
                : "⚡ Tester l'API v2 →"}
            </button>
          )}

          {apiErrorV2 && (
            <p className="field-error" role="alert">
              v2 : {apiErrorV2.message}
            </p>
          )}

          <p className="hint">Temps moyen : 5 à 10 secondes.</p>
          <p className="step-indicator">Étape 1 / 4 — Champs * obligatoires</p>
        </footer>
      </form>

      {/* ── Modal erreur API ── */}
      {showErrorModal && (
        <div className="modal-overlay" role="dialog" aria-modal="true">
          <div className="modal">
            <h2>Impossible de générer le pack</h2>
            <p>
              {apiError?.message
                ?? "Un problème est survenu côté serveur. Réessayez dans quelques instants."}
            </p>
            <div className="modal-actions">
              {(apiError?.retry ?? true) && (
                <button type="button" className="btn-primary" onClick={handleRetry}>
                  ↻ Réessayer
                </button>
              )}
              <button
                type="button"
                className="btn-secondary"
                onClick={() => setShowErrorModal(false)}
              >
                Fermer
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

// ── Sous-composants ────────────────────────────────────────────────────────

interface FieldProps {
  label:    string;
  error?:   string;
  inline?:  boolean;
  children: React.ReactNode;
}

const Field: React.FC<FieldProps> = ({ label, error, inline, children }) => (
  <div className={`field-group${inline ? " field-group--inline" : ""}`}>
    <label className="field-label">{label}</label>
    {children}
    {error && <span className="field-error" role="alert">{error}</span>}
  </div>
);

interface GammeCardProps {
  label:       string;
  description: string;
  range:       string;
  selected:    boolean;
  onSelect:    () => void;
}

const GammeCard: React.FC<GammeCardProps> = ({
  label, description, range, selected, onSelect,
}) => (
  <button
    type="button"
    className={`gamme-card${selected ? " gamme-card--selected" : ""}`}
    onClick={onSelect}
    aria-pressed={selected}
  >
    <div className="gamme-card-header">
      <strong>{label}</strong>
      <span className="gamme-range">{range}</span>
    </div>
    <p className="gamme-desc">{description}</p>
  </button>
);
