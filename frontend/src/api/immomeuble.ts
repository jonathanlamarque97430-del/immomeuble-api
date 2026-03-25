/**
 * api/immomeuble.ts — Client HTTP IMMOMEUBLE
 *
 * API v1 (rétrocompatibilité) :
 *   generatePack          → POST /packs/generate        → PackScreenResponse
 *   fetchMerchantBreakdown → GET /packs/{id}/merchants  → MerchantBreakdownResponse
 *   getPackById           → GET /packs/{id}             → PackScreenResponse
 *
 * API v2 (nouveau) :
 *   createProjectV2        → POST /projects             → ProjectPackResponse
 *   getProjectPack         → GET /projects/{id}/pack    → ProjectPackResponse
 *   getProjectMerchantsV2  → GET /projects/{id}/retailers → RetailersResponse
 *   getProjectSummary      → GET /projects/{id}/summary → SummaryResponse
 *
 * Gestion des erreurs :
 *   - 422 Pydantic → message champ par champ
 *   - 5xx → message générique non-technique
 *   - network → message réseau
 */

// ── Imports v1 ────────────────────────────────────────────────────────────────
import type {
  ApiError,
  GeneratePackPayload,
  MerchantBreakdownResponse,
  PackScreenResponse,
} from "../types/immomeuble";

// ── Imports v2 (alignés sur schemas_v2.py via immomeuble.v2.ts) ──────────────
import type {
  ProjectCreateInput,
  ProjectPackResponse,
  RetailersResponse,
  SummaryResponse,
} from "../types/immomeuble.v2";

// ── Config ────────────────────────────────────────────────────────────────────

const API_BASE =
  typeof import.meta !== "undefined" && import.meta.env?.VITE_API_URL
    ? import.meta.env.VITE_API_URL
    : "http://localhost:8000";

// ── Helper erreur (partagé v1 + v2) ───────────────────────────────────────────

async function parseApiError(res: Response): Promise<ApiError> {
  let message = `Erreur serveur (${res.status}).`;
  let retry   = res.status >= 500;

  try {
    const body = await res.json();
    if (body?.detail?.message) {
      message = body.detail.message;
      retry   = body.detail.retry ?? retry;
    } else if (typeof body?.detail === "string") {
      message = body.detail;
    } else if (res.status === 422 && Array.isArray(body?.detail)) {
      const first = body.detail[0];
      const field = first?.loc?.slice(-1)[0] ?? "champ";
      message = `Champ invalide — ${field} : ${first?.msg ?? "valeur incorrecte"}`;
      retry   = false;
    } else if (res.status >= 500) {
      message = "Un problème est survenu côté serveur. Réessayez dans quelques instants.";
    }
  } catch (_) {
    // body non-JSON
  }

  return { message, retry, status: res.status };
}

// ════════════════════════════════════════════════════════════════════════════
// API v1 — /packs  (rétrocompatibilité, Step2/Step3 actuels)
// ════════════════════════════════════════════════════════════════════════════

/**
 * POST /packs/generate
 * Génère un pack LMNP (ancien endpoint v1).
 */
export async function generatePack(
  payload: GeneratePackPayload
): Promise<PackScreenResponse> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}/packs/generate`, {
      method:  "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body:    JSON.stringify(payload),
    });
  } catch (_) {
    throw {
      message: "Impossible de joindre le serveur. Vérifiez votre connexion.",
      retry:   true,
      status:  0,
    } satisfies ApiError;
  }
  if (!res.ok) throw await parseApiError(res);
  return res.json() as Promise<PackScreenResponse>;
}

/**
 * GET /packs/{packId}/merchants
 * Sourcing par enseigne (ancien endpoint v1).
 */
export async function fetchMerchantBreakdown(
  packId: string
): Promise<MerchantBreakdownResponse> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}/packs/${packId}/merchants`, {
      method:  "GET",
      headers: { Accept: "application/json" },
    });
  } catch (_) {
    throw {
      message: "Impossible de joindre le serveur. Vérifiez votre connexion.",
      retry:   true,
      status:  0,
    } satisfies ApiError;
  }
  if (!res.ok) throw await parseApiError(res);
  return res.json() as Promise<MerchantBreakdownResponse>;
}

