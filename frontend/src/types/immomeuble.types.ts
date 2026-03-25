/**
 * immomeuble.types.ts
 * Types TypeScript générés depuis les modèles SQLAlchemy + schemas Pydantic.
 *
 * Règle de nommage :
 *   - Les types *Input  = ce qu'on envoie au backend (POST /projects)
 *   - Les types *Out    = ce qu'on reçoit du backend (GET /projects/{id}/pack)
 *   - Les types *UI     = vues enrichies construites côté front à partir des *Out
 *
 * Correspondance directe avec :
 *   models.py  → Project, Property, Pack, Room, PackItem, Retailer, LmnpCriterion
 *   schemas.py → PropertyCreate, ProjectCreate, PackItemOut, RoomOut,
 *                PropertyOut, PackOut, ProjectPackResponse
 */

// ─────────────────────────────────────────────────────────
// 1. ENUMS — valeurs attendues par le backend (String en DB)
// ─────────────────────────────────────────────────────────

/** Property.property_type */
export type PropertyType =
  | 'studio' | 'T1' | 'T2' | 'T3' | 'T4+' | 'coloc';

/** Property.tenant_profile */
export type TenantProfile =
  | 'etudiant' | 'jeune_actif' | 'famille' | 'courte_duree' | 'professionnel';

/** Property.rental_type */
export type RentalType = 'longue_duree' | 'courte_duree';

/** Property.decor_style */
export type DecorStyle =
  | 'contemporain' | 'scandinave' | 'industriel' | 'boheme' | 'minimaliste';

/** Property.budget_level */
export type BudgetLevel = 'economique' | 'standard' | 'premium';

/** PackItem.tag_type — CHAMP CLÉ : détermine l'affichage Essentiel/Confort */
export type TagType = 'essentiel_lmnp' | 'confort';

/** Room.room_type */
export type RoomType =
  | 'bedroom' | 'living_room' | 'kitchen' | 'bathroom'
  | 'entrance' | 'office' | 'balcony' | 'other';


// ─────────────────────────────────────────────────────────
// 2. INPUT — payload POST /projects
//    Correspond à schemas.py : ProjectCreate → PropertyCreate
// ─────────────────────────────────────────────────────────

/** schemas.PropertyCreate */
export interface PropertyCreateInput {
  property_type:  PropertyType;
  surface_m2:     number;
  rooms_count:    number;
  city:           string;
  postal_code:    string;
  tenant_profile: TenantProfile;
  rental_type?:   RentalType | null;
  decor_style?:   DecorStyle | null;
  budget_level:   BudgetLevel;
  budget_min?:    number | null;
  budget_max?:    number | null;
}

/** schemas.ProjectCreate — corps de POST /projects */
export interface ProjectCreateInput {
  property: PropertyCreateInput;
}


// ─────────────────────────────────────────────────────────
// 3. OUTPUT — réponses API
//    Correspond à schemas.py : ProjectPackResponse
// ─────────────────────────────────────────────────────────

/**
 * schemas.LmnpCriterionStatus
 * Un critère de la checklist décret 2015-981.
 * code  → clé stable (ex: "couchage", "vaisselle")
 * label → libellé affiché (ex: "Couchage (lit + matelas)")
 */
export interface LmnpCriterionStatus {
  code:       string;
  label:      string;
  is_covered: boolean;
}

/**
 * schemas.PackItemOut
 * Une ligne d'item dans une pièce.
 * tag_type → "essentiel_lmnp" | "confort"  (remplace is_lmnp_mandatory)
 */
export interface PackItemOut {
  id:          string;
  name:        string;
  reference:   string | null;
  retailer:    string;           // nom de l'enseigne (dénormalisé pour l'affichage)
  tag_type:    TagType;
  unit_price:  number;           // centimes ou entier €, à confirmer avec le backend
  quantity:    number;
  total_price: number;
  product_url?: string | null;   // futur lien produit (Phase 3)
}

/**
 * schemas.RoomOut
 * Une pièce avec ses items.
 * room_type → clé stable (bedroom, kitchen…)
 * label     → libellé lisible (peut différer de ROOM_NAME[room_type])
 */
export interface RoomOut {
  id:                    string;
  room_type:             RoomType;
  label:                 string;
  mandatory_items_count: number;
  total_price:           number;
  items:                 PackItemOut[];
}

/** schemas.PropertyOut — rappel du brief dans la réponse */
export interface PropertyOut {
  property_type:  PropertyType;
  surface_m2:     number;
  rooms_count:    number;
  city:           string;
  postal_code:    string;
  tenant_profile: TenantProfile;
  rental_type:    RentalType | null;
  decor_style:    DecorStyle | null;
  budget_level:   BudgetLevel;
  budget_min:     number | null;
  budget_max:     number | null;
}

/** schemas.PackOut — données financières + pièces + checklist */
export interface PackOut {
  id:                string;
  total_price:       number;
  is_lmnp_compliant: boolean;
  savings_amount:    number | null;
  savings_percent:   number | null;
  rooms:             RoomOut[];
  lmnp_checklist:    LmnpCriterionStatus[];
}

/**
 * schemas.ProjectPackResponse
 * Réponse de :
 *   POST /projects
 *   GET  /projects/{id}
 *   GET  /projects/{id}/pack
 */
export interface ProjectPackResponse {
  project_id:  string;
  public_slug: string;
  property:    PropertyOut;
  pack:        PackOut;
}


// ─────────────────────────────────────────────────────────
// 4. RETAILERS — GET /projects/{id}/retailers
//    Non encore défini dans schemas.py, shape anticipée
// ─────────────────────────────────────────────────────────

