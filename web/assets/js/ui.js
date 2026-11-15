// =============================================================================
// ui.js — pequenos utilitários de interface (toast, escape de HTML, badges, ícones)
// =============================================================================

function escaparHTML(str) {
  if (str === null || str === undefined) return '';
  return String(str).replace(/[&<>"']/g, (m) => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[m]
  ));
}

// toast('Salvo!', 'sucesso')  — tipos: info | sucesso | erro | aviso
function toast(msg, tipo = 'info') {
  let box = document.getElementById('toast-container');
  if (!box) {
    box = document.createElement('div');
    box.id = 'toast-container';
    box.setAttribute('role', 'status');
    box.className = 'fixed bottom-4 right-4 z-[90] flex flex-col gap-2 max-w-sm w-[calc(100%-2rem)] pointer-events-none';
    document.body.appendChild(box);
  }
  const el = document.createElement('div');
  el.className = `toast toast-${tipo}`;
  el.textContent = msg;
  box.appendChild(el);
  setTimeout(() => el.remove(), 4800);
}

function formatarData(iso) {
  return iso ? new Date(iso).toLocaleString('pt-BR', { dateStyle: 'short', timeStyle: 'short' }) : '—';
}

// ------------------------------------------------------------------ badges
function badgeGravidade(g) {
  const cls = { grave: 'badge-vermelho', moderado: 'badge-ambar', leve: 'badge-verde' }[g];
  if (!g) return '<span class="badge badge-cinza">Sem gravidade</span>';
  return `<span class="badge ${cls || 'badge-cinza'} uppercase">${escaparHTML(g)}</span>`;
}

function badgeStatus(st) {
  const cls = { aberta: 'badge-azul', resolvida: 'badge-verde', descartada: 'badge-cinza', duplicada: 'badge-roxo' }[st];
  return `<span class="badge ${cls || 'badge-cinza'} uppercase">${escaparHTML(st)}</span>`;
}

function badgePapel(p) {
  const cls = { admin: 'badge-roxo', gestor: 'badge-verde', cidadao: 'badge-cinza' }[p];
  const nome = { admin: 'Admin', gestor: 'Gestor', cidadao: 'Cidadão' }[p] || p;
  return `<span class="badge ${cls || 'badge-cinza'}">${escaparHTML(nome)}</span>`;
}

// ------------------------------------------------------------------- ícones
// Traços simples (estilo "lucide"). Uso: icone('mapa', 'w-5 h-5')
const _ICONES = {
  logo: '<path d="M4 20 9 4"/><path d="m20 20-5-16"/><path d="M12 6v3M12 12v3M12 18v2"/>',
  mapa: '<path d="M20 10c0 6-8 12-8 12S4 16 4 10a8 8 0 0 1 16 0Z"/><circle cx="12" cy="10" r="3"/>',
  camera: '<path d="M14.5 4h-5L7 7H4a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2V9a2 2 0 0 0-2-2h-3l-2.5-3z"/><circle cx="12" cy="13" r="3"/>',
  cpu: '<rect x="5" y="5" width="14" height="14" rx="2"/><rect x="9" y="9" width="6" height="6"/><path d="M9 2v3M15 2v3M9 19v3M15 19v3M2 9h3M2 15h3M19 9h3M19 15h3"/>',
  check: '<path d="M20 6 9 17l-5-5"/>',
  escudo: '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10Z"/><path d="m9 12 2 2 4-4"/>',
  usuario: '<circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/>',
  usuarios: '<circle cx="9" cy="8" r="3.5"/><path d="M2 21a7 7 0 0 1 14 0"/><path d="M16 4.5a3.5 3.5 0 0 1 0 7M22 21a7 7 0 0 0-4.5-6.5"/>',
  predio: '<path d="M3 21h18M5 21V7l8-4v18M19 21V11l-6-4"/><path d="M9 9v.01M9 13v.01M9 17v.01"/>',
  lista: '<path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01"/>',
  grade: '<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/>',
  mais: '<path d="M12 5v14M5 12h14"/>',
  busca: '<circle cx="11" cy="11" r="7"/><path d="m21 21-4.3-4.3"/>',
  x: '<path d="M18 6 6 18M6 6l12 12"/>',
  menu: '<path d="M4 6h16M4 12h16M4 18h16"/>',
  seta: '<path d="M5 12h14M13 6l6 6-6 6"/>',
  sair: '<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4M16 17l5-5-5-5M21 12H9"/>',
  editar: '<path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z"/>',
  alerta: '<path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z"/><path d="M12 9v4M12 17h.01"/>',
  relogio: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
};
function icone(nome, classe = 'w-5 h-5') {
  return `<svg class="${classe}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${_ICONES[nome] || ''}</svg>`;
}

// Aviso deixado por outra página (ex.: "Você não tem acesso a essa área.")
window.addEventListener('DOMContentLoaded', () => {
  const aviso = sessionStorage.getItem('PAVIMENTAI_AVISO');
  if (aviso) { sessionStorage.removeItem('PAVIMENTAI_AVISO'); toast(aviso, 'aviso'); }
});
