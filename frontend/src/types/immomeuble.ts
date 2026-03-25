/**
 * types/immomeuble.ts — Contrats TypeScript alignés sur schemas.py (backend)
 *
 * IMPORTANT : ces types utilisent les noms exacts du backend Pydantic.
 * Ne pas utiliser de variantes sans underscore (ex: "jeuneactif").
 * L'API FastAPI valide via Literal et rejettera toute valeur hors enum.
 *
 * Référence backend : app/schemas.py → PropertyBase, PackScreenResponse,
 * MerchantBreakdownResponse (tests : 35 tests passent avec ces valeurs).
 */

// ── Enums (identiques aux Literal Pydantic) ────────────────────────────────

export type CibleLocataire =
  | "etudiant"
  | "jeune_actif"       // ← underscore obligatoire
  | "famille"
  | "courte_duree"      // ← underscore obligatoire
  | "professionnel";

export type NiveauGamme   = "economique" | "standard" | "premium";
export type PriorityLevel = "mandatory"  | "recommended" | "optional";
export type RoomType      =
  | "bedroom" | "living_room" | "kitchen" | "bathroom"
  | "entrance" | "office" | "balcony" | "other";
export type TypeLocation  = "longue_duree" | "courte_duree"; // ← underscore
export type LmnpStatus    = "compliant" | "ok_with_minor_missing" | "non_compliant";

// ── Payload POST /packs/generate (= PropertyBase backend) ─────────────────

export interface GeneratePackPayload {
  type_de_bien:             string;           // "T2", "studio", "coloc"…
  surface_totale:           number;           // >= 5
  nb_pieces:                number;           // >= 1
  cible_locataire:          CibleLocataire;
  niveau_gamme:             NiveauGamme;
  budget_min:               number;           // >= 0
  budget_max:               number;           // >= budget_min
  localisation_ville:       string;
  localisation_code_postal: string;           // 4–10 caractères
  style_souhaite?:          string | null;
  type_location?:           TypeLocation | null;
}

// ── Réponse POST /packs/generate (PackScreenResponse — Étape 2) ───────────

export interface PackScreenBrand {
  brand:  string;
  label?: string | null;
  url?:   string | null;
}

export interface PackScreenItem {
  item_id:           string;
  category:          string;
  name:              string;
  priority:          PriorityLevel;
  quantity:          number;
  unit_price:        number;
  total_price:       number;
  brands:            PackScreenBrand[];
  is_lmnp_mandatory: boolean;
  notes?:            string | null;
}

export interface PackScreenRoom {
  room_id:           string;
  type:              RoomType;
  name:              string;
  surface_estimated: number | null;
  room_total_cost:   number;
  items:             PackScreenItem[];
}

export interface PackScreenProperty {
  type_de_bien:     string;
  surface_totale:   number;
  nb_pieces:        number;
  ville:            string;
  code_postal:      string;
  cible_locataire:  CibleLocataire;
  style_souhaite:   string | null;
  niveau_gamme:     NiveauGamme;
  budget_total:     number;
  budget_min:       number;
  budget_max:       number;
}

export interface PackSummary {
  title:                       string;
  total_cost_estimated:        number;
  currency:                    string;
  lmnp_compliant:              boolean;
  lmnp_missing_categories:     string[];
  lmnp_missing_items_example:  string[];
  economy_vs_budget:           number;
  economy_vs_budget_percent:   number;
}

export interface LmnpChecklist {
  categories_covered:  string[];
  categories_missing:  string[];
  global_status:       LmnpStatus;
  notes?:              string | null;
}

export interface PackScreenResponse {
  project_id:     string;
  pack_id:        string;
  step:           number;    // = 2
  property:       PackScreenProperty;
  pack_summary:   PackSummary;
  rooms:          PackScreenRoom[];
  lmnp_checklist: LmnpChecklist;
}

// ── Réponse GET /packs/{pack_id}/merchants (Étape 3) ─────────────────────

export interface MerchantItem {
  room_name:   string;
  item_id:     string;
  item_name:   string;
  quantity:    number;
  unit_price:  number;
  total_price: number;
  reference?:  string | null;
  url?:        string | null;
}

export interface MerchantBlock {
  merchant_name:     string;
  merchant_logo?:    string | null;
  items:             MerchantItem[];
  merchant_subtotal: number;
}

export interface MerchantSummary {
  total_amount:              number;
  total_merchants:           number;
  total_items:               number;
  lmnp_status:               LmnpStatus;
  lmnp_missing_categories:   string[];
}

export interface MerchantBreakdownResponse {
  project_id: string;
  pack_id:    string;
  step:       number;    // = 3
  merchants:  MerchantBlock[];
  summary:    MerchantSummary;
}

// ── Erreur API typée ──────────────────────────────────────────────────────

export interface ApiError {
  message: string;
  retry:   boolean;
  status:  number;
}
