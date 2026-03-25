/**
 * types/immomeuble.v2.ts
 * Types TypeScript alignés exactement sur app/schemas_v2.py
 *
 * Correspondances directes :
 *   TagType                ↔ Literal["essentiel_lmnp", "confort"]
 *   PropertyCreateInput    ↔ PropertyCreate
 *   ProjectCreatePayload   ↔ ProjectCreate  { property: PropertyCreate }
 *   PropertyOut            ↔ PropertyOut
 *   PackItemOut            ↔ PackItemOut
 *   RoomOut                ↔ RoomOut
 *   LmnpCriterionStatus    ↔ LmnpCriterionStatus
 *   PackOut                ↔ PackOut         { rooms[], lmnp_checklist[] }
 *   ProjectPackResponse    ↔ ProjectPackResponse
 *   RetailerItemOut        ↔ RetailerItemOut
 *   RetailerBlockOut       ↔ RetailerBlockOut
 *   RetailersResponse      ↔ RetailersResponse
 *   RetailerSummaryLine    ↔ RetailerSummaryLine
 *   SummaryResponse        ↔ SummaryResponse
 *
 * Corrections vs squelette fourni :
 *   project_id → string (pas number)
 *   city / postal_code (pas ville)
 *   rooms dans PackOut (pas à la racine de ProjectPackResponse)
 *   lmnp_checklist dans PackOut (pas summary)
 *   retailers (pas merchants) dans RetailersResponse
 *   room_label (pas room_name) dans RetailerItemOut
 *   product_url (pas url) dans RetailerItemOut
 *   budget_level "economique" (pas "budget")
 */

// ─────────────────────────────────────────────────────────────────────────────
// Enums — valeurs exactes validées par Pydantic côté backend
// ─────────────────────────────────────────────────────────────────────────────

/** PackItemOut.tag_type + RetailerItemOut.tag_type */
export type TagType = "essentiel_lmnp" | "confort";

/** PropertyCreate.property_type */
export type PropertyType =
  | "studio" | "T1" | "T2" | "T3" | "T4+" | "coloc";

/** PropertyCreate.tenant_profile */
export type TenantProfile =
  | "etudiant" | "jeune_actif" | "famille" | "courte_duree" | "professionnel";

/** PropertyCreate.budget_level — "economique" (pas "budget") */
export type BudgetLevel = "economique" | "standard" | "premium";

/** PropertyCreate.rental_type */
export type RentalType = "longue_duree" | "courte_duree";


// ─────────────────────────────────────────────────────────────────────────────
// INPUT — POST /projects
// Corps : { property: PropertyCreateInput }
// ─────────────────────────────────────────────────────────────────────────────

/** schemas_v2.PropertyCreate */
export interface PropertyCreateInput {
  property_type:  PropertyType;
  surface_m2:     number;          // >= 5, <= 500
  rooms_count:    number;          // >= 1, <= 10

  city:           string;          // ← "city" (pas "ville")
  postal_code:    string;          // 4–10 caractères

  tenant_profile: TenantProfile;
  rental_type?:   RentalType | null;
  decor_style?:   string | null;

  budget_level:   BudgetLevel;
  budget_min?:    number | null;
  budget_max?:    number | null;
}

/** schemas_v2.ProjectCreate — corps de POST /projects */
export interface ProjectCreatePayload {
  property: PropertyCreateInput;
}


// ─────────────────────────────────────────────────────────────────────────────
// OUTPUT — POST /projects + GET /projects/{id} + GET /projects/{id}/pack
// ─────────────────────────────────────────────────────────────────────────────

/** schemas_v2.LmnpCriterionStatus — un critère du décret 2015-981 */
export interface LmnpCriterionStatus {
  code:       string;   // ex: "couchage", "vaisselle" — utilisé via c.code
  label:      string;   // ex: "Couchage (lit + matelas)"
  is_covered: boolean;
}

/** schemas_v2.PackItemOut — ligne item Étape 2 */
export interface PackItemOut {
  id:          string;
  name:        string;
  reference:   string | null;
  retailer:    string;          // nom enseigne dénormalisé
  tag_type:    TagType;         // "essentiel_lmnp" | "confort"
  unit_price:  number;          // € entiers
  quantity:    number;
  total_price: number;
  product_url: string | null;   // Phase 2 — lien cliquable
}

/** schemas_v2.RoomOut — pièce avec ses items */
export interface RoomOut {
  id:                    string;
  room_type:             string;   // "chambre", "sejour", "cuisine", "sdb"…
  label:                 string;   // libellé affiché (ex: "Chambre principale")
  mandatory_items_count: number;   // nb items tag_type == "essentiel_lmnp"
  total_price:           number;
  items:                 PackItemOut[];
}

