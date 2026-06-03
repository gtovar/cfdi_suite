export const taxCodeCatalog = {
  '001': { label: 'ISR' },
  '002': { label: 'IVA' },
  '003': { label: 'IEPS' },
} as const;

export const tipoFactorCatalog = {
  Tasa: {
    label: 'Tasa',
    description: 'Porcentaje aplicado sobre la base',
  },
  Cuota: {
    label: 'Cuota',
    description: 'Cuota fija',
  },
  Exento: {
    label: 'Exento',
    description: 'Sin impuesto trasladado',
  },
} as const;

export const objetoImpCatalog = {
  '01': { label: 'No objeto de impuesto' },
  '02': { label: 'Sí objeto de impuesto' },
  '03': { label: 'Sí objeto de impuesto y no obligado al desglose' },
} as const;
