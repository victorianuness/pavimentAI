// =============================================================================
// admin.js — painel de administração (só papel "admin").
// Seções: visão geral · municípios · usuários · tipos. Navegação por #hash.
// Rotas usadas: /admin/areas, /admin/municipios/*, /admin/usuarios, /admin/tipos
// =============================================================================

const SECOES = {
  visao: { texto: 'Visão geral', icone: 'grade', carregar: carregarVisao },
  municipios: { texto: 'Municípios', icone: 'predio', carregar: carregarAreas },
  usuarios: { texto: 'Usuários', icone: 'usuarios', carregar: carregarUsuarios },
  tipos: { texto: 'Tipos de ocorrência', icone: 'lista', carregar: carregarTipos },
};
const TIPOS_BASE = ['buraco', 'acessibilidade'];
const POR_PAGINA = 20;

let eu = null;
let areas = [];          // /admin/areas (inclui desativadas)
let tipos = [];
let usuariosPag = { deslocamento: 0, total: 0 };
let usuarioEmEdicao = null;
let tipoEmEdicao = null;
let ibgeSelecionado = null;
let mapaPrevia = null;
let camadaPrevia = null;

const $ = (id) => document.getElementById(id);
const listaDeCategorias = (txt) => txt.split(',').map((c) => c.trim()).filter(Boolean);

// ------------------------------------------------------------------ navegação
function irPara(sec) {
  if (!SECOES[sec]) sec = 'visao';
  Object.keys(SECOES).forEach((s) => {
    $(`sec-${s}`).hidden = s !== sec;
    document.querySelector(`[data-sec="${s}"]`).classList.toggle('ativo', s === sec);
  });
  if (location.hash !== `#${sec}`) history.replaceState(null, '', `#${sec}`);
  SECOES[sec].carregar();
  if (sec === 'municipios' && mapaPrevia) setTimeout(() => mapaPrevia.invalidateSize(), 50);
}

function montarMenu() {
  document.querySelectorAll('#menu-admin [data-sec]').forEach((b) => {
    const s = SECOES[b.dataset.sec];
    b.innerHTML = `${icone(s.icone, 'w-5 h-5 shrink-0')}<span class="whitespace-nowrap">${s.texto}</span>`;
    b.addEventListener('click', () => irPara(b.dataset.sec));
  });
  document.querySelectorAll('[data-ir]').forEach((b) => b.addEventListener('click', () => irPara(b.dataset.ir)));
}

function erro(err) { toast(err.message || String(err), 'erro'); }

function alternar(botao, valor) {
  const novo = valor ?? botao.getAttribute('aria-checked') !== 'true';
  botao.setAttribute('aria-checked', String(novo));
  return novo;
}

// ------------------------------------------------------------------ visão geral
async function carregarAreas() {
  try {
    areas = await api('/admin/areas');
    renderAreas();
    preencherSelectAreas();
  } catch (e) { erro(e); }
}

async function carregarVisao() {
  try {
    areas = await api('/admin/areas');
    preencherSelectAreas();
    const soma = (k) => areas.reduce((t, a) => t + Number(a[k] || 0), 0);
    const cards = [
      ['Municípios ativos', `${areas.filter((a) => a.ativa).length}`, `de ${areas.length} cadastrados`],
      ['Ocorrências abertas', soma('ocorrencias_abertas'), `${soma('ocorrencias_total')} no total`],
      ['Gestores', soma('gestores'), 'vinculados a municípios'],
      ['Moradores', soma('moradores'), 'com residência informada'],
    ];
    $('cards-resumo').innerHTML = cards.map(([t, v, s]) => `
      <div class="card p-4">
        <p class="text-xs font-semibold text-ink-soft">${t}</p>
        <p class="text-3xl font-extrabold mt-1">${v}</p>
        <p class="text-xs text-ink-faint mt-0.5">${s}</p>
      </div>`).join('');

    const max = Math.max(1, ...areas.map((a) => Number(a.ocorrencias_abertas)));
    const ordenadas = [...areas].sort((a, b) => b.ocorrencias_abertas - a.ocorrencias_abertas);
    $('barras-municipios').innerHTML = ordenadas.length ? ordenadas.map((a) => `
      <div>
        <div class="flex justify-between text-sm mb-1">
          <span class="font-semibold">${escaparHTML(a.nome)} ${a.ativa ? '' : '<span class="badge badge-cinza ml-1">desativada</span>'}</span>
          <span class="text-ink-soft">${a.ocorrencias_abertas}</span>
        </div>
        <div class="h-2 rounded-full bg-brand-50 overflow-hidden">
          <div class="h-full rounded-full bg-brand-600" style="width:${(a.ocorrencias_abertas / max) * 100}%"></div>
        </div>
      </div>`).join('')
      : '<p class="text-sm text-ink-soft">Nenhum município cadastrado ainda. Comece por <b>Municípios</b>.</p>';
  } catch (e) { erro(e); }
}

