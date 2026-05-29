import clsx from 'clsx';
import { useEffect, useRef, useState } from 'react';
import { Building2, Eye, EyeOff, Pencil, Plus, Trash2, X } from 'lucide-react';
import {
  type Emisor,
  type EmisorCreate,
  createEmisor,
  deleteEmisor,
  listEmisores,
  updateEmisor,
} from '../lib/emisores-api-client';

// ---------------------------------------------------------------------------
// Modal form
// ---------------------------------------------------------------------------
interface ModalProps {
  initial?: Emisor;
  onSave: (data: EmisorCreate) => Promise<void>;
  onClose: () => void;
}

function EmisorModal({ initial, onSave, onClose }: ModalProps) {
  const [rfc, setRfc] = useState(initial?.rfc ?? '');
  const [credentialId, setCredentialId] = useState(initial?.credential_id ?? '');
  const [token, setToken] = useState('');
  const [certificate, setCertificate] = useState(initial?.certificate_number ?? '');
  const [showToken, setShowToken] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const firstRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    firstRef.current?.focus();
  }, []);

  async function handleSubmit(e: { preventDefault: () => void }) {
    e.preventDefault();
    if (!rfc.trim() || !credentialId.trim()) {
      setError('RFC y Credential ID son obligatorios');
      return;
    }
    if (!initial && !token.trim()) {
      setError('Credential Token es obligatorio al crear un emisor');
      return;
    }
    setSaving(true);
    setError('');
    try {
      await onSave({
        rfc: rfc.trim().toUpperCase(),
        pac: 'diverza',
        credential_id: credentialId.trim(),
        credential_token: token.trim(),
        certificate_number: certificate.trim(),
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido');
      setSaving(false);
    }
  }

  const inputClass = clsx(
    'w-full rounded-lg border border-gray-200 px-3 py-2 text-sm text-gray-900 outline-none',
    'placeholder:text-gray-400 transition-colors duration-200',
    'focus:border-primary-400 focus:ring-1 focus:ring-primary-400/30',
    'disabled:cursor-not-allowed disabled:bg-gray-50 disabled:text-gray-400',
  );

  const labelClass = 'block text-xs font-medium text-gray-700 mb-1.5';

  return (
    <div className="fixed inset-0 z-30 flex items-center justify-center bg-black/40 p-6">
      <div className="w-full max-w-md rounded-xl border border-gray-200 bg-white shadow-soft-2">
        {/* Modal header */}
        <div className="flex items-center justify-between border-b border-gray-200 px-5 py-4">
          <h3 className="text-sm font-semibold text-gray-900">
            {initial ? 'Editar emisor' : 'Agregar emisor'}
          </h3>
          <button
            onClick={onClose}
            className="flex size-7 items-center justify-center rounded-lg text-gray-400 transition-colors duration-200 hover:bg-gray-100 hover:text-gray-700"
          >
            <X size={16} />
          </button>
        </div>

        {/* Modal body */}
        <form onSubmit={handleSubmit} className="space-y-4 p-5">
          <div>
            <label className={labelClass}>RFC Emisor *</label>
            <input
              ref={firstRef}
              value={rfc}
              onChange={(e) => setRfc(e.target.value)}
              disabled={!!initial}
              className={inputClass}
              placeholder="XAXX010101000"
            />
          </div>

          <div>
            <label className={labelClass}>PAC</label>
            <div className="rounded-lg border border-gray-200 bg-gray-50 px-3 py-2 text-sm text-gray-500">
              Diverza
            </div>
          </div>

          <div>
            <label className={labelClass}>Credential ID *</label>
            <input
              value={credentialId}
              onChange={(e) => setCredentialId(e.target.value)}
              className={inputClass}
              placeholder="12345"
            />
          </div>

          <div>
            <label className={labelClass}>
              Credential Token {initial ? '(dejar vacío para no cambiar)' : '*'}
            </label>
            <div className="flex gap-2">
              <input
                value={token}
                onChange={(e) => setToken(e.target.value)}
                type={showToken ? 'text' : 'password'}
                className={clsx(inputClass, 'flex-1')}
                placeholder="••••••••"
              />
              <button
                type="button"
                onClick={() => setShowToken((v) => !v)}
                className="flex size-[38px] shrink-0 items-center justify-center rounded-lg border border-gray-200 text-gray-500 transition-colors duration-200 hover:border-gray-300 hover:bg-gray-100 hover:text-gray-700"
              >
                {showToken ? <EyeOff size={15} /> : <Eye size={15} />}
              </button>
            </div>
          </div>

          <div>
            <label className={labelClass}>Número de certificado (opcional)</label>
            <input
              value={certificate}
              onChange={(e) => setCertificate(e.target.value)}
              className={inputClass}
              placeholder="00001000000712142342"
            />
          </div>

          {error && (
            <p className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">
              {error}
            </p>
          )}

          <div className="flex gap-2.5 pt-1">
            <button
              type="submit"
              disabled={saving}
              className="flex-1 rounded-lg bg-primary-600 py-2.5 text-xs font-medium text-white transition-colors duration-200 hover:bg-primary-700 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {saving ? 'Guardando…' : 'Guardar'}
            </button>
            <button
              type="button"
              onClick={onClose}
              className="rounded-lg border border-gray-200 px-4 py-2.5 text-xs font-medium text-gray-700 transition-colors duration-200 hover:border-gray-300 hover:bg-gray-100"
            >
              Cancelar
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------
export default function EmisoresPage() {
  const [emisores, setEmisores] = useState<Emisor[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [modal, setModal] = useState<'create' | Emisor | null>(null);
  const [deleting, setDeleting] = useState<string | null>(null);

  async function reload() {
    try {
      setEmisores(await listEmisores());
      setError('');
    } catch {
      setError('No se pudo conectar con la API. ¿Está corriendo el backend?');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    reload();
  }, []);

  async function handleSave(data: EmisorCreate) {
    if (modal === 'create') {
      await createEmisor(data);
    } else if (modal && typeof modal === 'object') {
      const tokenPayload = data.credential_token ? data : { ...data, credential_token: '__keep__' };
      await updateEmisor(modal.rfc, tokenPayload);
    }
    setModal(null);
    await reload();
  }

  async function handleDelete(rfc: string) {
    if (!confirm(`¿Eliminar el emisor ${rfc}?`)) return;
    setDeleting(rfc);
    try {
      await deleteEmisor(rfc);
      await reload();
    } catch {
      setError(`No se pudo eliminar ${rfc}`);
    } finally {
      setDeleting(null);
    }
  }

  return (
    <div className="flex flex-1 flex-col min-h-0 overflow-auto bg-gray-50">
      <div className="mx-auto w-full max-w-4xl px-6 py-8">
        {/* Page heading */}
        <div className="mb-8 flex items-start justify-between gap-4">
          <div>
            <h2 className="text-base font-semibold text-gray-900">Emisores</h2>
            <p className="mt-1 text-xs text-gray-500">Credenciales por RFC — Diverza PAC</p>
          </div>
          <button
            onClick={() => setModal('create')}
            className="inline-flex shrink-0 items-center gap-1.5 rounded-lg bg-primary-600 px-4 py-2 text-xs font-medium text-white transition-colors duration-200 hover:bg-primary-700"
          >
            <Plus size={14} />
            Agregar emisor
          </button>
        </div>

        {/* Content card */}
        <div className="rounded-lg border border-gray-200 bg-white shadow-soft">
          {loading && (
            <div className="p-8 text-center text-xs text-gray-400">Cargando…</div>
          )}

          {!loading && error && (
            <div className="p-6">
              <p className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-xs text-red-700">
                {error}
              </p>
            </div>
          )}

          {!loading && !error && emisores.length === 0 && (
            <div className="flex flex-col items-center justify-center gap-3 p-16 text-center">
              <div className="flex size-12 items-center justify-center rounded-full bg-gray-100 text-gray-400">
                <Building2 size={22} />
              </div>
              <div>
                <p className="text-sm font-medium text-gray-700">Sin emisores configurados</p>
                <p className="mt-1 text-xs text-gray-500 max-w-sm">
                  Agrega las credenciales Diverza de cada RFC emisor que uses para operar.
                </p>
              </div>
            </div>
          )}

          {!loading && !error && emisores.length > 0 && (
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-gray-200 bg-gray-50 text-left">
                    {['RFC Emisor', 'PAC', 'Credential ID', 'Certificado', ''].map((h) => (
                      <th key={h} className="px-5 py-3 text-tiny font-medium uppercase tracking-wider text-gray-500">
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {emisores.map((em) => (
                    <tr key={em.rfc} className="transition-colors duration-150 hover:bg-gray-50">
                      <td className="px-5 py-3 text-xs-plus font-semibold text-gray-900">{em.rfc}</td>
                      <td className="px-5 py-3 text-xs text-gray-500 capitalize">{em.pac}</td>
                      <td className="px-5 py-3 text-xs text-gray-600">{em.credential_id}</td>
                      <td className="px-5 py-3 text-xs text-gray-500">{em.certificate_number || '—'}</td>
                      <td className="px-5 py-3">
                        <div className="flex items-center justify-end gap-1.5">
                          <button
                            onClick={() => setModal(em)}
                            className="flex size-7 items-center justify-center rounded-lg border border-gray-200 text-gray-500 transition-colors duration-200 hover:border-gray-300 hover:bg-gray-100 hover:text-gray-700"
                          >
                            <Pencil size={13} />
                          </button>
                          <button
                            onClick={() => handleDelete(em.rfc)}
                            disabled={deleting === em.rfc}
                            className={clsx(
                              'flex size-7 items-center justify-center rounded-lg border text-red-500 transition-colors duration-200',
                              'border-red-200 hover:border-red-300 hover:bg-red-50 hover:text-red-600',
                              'disabled:cursor-not-allowed disabled:opacity-40',
                            )}
                          >
                            <Trash2 size={13} />
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>

      {modal !== null && (
        <EmisorModal
          initial={modal === 'create' ? undefined : modal}
          onSave={handleSave}
          onClose={() => setModal(null)}
        />
      )}
    </div>
  );
}
