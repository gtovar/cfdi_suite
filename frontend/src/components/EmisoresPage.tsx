import clsx from 'clsx';
import { useEffect, useRef, useState } from 'react';
import { Building2, Eye, EyeOff, KeyRound, Loader2, Pencil, Plus, ShieldCheck, Trash2, X } from 'lucide-react';
import {
  type Emisor,
  type EmisorCreate,
  createEmisor,
  deleteEmisor,
  listEmisores,
  updateEmisor,
} from '../lib/emisores-api-client';
import {
  type FielStatus,
  configureFiel,
  deleteFiel,
  getFielStatus,
} from '../lib/rfc-validation-api-client';

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
            <label className={labelClass} htmlFor="emisor-rfc">RFC Emisor *</label>
            <input
              id="emisor-rfc"
              ref={firstRef}
              value={rfc}
              onChange={(e) => setRfc(e.target.value)}
              disabled={!!initial}
              className={inputClass}
              placeholder="XAXX010101000"
            />
          </div>

          <div>
            <label className={labelClass} htmlFor="emisor-credential-id">Credential ID *</label>
            <input
              id="emisor-credential-id"
              value={credentialId}
              onChange={(e) => setCredentialId(e.target.value)}
              className={inputClass}
              placeholder="12345"
            />
            <p className="mt-1 text-[11px] text-gray-400">El ID numérico que te asigna Diverza para este RFC.</p>
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
            <p className="mt-1 text-[11px] text-gray-400">La clave secreta de tu cuenta Diverza. Se guarda cifrada.</p>
          </div>

          <div>
            <label className={labelClass}>Número de certificado (opcional)</label>
            <input
              value={certificate}
              onChange={(e) => setCertificate(e.target.value)}
              className={inputClass}
              placeholder="00001000000712142342"
            />
            <p className="mt-1 text-[11px] text-gray-400">El número que aparece en tu certificado SAT (20 dígitos). Lo proporciona Diverza si lo requieren.</p>
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
// FIEL configuration card
// ---------------------------------------------------------------------------
function FielCard() {
  const [status, setStatus] = useState<FielStatus | null>(null);
  const [showForm, setShowForm] = useState(false);
  // react-doctor rerender-state-only-in-handlers: los <input type="file"> son
  // no-controlados (el navegador no permite bindear `value` a un File), y estos
  // valores solo se leen dentro de handleSave — useRef evita re-renders del
  // formulario en cada selección de archivo sin cambiar ningún comportamiento visible.
  const cerFileRef = useRef<File | null>(null);
  const keyFileRef = useRef<File | null>(null);
  const [password, setPassword] = useState('');
  const [showPass, setShowPass] = useState(false);
  const [saving, setSaving] = useState(false);
  const [removing, setRemoving] = useState(false);
  const [formError, setFormError] = useState('');

  useEffect(() => {
    getFielStatus().then(setStatus).catch(() => {});
  }, []);

  async function handleSave(e: { preventDefault: () => void }) {
    e.preventDefault();
    const cerFile = cerFileRef.current;
    const keyFile = keyFileRef.current;
    if (!cerFile || !keyFile || !password) {
      setFormError('Todos los campos son obligatorios');
      return;
    }
    setSaving(true);
    setFormError('');
    try {
      const updated = await configureFiel(cerFile, keyFile, password);
      setStatus(updated);
      setShowForm(false);
      setPassword('');
    } catch (err) {
      setFormError(err instanceof Error ? err.message : 'Error configurando FIEL');
    } finally {
      setSaving(false);
    }
  }

  async function handleRemove() {
    if (!confirm('¿Eliminar la configuración FIEL?')) return;
    setRemoving(true);
    try {
      const updated = await deleteFiel();
      setStatus(updated);
    } finally {
      setRemoving(false);
    }
  }

  const inputClass = clsx(
    'w-full rounded-lg border border-gray-200 px-3 py-2 text-sm text-gray-900 outline-none',
    'placeholder:text-gray-400 transition-colors duration-200',
    'focus:border-primary-400 focus:ring-1 focus:ring-primary-400/30',
  );

  return (
    <div className="mt-10">
      <div className="mb-4 flex items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <span className="size-2 rounded-full bg-violet-400 shrink-0" />
            <h2 className="text-sm font-semibold text-gray-900">e.Firma (FIEL)</h2>
          </div>
          <p className="mt-1 text-xs text-gray-500 ml-4">
            Tu firma electrónica emitida por el SAT: dos archivos (<strong className="font-medium text-gray-700">.cer</strong> + <strong className="font-medium text-gray-700">.key</strong>) y una contraseña.
            Se configura <strong className="font-medium text-gray-700">una sola vez</strong> para toda la app — no es por RFC.
            Habilita: verificar si un RFC existe en el SAT y validar que la Razón Social coincida.
          </p>
        </div>
        {status?.configurada ? (
          <button
            onClick={handleRemove}
            disabled={removing}
            className="inline-flex shrink-0 items-center gap-1.5 rounded-lg border border-red-200 px-3 py-2 text-xs font-medium text-red-600 transition-colors duration-200 hover:border-red-300 hover:bg-red-50 disabled:opacity-50"
          >
            {removing ? <Loader2 size={13} className="animate-spin" /> : <Trash2 size={13} />}
            Eliminar FIEL
          </button>
        ) : (
          <button
            onClick={() => setShowForm((v) => !v)}
            className="inline-flex shrink-0 items-center gap-1.5 rounded-lg bg-primary-600 px-4 py-2 text-xs font-medium text-white transition-colors duration-200 hover:bg-primary-700"
          >
            <KeyRound size={14} />
            Configurar FIEL
          </button>
        )}
      </div>

      <div className="rounded-lg border border-gray-200 bg-white shadow-soft">
        {status?.configurada ? (
          <div className="flex items-center gap-3 px-5 py-4">
            <div className="flex size-9 items-center justify-center rounded-full bg-emerald-100">
              <ShieldCheck size={18} className="text-emerald-600" />
            </div>
            <div>
              <p className="text-sm font-semibold text-gray-900">FIEL configurada</p>
              <p className="text-xs text-gray-500">RFC: {status.rfc ?? '—'}</p>
            </div>
          </div>
        ) : showForm ? (
          <form onSubmit={handleSave} className="space-y-4 p-5">
            <div>
              <label className="block text-xs font-medium text-gray-700 mb-1.5">
                Certificado (.cer) *
              </label>
              <input
                type="file"
                accept=".cer"
                onChange={(e) => { cerFileRef.current = e.target.files?.[0] ?? null; }}
                className={inputClass}
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-700 mb-1.5">
                Llave privada (.key) *
              </label>
              <input
                type="file"
                accept=".key"
                onChange={(e) => { keyFileRef.current = e.target.files?.[0] ?? null; }}
                className={inputClass}
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-700 mb-1.5">
                Contraseña FIEL *
              </label>
              <div className="flex gap-2">
                <input
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  type={showPass ? 'text' : 'password'}
                  className={clsx(inputClass, 'flex-1')}
                  placeholder="••••••••"
                />
                <button
                  type="button"
                  onClick={() => setShowPass((v) => !v)}
                  className="flex size-[38px] shrink-0 items-center justify-center rounded-lg border border-gray-200 text-gray-500 transition-colors duration-200 hover:border-gray-300 hover:bg-gray-100 hover:text-gray-700"
                >
                  {showPass ? <EyeOff size={15} /> : <Eye size={15} />}
                </button>
              </div>
            </div>

            {formError && (
              <p className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">
                {formError}
              </p>
            )}

            <div className="flex gap-2.5 pt-1">
              <button
                type="submit"
                disabled={saving}
                className="flex-1 rounded-lg bg-primary-600 py-2.5 text-xs font-medium text-white transition-colors duration-200 hover:bg-primary-700 disabled:opacity-50"
              >
                {saving ? 'Guardando…' : 'Guardar FIEL'}
              </button>
              <button
                type="button"
                onClick={() => setShowForm(false)}
                className="rounded-lg border border-gray-200 px-4 py-2.5 text-xs font-medium text-gray-700 transition-colors duration-200 hover:border-gray-300 hover:bg-gray-100"
              >
                Cancelar
              </button>
            </div>
          </form>
        ) : (
          <div className="flex flex-col items-center justify-center gap-3 p-10 text-center">
            <div className="flex size-10 items-center justify-center rounded-full bg-gray-100 text-gray-400">
              <KeyRound size={20} />
            </div>
            <div>
              <p className="text-sm font-medium text-gray-700">Sin e.Firma configurada</p>
              <p className="mt-1 text-xs text-gray-500 max-w-xs">
                Sube tu certificado .cer, llave .key y contraseña para habilitar la validación contra el portal SAT.
              </p>
            </div>
          </div>
        )}
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
        <div className="mb-6">
          <h2 className="text-base font-semibold text-gray-900">Configuración</h2>
          <p className="mt-1 text-sm text-gray-500">
            Aquí defines qué puede hacer la app con el SAT. Sin configurar nada ya puedes leer XMLs y exportar; lo de abajo desbloquea más.
          </p>
        </div>

        {/* Diverza section heading */}
        <div className="mb-4 flex items-start justify-between gap-4">
          <div>
            <div className="flex items-center gap-2">
              <span className="size-2 rounded-full bg-blue-400 shrink-0" />
              <h3 className="text-sm font-semibold text-gray-900">Credenciales Diverza</h3>
            </div>
            <p className="mt-1 text-xs text-gray-500 ml-4">
              Diverza es un proveedor autorizado por el SAT (PAC). Sus credenciales permiten consultar el estado de los CFDIs directamente ante el SAT.
              Necesitas una cuenta en Diverza y agregar las credenciales de cada RFC emisor que uses.
              Habilita: botón <strong className="font-medium text-gray-700">"Consultar SAT"</strong> en el Inspector y la página <strong className="font-medium text-gray-700">Consultas SAT</strong>.
            </p>
          </div>
          <button
            onClick={() => setModal('create')}
            className="inline-flex shrink-0 items-center gap-1.5 rounded-lg bg-primary-600 px-4 py-2 text-xs font-medium text-white transition-colors duration-200 hover:bg-primary-700"
          >
            <Plus size={14} />
            Agregar RFC
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
                    {['RFC Emisor', 'Credential ID', 'Certificado', ''].map((h) => (
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

        <FielCard />
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
