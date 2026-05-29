import { useState } from 'react';
import { enquirySingle, type EnquiryResult } from '../../lib/sat-enquiry-api-client';

interface SatEnquiryParams {
  uuid: string;
  rfcEmisor: string;
  rfcReceptor: string;
  total: number;
}

export function useSatEnquiry() {
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<EnquiryResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function consult(params: SatEnquiryParams) {
    setLoading(true);
    setResult(null);
    setError(null);
    try {
      const res = await enquirySingle({
        uuid: params.uuid,
        rfc_emisor: params.rfcEmisor,
        rfc_receptor: params.rfcReceptor,
        total_cfdi: String(params.total),
        motive: '01',
      });
      setResult(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error consultando SAT');
    } finally {
      setLoading(false);
    }
  }

  function reset() {
    setResult(null);
    setError(null);
    setLoading(false);
  }

  return { loading, result, error, consult, reset };
}
