import { useState } from 'react';
import {
  type FielStatus,
  type RfcFormatResult,
  type RfcSatResult,
  validateRfcFormat,
  validateRfcSat,
} from '../../lib/rfc-validation-api-client';

export interface RfcValidationParams {
  rfc: string;
  razonSocial?: string;
}

export interface RfcValidationState {
  formatLoading: boolean;
  satLoading: boolean;
  formatResult: RfcFormatResult | null;
  satResult: RfcSatResult | null;
  satError: string | null;
  fielStatus: FielStatus | null;
}

export function useRfcValidation() {
  const [formatLoading, setFormatLoading] = useState(false);
  const [satLoading, setSatLoading] = useState(false);
  const [formatResult, setFormatResult] = useState<RfcFormatResult | null>(null);
  const [satResult, setSatResult] = useState<RfcSatResult | null>(null);
  const [satError, setSatError] = useState<string | null>(null);
  const [fielStatus, setFielStatus] = useState<FielStatus | null>(null);

  async function validateFormat(params: RfcValidationParams) {
    setFormatLoading(true);
    setFormatResult(null);
    setSatResult(null);
    setSatError(null);
    try {
      const res = await validateRfcFormat(params.rfc, params.razonSocial);
      setFormatResult(res);
    } finally {
      setFormatLoading(false);
    }
  }

  async function validateSat(params: RfcValidationParams) {
    setSatLoading(true);
    setSatResult(null);
    setSatError(null);
    try {
      const res = await validateRfcSat(params.rfc, params.razonSocial);
      setSatResult(res);
    } catch (err) {
      setSatError(err instanceof Error ? err.message : 'Error en portal SAT');
    } finally {
      setSatLoading(false);
    }
  }

  async function checkFielStatus() {
    const { getFielStatus } = await import('../../lib/rfc-validation-api-client');
    try {
      const status = await getFielStatus();
      setFielStatus(status);
      return status;
    } catch {
      return null;
    }
  }

  function reset() {
    setFormatResult(null);
    setSatResult(null);
    setSatError(null);
    setFielStatus(null);
  }

  return {
    formatLoading,
    satLoading,
    formatResult,
    satResult,
    satError,
    fielStatus,
    validateFormat,
    validateSat,
    checkFielStatus,
    reset,
  };
}
