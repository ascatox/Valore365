import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useCallback } from 'react';
import { DOCTOR_LAB_UI_ENABLED, DOCTOR_POLICY_UI_ENABLED } from '../../../features';
import { ApiRequestError } from '../../../services/api/client';
import {
  doctorScopeFingerprint,
  getDoctorEvaluation,
  getDoctorFeatures,
  getDoctorMetrics,
  getDoctorPolicy,
  getDoctorPolicyVersions,
  getDoctorTemplates,
} from '../../../services/api/doctor';

// React Query keys: policy and evaluation are per exact scope (fingerprint);
// the evaluation key also carries the policy version so a save never shows
// a result computed on the previous version.
export const doctorQueryKeys = {
  features: ['doctor-features'] as const,
  metrics: ['doctor-metrics'] as const,
  templates: ['doctor-templates'] as const,
  policy: (fingerprint: string) => ['doctor-policy', fingerprint] as const,
  evaluation: (fingerprint: string, policyVersion: number | null) => ['doctor-evaluation', fingerprint, policyVersion] as const,
  versions: (policyId: number | null, policyVersion: number | null) => ['doctor-policy-versions', policyId, policyVersion] as const,
};

// Client errors (404 feature_disabled, 422, 409) are answers, not glitches.
function retryServerErrors(failureCount: number, error: unknown): boolean {
  if (error instanceof ApiRequestError && error.status >= 400 && error.status < 500) return false;
  return failureCount < 2;
}

export function useDoctorFeatures() {
  const query = useQuery({
    queryKey: doctorQueryKeys.features,
    queryFn: getDoctorFeatures,
    staleTime: 5 * 60 * 1000,
    retry: retryServerErrors,
  });
  return {
    isLoading: query.isLoading,
    policyEnabled: DOCTOR_POLICY_UI_ENABLED && query.data?.policy_enabled === true,
    simulatorEnabled: DOCTOR_LAB_UI_ENABLED && query.data?.simulator_enabled === true,
  };
}

export function useDoctorMetrics(enabled = true) {
  return useQuery({
    queryKey: doctorQueryKeys.metrics,
    queryFn: getDoctorMetrics,
    staleTime: 30 * 60 * 1000,
    enabled,
    retry: retryServerErrors,
  });
}

export function useDoctorTemplates(enabled = true) {
  return useQuery({
    queryKey: doctorQueryKeys.templates,
    queryFn: getDoctorTemplates,
    staleTime: 30 * 60 * 1000,
    enabled,
    retry: retryServerErrors,
  });
}

/** Policy + evaluation of the exact scope. */
export function useDoctorPolicyState(portfolioIds: number[], enabled: boolean) {
  const fingerprint = doctorScopeFingerprint(portfolioIds);
  const active = enabled && portfolioIds.length > 0;
  const policyQuery = useQuery({
    queryKey: doctorQueryKeys.policy(fingerprint),
    queryFn: () => getDoctorPolicy(portfolioIds),
    enabled: active,
    retry: retryServerErrors,
  });
  const policy = policyQuery.data ?? null;
  const policyVersion = policy?.current_version ?? null;
  const evaluationQuery = useQuery({
    queryKey: doctorQueryKeys.evaluation(fingerprint, policyVersion),
    queryFn: () => getDoctorEvaluation(portfolioIds),
    enabled: active && !policyQuery.isLoading,
    retry: retryServerErrors,
  });
  return { fingerprint, policyQuery, policy, policyVersion, evaluationQuery };
}

export function useDoctorPolicyVersions(policyId: number | null, policyVersion: number | null, enabled = true) {
  return useQuery({
    queryKey: doctorQueryKeys.versions(policyId, policyVersion),
    queryFn: () => getDoctorPolicyVersions(policyId!),
    enabled: enabled && policyId != null,
    retry: retryServerErrors,
  });
}

/** Refetch everything that depends on the scope's policy (after save / restore / conflict). */
export function useInvalidateDoctorPolicy() {
  const queryClient = useQueryClient();
  return useCallback((fingerprint: string) => Promise.all([
    queryClient.invalidateQueries({ queryKey: ['doctor-policy', fingerprint] }),
    queryClient.invalidateQueries({ queryKey: ['doctor-evaluation', fingerprint] }),
    queryClient.invalidateQueries({ queryKey: ['doctor-policy-versions'] }),
  ]), [queryClient]);
}