/**
 * GET /packs/{packId}
 * Pack par id — URL partageable (ancien endpoint v1).
 */
export async function getPackById(
  packId: string
): Promise<PackScreenResponse> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}/packs/${packId}`, {
      headers: { Accept: "application/json" },
    });
  } catch (_) {
    throw {
      message: "Impossible de joindre le serveur.",
      retry:   true,
      status:  0,
    } satisfies ApiError;
  }
  if (!res.ok) throw await parseApiError(res);
  return res.json() as Promise<PackScreenResponse>;
}

// ════════════════════════════════════════════════════════════════════════════
// API v2 — /projects  (nouveaux endpoints, Step2V2 à venir)
// Types : immomeuble.v2.ts ↔ schemas_v2.py
// ════════════════════════════════════════════════════════════════════════════

/**
 * POST /projects
 * Crée un projet + génère le pack adaptatif (profil small/medium/large,
 * Budget/Standard/Premium, cible locataire).
 *
 * Payload : { property: PropertyCreateInput }
 *   — enveloppe ProjectCreate de schemas_v2.py
 * Retour  : ProjectPackResponse
 *   — pack.rooms[] et pack.lmnp_checklist[] sont dans pack (pas à la racine)
 */
export async function createProjectV2(
  input: ProjectCreateInput
): Promise<ProjectPackResponse> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}/projects`, {
      method:  "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body:    JSON.stringify({ property: input }),  // enveloppe ProjectCreate
    });
  } catch (_) {
    throw {
      message: "Impossible de joindre le serveur. Vérifiez votre connexion.",
      retry:   true,
      status:  0,
    } satisfies ApiError;
  }
  if (!res.ok) throw await parseApiError(res);
  return res.json() as Promise<ProjectPackResponse>;
}

/**
 * GET /projects/{id}/pack
 * Rafraîchit l'Étape 2 depuis un project_id existant.
 */
export async function getProjectPack(
  projectId: string
): Promise<ProjectPackResponse> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}/projects/${projectId}/pack`, {
      headers: { Accept: "application/json" },
    });
  } catch (_) {
    throw {
      message: "Impossible de joindre le serveur.",
      retry:   true,
      status:  0,
    } satisfies ApiError;
  }
  if (!res.ok) throw await parseApiError(res);
  return res.json() as Promise<ProjectPackResponse>;
}

/**
 * GET /projects/{id}/retailers
 * Sourcing par enseigne (Étape 3 v2).
 * Items : RetailerItemOut avec product_url (pas url) et room_label (pas room_name).
 */
export async function getProjectMerchantsV2(
  projectId: string
): Promise<RetailersResponse> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}/projects/${projectId}/retailers`, {
      headers: { Accept: "application/json" },
    });
  } catch (_) {
    throw {
      message: "Impossible de joindre le serveur.",
      retry:   true,
      status:  0,
    } satisfies ApiError;
  }
  if (!res.ok) throw await parseApiError(res);
  return res.json() as Promise<RetailersResponse>;
}

/**
 * GET /projects/{id}/summary
 * Résumé financier (Étape 4 v2).
 */
export async function getProjectSummary(
  projectId: string
): Promise<SummaryResponse> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}/projects/${projectId}/summary`, {
      headers: { Accept: "application/json" },
    });
  } catch (_) {
    throw {
      message: "Impossible de joindre le serveur.",
      retry:   true,
      status:  0,
    } satisfies ApiError;
  }
  if (!res.ok) throw await parseApiError(res);
  return res.json() as Promise<SummaryResponse>;
}