// ------------------------------------------------------------------ municípios
function renderAreas() {
  $('areas-contagem').textContent = `(${areas.length})`;
  $('lista-areas').innerHTML = areas.length ? areas.map((a) => `
    <div class="p-4 flex flex-wrap items-center justify-between gap-4" data-area="${a.id_area}">
      <div class="min-w-0">
        <p class="font-bold">${escaparHTML(a.nome)}
          <span class="text-xs font-medium text-ink-faint ml-1">IBGE ${escaparHTML(a.codigo_ibge)}</span></p>
        <p class="text-xs text-ink-soft mt-0.5">
          ${a.ocorrencias_abertas} abertas · ${a.ocorrencias_total} no total · ${a.gestores} gestor(es) · ${a.moradores} morador(es)</p>
      </div>
      <div class="flex items-center gap-5 text-sm">
        <label class="flex items-center gap-2 cursor-pointer"><span class="text-ink-soft">Só moradores</span>
          <button class="switch" role="switch" aria-checked="${a.exige_residencia}" data-campo="exige_residencia" aria-label="Só moradores"></button></label>
        <label class="flex items-center gap-2 cursor-pointer"><span class="text-ink-soft">Ativo</span>
          <button class="switch" role="switch" aria-checked="${a.ativa}" data-campo="ativa" aria-label="Ativo"></button></label>
      </div>
    </div>`).join('')
    : '<p class="p-6 text-sm text-ink-soft">Nenhum município cadastrado.</p>';
}

async function alterarArea(botao) {
  const idArea = botao.closest('[data-area]').dataset.area;
  const campo = botao.dataset.campo;
  const novo = botao.getAttribute('aria-checked') !== 'true';
  botao.disabled = true;
  try {
    await api(`/admin/areas/${idArea}`, { method: 'PATCH', json: { [campo]: novo } });
    toast('Município atualizado.', 'sucesso');
  } catch (e) { erro(e); }
  carregarAreas();
}

async function buscarIBGE(ev) {
  ev.preventDefault();
  const uf = $('ibge-uf').value.trim();
  const nome = $('ibge-nome').value.trim();
  const box = $('ibge-resultados');
  box.innerHTML = '<p class="text-sm text-ink-soft">Buscando…</p>';
  try {
    const res = await api(`/admin/municipios/buscar?uf=${encodeURIComponent(uf)}&nome=${encodeURIComponent(nome)}`);
    box.innerHTML = res.length ? res.map((m) => `
      <div class="flex items-center justify-between gap-3 p-3 rounded-xl border border-line bg-surface">
        <p class="text-sm"><b>${escaparHTML(m.nome)}</b> <span class="text-ink-faint">· IBGE ${escaparHTML(m.codigo_ibge)}</span>
          ${m.ja_cadastrada ? '<span class="badge badge-verde ml-1">já cadastrado</span>' : ''}</p>
        <button class="btn btn-outline btn-sm" data-previa="${escaparHTML(m.codigo_ibge)}">Ver contorno</button>
      </div>`).join('')
      : '<p class="text-sm text-ink-soft">Nenhum município encontrado no IBGE para essa busca.</p>';
  } catch (e) { box.innerHTML = ''; erro(e); }
}

