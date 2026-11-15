// =============================================================================
// core.js — infraestrutura compartilhada (API, tokens, sessão, guarda de página)
// Todas as páginas carregam este arquivo. Funções ficam globais de propósito
// (mesmo estilo do código antigo), então dá pra usar api(), toast(), etc. direto.
// =============================================================================

// Raiz do front (a pasta /web/), calculada a partir deste próprio script.
// Use RAIZ + 'admin/' para linkar páginas, não caminhos fixos.
const RAIZ = new URL('../../', document.currentScript.src).href;

// Rodando dentro da própria API (/web/...) → mesma origem. Fora (Live Server) → API local.
const API_BASE = window.location.pathname.startsWith('/web')
  ? window.location.origin
  : (localStorage.getItem('PAVIMENTAI_API_URL') || 'http://127.0.0.1:8000');

// Para onde cada papel vai depois do login
const PAINEL_POR_PAPEL = { cidadao: 'cidadao/', gestor: 'gestao/', admin: 'admin/' };
const painelDoPapel = (papel) => RAIZ + (PAINEL_POR_PAPEL[papel] || '');

let tokenJWT = localStorage.getItem('PAVIMENTAI_TOKEN') || null;
let refreshToken = localStorage.getItem('PAVIMENTAI_REFRESH_TOKEN') || null;
let refreshPromise = null;
let _usuarioPromise = null;

// ------------------------------------------------------------------ tokens
function salvarTokens(access, refresh) {
  tokenJWT = access;
  refreshToken = refresh;
  localStorage.setItem('PAVIMENTAI_TOKEN', access);
  localStorage.setItem('PAVIMENTAI_REFRESH_TOKEN', refresh);
  _usuarioPromise = null;
}

function limparTokens() {
  tokenJWT = null;
  refreshToken = null;
  localStorage.removeItem('PAVIMENTAI_TOKEN');
  localStorage.removeItem('PAVIMENTAI_REFRESH_TOKEN');
  _usuarioPromise = null;
}

async function renovarAccessToken() {
  if (!refreshPromise) {
    refreshPromise = (async () => {
      const resp = await fetch(`${API_BASE}/auth/refresh`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh_token: refreshToken }),
      });
      const dados = await resp.json();
      if (resp.status === 401) { limparTokens(); return false; }
      if (!resp.ok) throw new Error(dados?.mensagem || `Erro HTTP ${resp.status} ao renovar a sessão`);
      salvarTokens(dados.access_token, dados.refresh_token);
      return true;
    })();
  }
  try { return await refreshPromise; } finally { refreshPromise = null; }
}

// ---------------------------------------------------------------------- api
// Uso: await api('/ocorrencias/minhas')
//      await api('/admin/areas', { method: 'POST', json: { codigo_ibge: '3543303' } })
// Erros viram Error com .status, .codigo e .detail (a API devolve {codigo, mensagem}).
async function api(caminho, opcoes = {}) {
  const headers = { ...(opcoes.headers || {}) };
  if (tokenJWT) headers['Authorization'] = `Bearer ${tokenJWT}`;
  if (opcoes.json) {
    headers['Content-Type'] = 'application/json';
    opcoes.body = JSON.stringify(opcoes.json);
  }
  const enviar = () => fetch(`${API_BASE}${caminho}`, { ...opcoes, headers });

  let resp;
  try {
    resp = await enviar();
  } catch (e) {
    if (e.name === 'AbortError') throw e;
    throw new Error('Não foi possível falar com o servidor. Confira se a API está rodando.');
  }
  if (resp.status === 401 && refreshToken &&
      !['/auth/login', '/auth/refresh', '/auth/logout'].includes(caminho)) {
    if (await renovarAccessToken()) {
      headers['Authorization'] = `Bearer ${tokenJWT}`;
      resp = await enviar();
    }
  }
  let dados = null;
  if ((resp.headers.get('content-type') || '').includes('application/json')) {
    dados = await resp.json();
  }
  if (!resp.ok) {
    const err = new Error(dados?.mensagem || `Erro HTTP ${resp.status}`);
    err.status = resp.status;
    err.codigo = dados?.codigo;
    err.detail = dados;
    throw err;
  }
  return dados;
}

// ------------------------------------------------------------------ sessão
// Devolve o usuário logado (ou null). Guarda o resultado para não repetir a chamada.
function usuarioAtual(forcar = false) {
  if (forcar) _usuarioPromise = null;
  if (!_usuarioPromise) {
    _usuarioPromise = (async () => {
      if (!tokenJWT && !refreshToken) return null;
      try {
        return await api('/auth/eu');
      } catch (e) {
        if (e.status === 401) { limparTokens(); return null; }
        throw e;
      }
    })();
  }
  return _usuarioPromise;
}

// Garante que a página só abre para certos papéis. Use no começo do script da página:
//   const eu = await exigirPapel(['admin']);
// Sem login → volta para o index abrindo o login (e retorna para cá depois).
// Papel errado → manda para o painel do próprio papel.
async function exigirPapel(papeis) {
  let u;
  try {
    u = await usuarioAtual();
  } catch (e) {
    // API fora do ar: não dá para saber quem é a pessoa, então não segue com a página
    toast(`Não foi possível validar a sessão: ${e.message}`, 'erro');
    return new Promise(() => {});
  }
  if (!u) {
    const volta = encodeURIComponent(location.pathname + location.search);
    location.replace(`${RAIZ}index.html?auth=login&volta=${volta}`);
    return new Promise(() => {}); // não deixa o resto da página rodar enquanto redireciona
  }
  if (papeis && !papeis.includes(u.papel)) {
    sessionStorage.setItem('PAVIMENTAI_AVISO', 'Você não tem acesso a essa área.');
    location.replace(painelDoPapel(u.papel));
    return new Promise(() => {});
  }
  return u;
}

async function logout() {
  if (refreshToken) {
    try {
      await fetch(`${API_BASE}/auth/logout`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh_token: refreshToken }),
      });
    } catch { /* sai localmente mesmo assim */ }
  }
  limparTokens();
  location.href = RAIZ + 'index.html';
}

// Fotos de ocorrências ainda não verificadas exigem login, e <img src> não envia o token.
// Então busca com o Authorization e mostra como blob. Use: <img data-foto-url="...">
async function carregarFotosAutenticadas(container) {
  for (const img of container.querySelectorAll('img[data-foto-url]')) {
    try {
      const headers = tokenJWT ? { Authorization: `Bearer ${tokenJWT}` } : {};
      const resp = await fetch(img.dataset.fotoUrl, { headers });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      img.src = URL.createObjectURL(await resp.blob());
    } catch {
      img.alt = 'Foto indisponível';
    }
  }
}
