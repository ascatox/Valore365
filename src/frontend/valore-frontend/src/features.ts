// Feature flags (frontend)

/**
 * Portfolio Doctor 2.0 — frontend kill switches. A section shows only when
 * this flag is on AND the backend reports it enabled (`GET /api/doctor/features`).
 */
export const DOCTOR_POLICY_UI_ENABLED: boolean = true;
export const DOCTOR_LAB_UI_ENABLED: boolean = true;
