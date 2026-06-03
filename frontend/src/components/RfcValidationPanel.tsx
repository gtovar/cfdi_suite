import clsx from 'clsx';
import { CheckCircle2, HelpCircle, Loader2, ShieldCheck, ShieldX, XCircle } from 'lucide-react';
import type { FielStatus, RfcFormatResult, RfcSatResult } from '../lib/rfc-validation-api-client';

interface Props {
  rfc: string;
  razonSocial?: string;
  formatLoading: boolean;
  satLoading: boolean;
  formatResult: RfcFormatResult | null;
  satResult: RfcSatResult | null;
  satError: string | null;
  fielStatus: FielStatus | null;
  onValidateFormat: () => void;
  onValidateSat: () => void;
}

function StatusIcon({ ok }: { ok: boolean }) {
  return ok
    ? <CheckCircle2 size={14} className="text-emerald-500 shrink-0" />
    : <XCircle size={14} className="text-red-500 shrink-0" />;
}

function Row({ label, ok, text }: { label: string; ok: boolean; text?: string }) {
  return (
    <div className="flex items-center gap-2 text-xs">
      <StatusIcon ok={ok} />
      <span className="text-gray-600">{label}</span>
      {text && <span className={clsx('font-medium', ok ? 'text-gray-800' : 'text-red-600')}>{text}</span>}
    </div>
  );
}

export default function RfcValidationPanel({
  rfc,
  razonSocial,
  formatLoading,
  satLoading,
  formatResult,
  satResult,
  satError,
  fielStatus,
  onValidateFormat,
  onValidateSat,
}: Props) {
  const canValidateSat = !!fielStatus?.configurada;

  return (
    <div className="rounded-xl border border-gray-200 bg-white shadow-sm p-4 space-y-3 min-w-[260px]">
      {/* RFC target */}
      <div className="space-y-0.5">
        <div className="flex items-center justify-between">
          <span className="text-xs font-semibold text-gray-500 uppercase tracking-wide">Validar RFC emisor</span>
          <span className="text-xs font-mono text-gray-800 font-semibold">{rfc}</span>
        </div>
        <p className="text-[11px] text-gray-400 leading-snug">
          Revisa que el RFC tenga formato correcto y esté registrado ante el SAT
        </p>
      </div>

      {/* Format section */}
      <div className="space-y-1.5">
        <div className="flex items-center justify-between">
          <span className="text-xs font-medium text-gray-700">Formato local</span>
          <button
            onClick={onValidateFormat}
            disabled={formatLoading}
            className="text-xs text-blue-600 hover:text-blue-700 disabled:opacity-50 flex items-center gap-1"
          >
            {formatLoading && <Loader2 size={11} className="animate-spin" />}
            {formatResult ? 'Re-validar' : 'Validar'}
          </button>
        </div>

        {formatResult && (
          <div className="space-y-1 pl-1">
            <Row label="Estructura RFC" ok={formatResult.formatoValido} text={formatResult.error ?? undefined} />
            {formatResult.formatoValido && (
              <>
                <Row label="Dígito verificador" ok={formatResult.digitoVerificador} />
                <Row
                  label="Tipo"
                  ok={true}
                  text={formatResult.tipo === 'FISICA' ? 'Persona Física' : formatResult.tipo === 'MORAL' ? 'Persona Moral' : undefined}
                />
                {formatResult.esGenerico && (
                  <div className="flex items-center gap-2 text-xs text-amber-600">
                    <HelpCircle size={13} />
                    <span>RFC genérico</span>
                  </div>
                )}
              </>
            )}
          </div>
        )}
      </div>

      <div className="border-t border-gray-100" />

      {/* SAT portal section */}
      <div className="space-y-1.5">
        <div className="flex items-center justify-between">
          <span className="text-xs font-medium text-gray-700">Portal SAT (LRFC)</span>
          {canValidateSat ? (
            <button
              onClick={onValidateSat}
              disabled={satLoading}
              className="text-xs text-blue-600 hover:text-blue-700 disabled:opacity-50 flex items-center gap-1"
            >
              {satLoading && <Loader2 size={11} className="animate-spin" />}
              {satResult ? 'Re-verificar' : 'Verificar'}
            </button>
          ) : (
            <span className="text-xs text-gray-400 italic">FIEL no configurada</span>
          )}
        </div>

        {!canValidateSat && (
          <p className="text-xs text-gray-500 pl-1">
            Para verificar si el RFC existe en el SAT y validar la Razón Social, configura tu e.Firma (archivo .cer + .key) en{' '}
            <span className="font-medium text-gray-700">Emisores → FIEL</span>.
          </p>
        )}

        {satResult && (
          <div className="space-y-1 pl-1">
            <div className="flex items-center gap-2 text-xs">
              {satResult.existeEnLrfc === null ? (
                <HelpCircle size={14} className="text-gray-400 shrink-0" />
              ) : satResult.existeEnLrfc ? (
                <ShieldCheck size={14} className="text-emerald-500 shrink-0" />
              ) : (
                <ShieldX size={14} className="text-red-500 shrink-0" />
              )}
              <span className="text-gray-600">Existe en LRFC</span>
              <span className={clsx('font-medium', satResult.existeEnLrfc ? 'text-emerald-700' : 'text-red-600')}>
                {satResult.existeEnLrfc === null ? '—' : satResult.existeEnLrfc ? 'Sí' : 'No'}
              </span>
            </div>

            {satResult.razonSocialValida !== null && (
              <Row
                label="Razón Social"
                ok={satResult.razonSocialValida}
                text={satResult.razonSocialValida ? 'Coincide' : 'No coincide'}
              />
            )}

            {satResult.error && (
              <p className="text-xs text-red-600 pl-1">{satResult.error}</p>
            )}
          </div>
        )}

        {satError && (
          <p className="text-xs text-red-600 pl-1">{satError}</p>
        )}
      </div>
    </div>
  );
}
