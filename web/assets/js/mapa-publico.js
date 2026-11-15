// =============================================================================
// mapa-publico.js — mapa da página inicial (somente leitura).
// Aqui só se VÊ ocorrências. Criar/gerir ocorrência fica em cidadao/ e gestao/.
// Contratos com as outras páginas (querystring):
//   cidadao/?nova=1&lat=..&lon=..        → abre o formulário de nova ocorrência naquele ponto
//   cidadao/?ocorrencia=ID               → abre o detalhe/sinalização de uma ocorrência
//   gestao/?ocorrencia=ID                → abre o detalhe de gestão de uma ocorrência
// =============================================================================

let mapa, camadaAreas, camadaMarcadores, camadaClusters, marcadorSelecao;
let areasAtendidas = [];
let catalogoTipos = [];
let _timerMapa = null;
let _reqMapa = 0;
let _abortMapa = null;

// ------------------------------------------------------------------ mapa
function inicializarMapa() {
  mapa = L.map('mapa-principal').setView([-23.705, -46.415], 13); // Ribeirão Pires / ABC
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 19,
    attribution: '&copy; OpenStreetMap',
  }).addTo(mapa);

  camadaAreas = L.layerGroup().addTo(mapa);
  camadaClusters = L.layerGroup().addTo(mapa);
  camadaMarcadores = L.layerGroup().addTo(mapa);

  mapa.on('moveend', agendarAtualizacao);
  mapa.on('click', (e) => {
    const { lat, lng } = e.latlng;
    if (marcadorSelecao) mapa.removeLayer(marcadorSelecao);
    const popup = document.createElement('div');
    popup.className = 'text-xs space-y-2';
    popup.innerHTML = `<p class="font-bold">Reportar neste ponto?</p>
      <p class="text-ink-soft">${lat.toFixed(5)}, ${lng.toFixed(5)}</p>`;
    const btn = document.createElement('button');
    btn.className = 'btn btn-primary btn-sm w-full';
    btn.textContent = 'Reportar aqui';
    btn.addEventListener('click', () => reportarEm(lat, lng));
    popup.appendChild(btn);
    marcadorSelecao = L.marker([lat, lng]).addTo(mapa).bindPopup(popup).openPopup();
  });
}

// Leva a pessoa ao formulário do cidadão (ou pede login antes)
async function reportarEm(lat, lon) {
  const u = await usuarioAtual();
  if (!u) {
    toast('Entre ou crie uma conta para reportar.', 'info');
    return abrirModalAuth('login');
  }
  const q = new URLSearchParams({ nova: '1' });
  if (lat !== null) { q.set('lat', lat.toFixed(6)); q.set('lon', lon.toFixed(6)); }
  location.href = `${RAIZ}cidadao/?${q}`;
}

// ------------------------------------------------------------------ dados iniciais
async function carregarAreasETipos() {
  try {
    const [geoAreas, tipos] = await Promise.all([api('/areas'), api('/ocorrencias/tipos')]);
    catalogoTipos = tipos || [];
    areasAtendidas = geoAreas.features || [];

    const selArea = document.getElementById('filtro-area');
    selArea.innerHTML = '<option value="">Todos os atendidos</option>' + areasAtendidas
      .map((f) => `<option value="${f.properties.id_area}">${escaparHTML(f.properties.nome)}</option>`).join('');

    const selTipo = document.getElementById('filtro-tipo');
    selTipo.innerHTML = '<option value="">Todos</option>' + catalogoTipos
      .map((t) => `<option value="${escaparHTML(t.codigo)}">${escaparHTML(t.nome)}</option>`).join('');

    document.getElementById('stat-municipios').textContent = areasAtendidas.length;

    camadaAreas.clearLayers();
    const grupo = L.featureGroup();
    areasAtendidas.forEach((feat) => {
      grupo.addLayer(L.geoJSON(feat, {
        style: { color: '#1f8556', weight: 2, fillColor: '#34a06b', fillOpacity: 0.06, dashArray: '6 5' },
      }).addTo(camadaAreas));
    });
    if (areasAtendidas.length) mapa.fitBounds(grupo.getBounds(), { padding: [20, 20] });
  } catch (e) {
    toast(`Não foi possível carregar os municípios: ${e.message}`, 'erro');
  }
}

function centralizarAreaSelecionada() {
  const id = document.getElementById('filtro-area').value;
  const feat = areasAtendidas.find((f) => String(f.properties.id_area) === id);
  if (feat) mapa.fitBounds(L.geoJSON(feat).getBounds(), { padding: [20, 20] });
  else atualizarMapa();
}