async function verPrevia(codigo) {
  try {
    const prev = await api(`/admin/municipios/${codigo}/previa`);
    ibgeSelecionado = prev;
    $('ibge-previa').classList.remove('hidden');
    $('ibge-previa-titulo').textContent = `${prev.nome} · ${prev.pontos} vértices`;
    $('ibge-confirmar').disabled = prev.ja_cadastrada;
    $('ibge-confirmar').textContent = prev.ja_cadastrada ? 'Já cadastrado' : 'Importar limite e cadastrar';

    if (!mapaPrevia) {
      mapaPrevia = L.map('mapa-previa');
      L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', { attribution: '&copy; OpenStreetMap' }).addTo(mapaPrevia);
      camadaPrevia = L.layerGroup().addTo(mapaPrevia);
    }
    mapaPrevia.invalidateSize();
    camadaPrevia.clearLayers();
    const camada = L.geoJSON(prev.contorno, { style: { color: '#1f8556', weight: 2.5, fillColor: '#34a06b', fillOpacity: 0.15 } }).addTo(camadaPrevia);
    mapaPrevia.fitBounds(camada.getBounds());
    $('ibge-previa').scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  } catch (e) { erro(e); }
}

async function confirmarCadastro() {
  if (!ibgeSelecionado) return;
  const btn = $('ibge-confirmar');
  btn.disabled = true;
  btn.textContent = 'Importando…';
  try {
    const r = await api('/admin/areas', {
      method: 'POST',
      json: { codigo_ibge: ibgeSelecionado.codigo_ibge, exige_residencia: $('ibge-exige').getAttribute('aria-checked') === 'true' },
    });
    toast(`${r.nome} cadastrado (${r.ocorrencias_ligadas} ocorrências e ${r.moradores_ligados} moradores vinculados).`, 'sucesso');
    fecharPrevia();
    $('ibge-resultados').innerHTML = '';
    carregarAreas();
  } catch (e) {
    erro(e);
    btn.disabled = false;
    btn.textContent = 'Importar limite e cadastrar';
  }
}

function fecharPrevia() {
  ibgeSelecionado = null;
  $('ibge-previa').classList.add('hidden');
  alternar($('ibge-exige'), false);
}

// ------------------------------------------------------------------ usuários
function preencherSelectAreas() {
  const ativas = areas.filter((a) => a.ativa);
  const opcoes = ativas.map((a) => `<option value="${a.id_area}">${escaparHTML(a.nome)}</option>`).join('');
  const valorAtual = $('u-area').value;
  $('u-area').innerHTML = '<option value="">Todos</option>' + opcoes;
  $('u-area').value = valorAtual;
  $('papel-area').innerHTML = opcoes;
}

async function carregarUsuarios() {
  if (!areas.length) { try { areas = await api('/admin/areas'); preencherSelectAreas(); } catch (e) { erro(e); } }
  const q = new URLSearchParams({ limite: POR_PAGINA, deslocamento: usuariosPag.deslocamento });
  const busca = $('u-busca').value.trim();
  if (busca.length >= 2) q.set('busca', busca);
  if ($('u-papel').value) q.set('papel', $('u-papel').value);
  if ($('u-area').value) q.set('id_area_gestao', $('u-area').value);
  try {
    const res = await api(`/admin/usuarios?${q}`);
    usuariosPag.total = res.total;
    $('lista-usuarios').innerHTML = res.itens.length ? res.itens.map((u) => `
      <div class="p-4 flex flex-wrap items-center justify-between gap-3">
        <div class="flex items-center gap-3 min-w-0">
          <span class="w-9 h-9 rounded-full bg-brand-100 text-brand-800 grid place-items-center font-bold shrink-0">${escaparHTML(u.nome.trim()[0]?.toUpperCase() || '?')}</span>
          <div class="min-w-0">
            <p class="font-semibold truncate">${escaparHTML(u.nome)}</p>
            <p class="text-xs text-ink-soft truncate">${escaparHTML(u.email)}${u.cidade_gestao ? ` · gestor de ${escaparHTML(u.cidade_gestao)}` : ''}${u.cidade_residencia ? ` · mora em ${escaparHTML(u.cidade_residencia)}` : ''}</p>
          </div>
        </div>
        <div class="flex items-center gap-2">
          ${u.status_conta !== 'ativa' ? `<span class="badge badge-ambar">${escaparHTML(u.status_conta)}</span>` : ''}
          ${badgePapel(u.papel)}
          <button class="btn btn-outline btn-sm" data-papel="${u.id_usuario}"
            ${u.id_usuario === eu.id_usuario ? 'disabled title="Você não pode mudar o próprio papel"' : ''}>Alterar papel</button>
        </div>
      </div>`).join('')
      : '<p class="p-6 text-sm text-ink-soft">Nenhum usuário encontrado.</p>';
    window._usuariosPagina = Object.fromEntries(res.itens.map((u) => [u.id_usuario, u]));

    const de = res.total ? usuariosPag.deslocamento + 1 : 0;
    const ate = usuariosPag.deslocamento + res.itens.length;
    $('u-resumo').textContent = `${de}–${ate} de ${res.total}`;
    $('u-ant').disabled = usuariosPag.deslocamento === 0;
    $('u-prox').disabled = ate >= res.total;
  } catch (e) { erro(e); }
}