/** schemas_v2.PropertyOut — rappel du brief dans la réponse */
export interface PropertyOut {
  property_type:  PropertyType;
  surface_m2:     number;
  rooms_count:    number;
  city:           string;
  postal_code:    string;
  tenant_profile: TenantProfile;
  rental_type:    RentalType | null;
  decor_style:    string | null;
  budget_level:   BudgetLevel;
  budget_min:     number | null;
  budget_max:     number | null;
}

/**
 * schemas_v2.PackOut
 * ⚠ rooms[] et lmnp_checklist[] sont dans PackOut, PAS à la racine.
 * Accès : response.pack.rooms  et  response.pack.lmnp_checklist
 */
export interface PackOut {
  id:                string;
  total_price:       number;
  is_lmnp_compliant: boolean;
  savings_amount:    number | null;
  savings_percent:   number | null;
  rooms:             RoomOut[];             // dans PackOut
  lmnp_checklist:    LmnpCriterionStatus[]; // dans PackOut
}

/**
 * schemas_v2.ProjectPackResponse
 * Réponse de POST /projects, GET /projects/{id}, GET /projects/{id}/pack
 */
export interface ProjectPackResponse {
  project_id:  string;   // UUID string (pas number)
  public_slug: string;   // ex: "paris-t2-standard-3f2a1b8c"
  property:    PropertyOut;
  pack:        PackOut;  // rooms et lmnp_checklist sont dans pack
}


// ─────────────────────────────────────────────────────────────────────────────
// OUTPUT — GET /projects/{id}/retailers  (Étape 3)
// ─────────────────────────────────────────────────────────────────────────────

/**
 * schemas_v2.RetailerItemOut
 * ⚠ room_label (pas room_name), product_url (pas url)
 */
export interface RetailerItemOut {
  item_id:     string;
  room_label:  string;          // ← "room_label" (pas "room_name")
  name:        string;
  reference:   string | null;
  tag_type:    TagType;
  unit_price:  number;
  quantity:    number;
  total_price: number;
  product_url: string | null;   // ← "product_url" (pas "url")
}

/** schemas_v2.RetailerBlockOut — un bloc enseigne */
export interface RetailerBlockOut {
  retailer_id:     string;
  name:            string;
  website_url:     string | null;
  subtotal:        number;
  item_count:      number;
  essential_count: number;   // items tag_type == "essentiel_lmnp"
  comfort_count:   number;   // items tag_type == "confort"
  items:           RetailerItemOut[];
}

/** schemas_v2.RetailersResponse — GET /projects/{id}/retailers */
export interface RetailersResponse {
  total_amount:      number;
  retailer_count:    number;
  item_count:        number;
  order_count:       number;
  is_lmnp_compliant: boolean;
  retailers:         RetailerBlockOut[];  // ← "retailers" (pas "merchants")
}


// ─────────────────────────────────────────────────────────────────────────────
// OUTPUT — GET /projects/{id}/summary  (Étape 4)
// ─────────────────────────────────────────────────────────────────────────────

/** schemas_v2.RetailerSummaryLine */
export interface RetailerSummaryLine {
  name:     string;
  subtotal: number;
}

/** schemas_v2.SummaryResponse — GET /projects/{id}/summary */
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


// ─────────────────────────────────────────────────────────────────────────────
// Helpers utilitaires
// ─────────────────────────────────────────────────────────────────────────────

/** Résout product_url quel que soit le shape reçu (v1 url ou v2 product_url) */
export function resolveProductUrl(
  item: { url?: string | null; product_url?: string | null }
): string | null {
  return item.product_url ?? item.url ?? null;
}

/** true si l'item est obligatoire LMNP */
export const isEssentiel = (tag: TagType): boolean =>
  tag === "essentiel_lmnp";

/** Libellé affiché du tag */
export const tagLabel = (tag: TagType): string =>
  tag === "essentiel_lmnp" ? "✦ Essentiel LMNP" : "＋ Confort";

/** Formatage montant en euros (ex: "3 815 €") */
export const fmtEur = (n: number): string =>
  n.toLocaleString("fr-FR", { maximumFractionDigits: 0 }) + "\u202f€";

/** Ligne de résumé pack (sous-titre Étape 2) */
export function buildPackSummaryLine(
  property: PropertyOut,
  pack: PackOut
): string {
  const profileLabels: Record<string, string> = {
    etudiant: "Étudiant", jeune_actif: "Jeune actif",
    famille: "Famille", courte_duree: "Courte durée",
    professionnel: "Professionnel",
  };
  const gammeLabels: Record<BudgetLevel, string> = {
    economique: "Budget", standard: "Standard", premium: "Premium",
  };
  const profile = profileLabels[property.tenant_profile] ?? property.tenant_profile;
  const gamme   = gammeLabels[property.budget_level]     ?? property.budget_level;
  return `Optimisé pour ${profile} à ${property.city} — ${property.property_type} ${property.surface_m2} m² · ${gamme} · ${fmtEur(pack.total_price)}`;
}