// ------------------------------------------------------------------ marcadores
const COR_GRAVIDADE = { grave: '#dc2626', moderado: '#f59e0b', leve: '#1f8556' };

function iconePorGravidade(gravidade, tipo) {
  const cor = COR_GRAVIDADE[gravidade] || (tipo === 'buraco' ? '#d97706' : '#2563eb');
  return L.divIcon({
    className: '',
    html: `<div style="background:${cor}" class="marker-pin"></div>`,
    iconSize: [24, 34],
    iconAnchor: [12, 34],
  });
}

function agendarAtualizacao() {
  clearTimeout(_timerMapa);
  _timerMapa = setTimeout(atualizarMapa, 200);
}

async function atualizarMapa() {
  if (!mapa) return;
  _abortMapa?.abort();
  const controller = new AbortController();
  _abortMapa = controller;
  const requisicao = ++_reqMapa;
  const estado = document.getElementById('mapa-estado');
  estado.textContent = 'Carregando…';

  const b = mapa.getBounds();
  const params = new URLSearchParams({
    lat_min: Math.max(-90, b.getSouth()).toFixed(6),
    lat_max: Math.min(90, b.getNorth()).toFixed(6),
    lon_min: Math.max(-180, b.getWest()).toFixed(6),
    lon_max: Math.min(180, b.getEast()).toFixed(6),
    verificacao: document.getElementById('filtro-verif').value,
  });
  const idArea = document.getElementById('filtro-area').value;
  const tipo = document.getElementById('filtro-tipo').value;
  if (idArea) params.set('id_area', idArea);
  if (tipo) params.set('tipo', tipo);

  try {
    if (mapa.getZoom() < 15) {
      const pc = new URLSearchParams(params);
      pc.set('dias', document.getElementById('filtro-dias').value);
      pc.set('tamanho_celula_m', document.getElementById('filtro-celula').value);
      const geo = await api(`/ocorrencias/clusters?${pc}`, { signal: controller.signal });
      if (requisicao !== _reqMapa) return;
      desenharClusters(geo);
      const n = geo.features?.length || 0;
      estado.textContent = n ? `${n} ${n === 1 ? 'região' : 'regiões'} com concentração${geo.truncado ? ' (limitado)' : ''}` : 'Nenhuma concentração neste período.';
    } else {
      const geo = await api(`/ocorrencias/mapa?${params}`, { signal: controller.signal });
      if (requisicao !== _reqMapa) return;
      camadaClusters.clearLayers();
      camadaMarcadores.clearLayers();
      (geo.features || []).forEach((f) => {
        const [lon, lat] = f.geometry.coordinates;
        const p = f.properties;
        L.marker([lat, lon], { icon: iconePorGravidade(p.gravidade, p.tipo) })
          .on('click', () => abrirOcorrencia(p.id_ocorrencia))
          .addTo(camadaMarcadores);
      });
      const n = geo.features?.length || 0;
      estado.textContent = `${n} ocorrência${n === 1 ? '' : 's'}`;
      document.getElementById('stat-ocorrencias').textContent = n;
    }
  } catch (e) {
    if (e.name === 'AbortError' || requisicao !== _reqMapa) return;
    camadaClusters.clearLayers();
    camadaMarcadores.clearLayers();
    estado.textContent = `Não foi possível carregar o mapa: ${e.message}`;
  }
}

function desenharClusters(geo) {
  camadaClusters.clearLayers();
  camadaMarcadores.clearLayers();
  let total = 0;
  (geo.features || []).forEach((f) => {
    const [lon, lat] = f.geometry.coordinates;
    const p = f.properties;
    total += p.total_ocorrencias;
    const corTipo = p.por_tipo.some((t) => t.tipo === 'buraco') ? '#d97706' : '#2563eb';
    const corNivel = { alta: '#dc2626', moderada: '#f59e0b', normal: '#1f8556' }[p.nivel_concentracao] || '#5b6b62';
    const icone = L.divIcon({
      className: '',
      html: `<div style="width:42px;height:42px;border-radius:50%;display:flex;align-items:center;justify-content:center;background:${corTipo};border:3px solid ${corNivel};color:#fff;font-weight:800;box-shadow:0 2px 8px #0005">${p.total_ocorrencias}</div>`,
      iconSize: [42, 42],
      iconAnchor: [21, 21],
    });
    const linhas = p.por_tipo.map((t) => {
      const nome = catalogoTipos.find((c) => c.codigo === t.tipo)?.nome || t.tipo;
      const cats = Object.entries(t.categorias).map(([c, n]) => `${escaparHTML(c)}: ${n}`).join(', ');
      return `<li>${escaparHTML(nome)}: <b>${t.total}</b>${cats ? ` (${cats})` : ''}</li>`;
    }).join('');
    const popup = `<div class="text-xs space-y-1"><p class="font-bold">Concentração ${escaparHTML(p.nivel_concentracao)}</p>
      <p>${p.total_ocorrencias} ocorrências na célula</p><ul class="list-disc pl-4">${linhas}</ul>
      <p class="text-ink-soft">Agrupamento de relatos; não representa risco real.</p></div>`;
    L.marker([lat, lon], { icon: icone }).bindPopup(popup).addTo(camadaClusters);
  });
  document.getElementById('stat-ocorrencias').textContent = total;
}