function abrirDialogoPapel(id) {
  usuarioEmEdicao = window._usuariosPagina[id];
  $('papel-quem').textContent = `${usuarioEmEdicao.nome} · ${usuarioEmEdicao.email}`;
  $('papel-novo').value = usuarioEmEdicao.papel;
  if (usuarioEmEdicao.id_area_gestao) $('papel-area').value = usuarioEmEdicao.id_area_gestao;
  atualizarCampoArea();
  $('dlg-papel').showModal();
}

function atualizarCampoArea() {
  $('papel-area-box').classList.toggle('hidden', $('papel-novo').value !== 'gestor');
}

async function salvarPapel(ev) {
  ev.preventDefault();
  const papel = $('papel-novo').value;
  if (papel === 'gestor' && !$('papel-area').value) return toast('Escolha o município do gestor.', 'aviso');
  try {
    await api(`/admin/usuarios/${usuarioEmEdicao.id_usuario}/papel`, {
      method: 'POST',
      json: { papel, id_area_gestao: papel === 'gestor' ? Number($('papel-area').value) : null },
    });
    $('dlg-papel').close();
    toast('Papel atualizado.', 'sucesso');
    carregarUsuarios();
  } catch (e) { erro(e); }
}

// ------------------------------------------------------------------ tipos
async function carregarTipos() {
  try {
    tipos = await api('/admin/tipos');
    $('lista-tipos').innerHTML = tipos.map((t) => {
      const base = TIPOS_BASE.includes(t.codigo);
      const cats = (t.categorias || []).map((c) => `<span class="badge badge-cinza font-mono">${escaparHTML(c)}</span>`).join(' ');
      return `
      <article class="card p-4 flex flex-col gap-3" data-tipo="${escaparHTML(t.codigo)}">
        <div class="flex items-start justify-between gap-3">
          <div class="min-w-0">
            <h3 class="font-bold">${escaparHTML(t.nome)}</h3>
            <p class="text-xs text-ink-faint font-mono">${escaparHTML(t.codigo)} · ordem ${t.ordem}</p>
          </div>
          <button class="switch" role="switch" aria-checked="${t.ativo}" data-ativo
            ${base ? 'disabled title="Tipos base não podem ser desativados"' : ''} aria-label="Ativo"></button>
        </div>
        <div class="flex flex-wrap gap-1.5">
          ${t.usa_ia ? '<span class="badge badge-verde">IA YOLO</span>' : ''}
          ${t.usa_gravidade ? '<span class="badge badge-ambar">gravidade</span>' : ''}
          ${base ? '<span class="badge badge-azul">base</span>' : ''}
        </div>
        ${cats ? `<div class="flex flex-wrap gap-1.5">${cats}</div>` : ''}
        <div class="flex items-center justify-between pt-1 border-t border-line">
          <span class="text-xs text-ink-soft">${t.ocorrencias} ocorrência(s)</span>
          <button class="btn btn-ghost btn-sm" data-editar>${icone('editar', 'w-4 h-4')} Editar</button>
        </div>
      </article>`;
    }).join('');
  } catch (e) { erro(e); }
}