/** Une ligne d'item enrichie pour l'écran 3 (room_label ajouté) */
export interface RetailerItemOut extends PackItemOut {
  room_label: string;  // label de la pièce, résolu côté backend ou front
}

/** Un bloc enseigne pour l'écran 3 */
export interface RetailerBlockOut {
  retailer_id:     string;
  name:            string;
  website_url?:    string | null;
  subtotal:        number;
  item_count:      number;
  essential_count: number;  // items où tag_type === "essentiel_lmnp"
  comfort_count:   number;  // items où tag_type === "confort"
  items:           RetailerItemOut[];
}

/** Réponse de GET /projects/{id}/retailers */
export interface RetailersResponse {
  total_amount:      number;
  retailer_count:    number;
  item_count:        number;
  order_count:       number;
  is_lmnp_compliant: boolean;
  retailers:         RetailerBlockOut[];
}


// ─────────────────────────────────────────────────────────
// 5. SUMMARY — GET /projects/{id}/summary
//    Non encore défini dans schemas.py, shape anticipée
// ─────────────────────────────────────────────────────────

export interface RetailerSummaryLine {
  name:     string;
  subtotal: number;
}

/** Réponse de GET /projects/{id}/summary */
export interface SummaryResponse {
  project_id:        string;
  public_slug:       string;
  total_amount:      number;
  budget_max:        number | null;
  savings_amount:    number | null;
  is_lmnp_compliant: boolean;
  retailers_summary: RetailerSummaryLine[];
  lmnp_checklist:    LmnpCriterionStatus[];
}


// ─────────────────────────────────────────────────────────
// 6. STATE APPLICATIF — AppState côté front
// ─────────────────────────────────────────────────────────

export type Step = 1 | 2 | 3 | 4;

export interface AppState {
  step:            Step;
  project_id:      string | null;
  public_slug:     string | null;
  /** Réponse complète de POST /projects ou GET /projects/{id}/pack */
  projectPack:     ProjectPackResponse | null;
  /** Réponse de GET /projects/{id}/retailers (chargée à la demande) */
  retailers:       RetailersResponse | null;
  /** Réponse de GET /projects/{id}/summary (chargée à la demande) */
  summary:         SummaryResponse | null;
  /** Copie locale du formulaire Étape 1 (avant création du projet) */
  draftProperty:   PropertyCreateInput | null;
  /** Niveau de gamme sélectionné dans l'UI */
  budgetLevel:     BudgetLevel;
}


// ─────────────────────────────────────────────────────────
// 7. HELPERS UI — constantes et fonctions de mapping
// ─────────────────────────────────────────────────────────

export const BUDGET_LEVEL_CONFIG: Record<BudgetLevel, {
  min: number; max: number; mid: number; label: string;
}> = {
  economique: { min: 1500, max: 3000,  mid: 2250, label: 'Budget · 1 500 – 3 000 €'   },
  standard:   { min: 3000, max: 6000,  mid: 4500, label: 'Standard · 3 000 – 6 000 €' },
  premium:    { min: 6000, max: 12000, mid: 9000,  label: 'Premium · 6 000 – 12 000 €' },
};

export const TENANT_PROFILE_LABELS: Record<TenantProfile, string> = {
  etudiant:      'Étudiant',
  jeune_actif:   'Jeune actif',
  famille:       'Famille',
  courte_duree:  'Courte durée / Airbnb',
  professionnel: 'Professionnel',
};

export const BUDGET_LEVEL_LABELS: Record<BudgetLevel, string> = {
  economique: 'Budget',
  standard:   'Standard',
  premium:    'Premium',
};

/** tag_type → booléen utilitaire */
export const isEssentiel = (tag: TagType): boolean =>
  tag === 'essentiel_lmnp';

/** tag_type → libellé affiché */
export const tagLabel = (tag: TagType): string =>
  tag === 'essentiel_lmnp' ? '✦ Essentiel LMNP' : '＋ Confort';

/** Formatage montant en euros (ex: 3 815 €) */
export const fmtEur = (n: number): string =>
  n.toLocaleString('fr-FR', { maximumFractionDigits: 0 }) + '\u202f€';

/** Ligne de résumé projet (sous-titre Étape 2) */
export const buildProjectSummaryLine = (
  property: PropertyOut,
  pack: PackOut
): string => {
  const profile = TENANT_PROFILE_LABELS[property.tenant_profile] ?? property.tenant_profile;
  const level   = BUDGET_LEVEL_LABELS[property.budget_level]     ?? property.budget_level;
  return `Optimisé pour ${profile} à ${property.city} — ${property.property_type} ${property.surface_m2} m² · ${level} · ${fmtEur(pack.total_price)}`;
};


// ─────────────────────────────────────────────────────────────────────────────
// PHASE 2 — product_url : note sur le mapping frontend
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Mapping product_url → url selon l'endpoint utilisé :
 *
 *   GET /packs/{id}/merchants  (v1 — schemas.py)
 *     MerchantItem.url         → string | null
 *     Utilisé dans : Step3MerchantsScreen.tsx → item.url
 *
 *   GET /projects/{id}/retailers (v2 — schemas_v2.py)
 *     RetailerItemOut.product_url → string | null
 *     Utilisé dans : HTML v15 → item.product_url
 *
 * Les deux champs contiennent la même donnée (product_url en base).
 * La différence de nom est un vestige de la migration v1→v2.
 * À unifier en "product_url" lors du passage à l'API v2 complète.
 */
export type ProductUrlField = "url" | "product_url";

// Helper : résout le lien produit quel que soit le shape reçu
export function resolveProductUrl(
  item: { url?: string | null; product_url?: string | null }
): string | null {
  return item.product_url ?? item.url ?? null;
}