// ------------------------------------------------------------------ detalhe (somente leitura)
async function abrirOcorrencia(id) {
  const modal = document.getElementById('modal-ocorrencia');
  const eu = await usuarioAtual().catch(() => null);
  try {
    const [occ, fotos] = await Promise.all([
      api(`/ocorrencias/${id}`),
      api(`/ocorrencias/${id}/fotos`).catch(() => []),
    ]);
    const grav = occ.gravidade;
    document.getElementById('occ-badges').innerHTML =
      badgeStatus(occ.status) + badgeGravidade(grav) +
      (occ.situacao_ia ? `<span class="badge badge-ambar">IA: ${escaparHTML(occ.situacao_ia)}</span>` : '');
    document.getElementById('occ-titulo').textContent =
      `#${occ.id_ocorrencia} · ${occ.tipo}${occ.categoria ? ` (${occ.categoria})` : ''}`;
    document.getElementById('occ-sub').textContent =
      `Registrada em ${formatarData(occ.criado_em)} · ${occ.latitude.toFixed(5)}, ${occ.longitude.toFixed(5)}`;
    document.getElementById('occ-desc').textContent = occ.descricao || 'Sem descrição informada.';

    const box = document.getElementById('occ-fotos');
    box.innerHTML = fotos.length
      ? fotos.map((f) => `<div class="rounded-xl overflow-hidden border border-line bg-ink">
          <img data-foto-url="${escaparHTML(API_BASE + f.url)}" alt="Foto da ocorrência" class="w-full h-52 object-contain" /></div>`).join('')
      : '<p class="text-sm text-ink-soft italic">Nenhuma foto anexada.</p>';
    carregarFotosAutenticadas(box);

    // Ações: cada papel continua o trabalho na própria página
    const acoes = document.getElementById('occ-acoes');
    acoes.innerHTML = '';
    if (eu && ['gestor', 'admin'].includes(eu.papel)) {
      acoes.innerHTML = `<a class="btn btn-primary btn-sm" href="${RAIZ}gestao/?ocorrencia=${id}">Gerir na área de gestão</a>`;
    } else if (eu && occ.status === 'aberta') {
      acoes.innerHTML = `<a class="btn btn-outline btn-sm" href="${RAIZ}cidadao/?ocorrencia=${id}">Sinalizar um erro</a>`;
    }
    modal.classList.remove('hidden');
  } catch (err) {
    toast(err.message, 'erro');
  }
}

function fecharOcorrencia() {
  document.getElementById('modal-ocorrencia').classList.add('hidden');
}

// ------------------------------------------------------------------ início
window.addEventListener('DOMContentLoaded', async () => {
  inicializarMapa();

  document.getElementById('filtro-area').addEventListener('change', centralizarAreaSelecionada);
  ['filtro-tipo', 'filtro-verif', 'filtro-dias', 'filtro-celula']
    .forEach((id) => document.getElementById(id).addEventListener('change', atualizarMapa));
  document.getElementById('occ-fechar').addEventListener('click', fecharOcorrencia);
  document.getElementById('modal-ocorrencia').addEventListener('click', (e) => {
    if (e.target.id === 'modal-ocorrencia') fecharOcorrencia();
  });
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape') fecharOcorrencia(); });

  // gestão/admin podem ver também o que ainda está em triagem
  usuarioAtual().then((u) => {
    if (u && ['gestor', 'admin'].includes(u.papel)) document.getElementById('box-verificacao').classList.remove('hidden');
  }).catch(() => {});

  await carregarAreasETipos();
  atualizarMapa();
});