async function criarTipo(ev) {
  ev.preventDefault();
  try {
    await api('/admin/tipos', {
      method: 'POST',
      json: {
        codigo: $('t-codigo').value.trim(),
        nome: $('t-nome').value.trim(),
        usa_gravidade: $('t-grav').getAttribute('aria-checked') === 'true',
        categorias: listaDeCategorias($('t-cats').value),
      },
    });
    toast('Tipo criado.', 'sucesso');
    ev.target.reset();
    alternar($('t-grav'), false);
    carregarTipos();
  } catch (e) { erro(e); }
}

async function alterarTipo(codigo, dados, botao) {
  if (botao) botao.disabled = true;
  try {
    await api(`/admin/tipos/${codigo}`, { method: 'PATCH', json: dados });
    return true;
  } catch (e) { erro(e); return false; }
  finally { carregarTipos(); }
}

function abrirEdicaoTipo(codigo) {
  tipoEmEdicao = tipos.find((t) => t.codigo === codigo);
  $('et-codigo').textContent = tipoEmEdicao.codigo;
  $('et-nome').value = tipoEmEdicao.nome;
  $('et-ordem').value = tipoEmEdicao.ordem;
  $('et-cats').value = (tipoEmEdicao.categorias || []).join(', ');
  $('dlg-tipo').showModal();
}

async function salvarEdicaoTipo(ev) {
  ev.preventDefault();
  const ok = await alterarTipo(tipoEmEdicao.codigo, {
    nome: $('et-nome').value.trim(),
    ordem: Number($('et-ordem').value),
    categorias: listaDeCategorias($('et-cats').value),
  });
  if (ok) { $('dlg-tipo').close(); toast('Tipo atualizado.', 'sucesso'); }
}

// ------------------------------------------------------------------ início
window.addEventListener('DOMContentLoaded', async () => {
  eu = await exigirPapel(['admin']);
  montarMenu();

  // municípios
  $('form-busca-ibge').addEventListener('submit', buscarIBGE);
  $('ibge-resultados').addEventListener('click', (e) => {
    const b = e.target.closest('[data-previa]');
    if (b) verPrevia(b.dataset.previa);
  });
  $('ibge-exige').addEventListener('click', (e) => alternar(e.currentTarget));
  $('ibge-confirmar').addEventListener('click', confirmarCadastro);
  $('ibge-cancelar').addEventListener('click', fecharPrevia);
  $('areas-atualizar').addEventListener('click', carregarAreas);
  $('lista-areas').addEventListener('click', (e) => {
    const b = e.target.closest('button[data-campo]');
    if (b) alterarArea(b);
  });

  // usuários
  $('form-usuarios').addEventListener('submit', (e) => { e.preventDefault(); usuariosPag.deslocamento = 0; carregarUsuarios(); });
  $('u-ant').addEventListener('click', () => { usuariosPag.deslocamento = Math.max(0, usuariosPag.deslocamento - POR_PAGINA); carregarUsuarios(); });
  $('u-prox').addEventListener('click', () => { usuariosPag.deslocamento += POR_PAGINA; carregarUsuarios(); });
  $('lista-usuarios').addEventListener('click', (e) => {
    const b = e.target.closest('[data-papel]');
    if (b) abrirDialogoPapel(b.dataset.papel);
  });
  $('papel-novo').addEventListener('change', atualizarCampoArea);
  $('form-papel').addEventListener('submit', salvarPapel);

  // tipos
  $('t-grav').addEventListener('click', (e) => alternar(e.currentTarget));
  $('form-tipo').addEventListener('submit', criarTipo);
  $('lista-tipos').addEventListener('click', (e) => {
    const card = e.target.closest('[data-tipo]');
    if (!card) return;
    const codigo = card.dataset.tipo;
    if (e.target.closest('[data-editar]')) return abrirEdicaoTipo(codigo);
    const sw = e.target.closest('[data-ativo]');
    if (sw) alterarTipo(codigo, { ativo: sw.getAttribute('aria-checked') !== 'true' }, sw);
  });
  $('form-editar-tipo').addEventListener('submit', salvarEdicaoTipo);

  // fechar diálogos
  document.querySelectorAll('dialog [data-fechar]').forEach((b) => b.addEventListener('click', () => b.closest('dialog').close()));

  window.addEventListener('hashchange', () => irPara(location.hash.slice(1)));
  irPara(location.hash.slice(1));
});
