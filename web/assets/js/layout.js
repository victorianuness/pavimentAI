// =============================================================================
// layout.js — cabeçalho e rodapé iguais em todas as páginas.
//
// Na página, basta:
//   <body data-pagina="inicio">           (inicio | cidadao | gestao | admin)
//   <div id="cabecalho"></div> ... <div id="rodape"></div>
//
// Para ADICIONAR uma página no menu, edite a função itensDoMenu() abaixo.
// =============================================================================

function itensDoMenu(u) {
  const itens = [
    { id: 'inicio', texto: 'Início', href: RAIZ + 'index.html' },
    { id: 'mapa', texto: 'Mapa', href: RAIZ + 'index.html#mapa' },
  ];
  if (u) itens.push({ id: 'cidadao', texto: 'Meu espaço', href: RAIZ + 'cidadao/' });
  if (u && ['gestor', 'admin'].includes(u.papel)) itens.push({ id: 'gestao', texto: 'Gestão', href: RAIZ + 'gestao/' });
  if (u && u.papel === 'admin') itens.push({ id: 'admin', texto: 'Administração', href: RAIZ + 'admin/' });
  return itens;
}

function renderCabecalho(u) {
  const alvo = document.getElementById('cabecalho');
  if (!alvo) return;
  const pagina = document.body.dataset.pagina;
  const links = itensDoMenu(u)
    .map((i) => `<a href="${i.href}" class="nav-link ${i.id === pagina ? 'ativo' : ''}">${i.texto}</a>`)
    .join('');

  const area = u
    ? `<div class="hidden sm:flex items-center gap-2.5 pr-1">
         <span class="w-8 h-8 rounded-full bg-brand-100 text-brand-800 grid place-items-center text-sm font-bold">${escaparHTML(u.nome.trim()[0]?.toUpperCase() || '?')}</span>
         <div class="leading-tight">
           <p class="text-sm font-semibold max-w-[9rem] truncate">${escaparHTML(u.nome)}</p>
           <p class="text-[11px] text-ink-soft capitalize">${escaparHTML({ cidadao: 'cidadão' }[u.papel] || u.papel)}</p>
         </div>
       </div>
       <button id="btn-sair" class="btn btn-outline btn-sm" title="Sair">${icone('sair', 'w-4 h-4')}<span class="hidden sm:inline">Sair</span></button>`
    : `<button id="btn-entrar" class="btn btn-ghost btn-sm">Entrar</button>
       <button id="btn-criar" class="btn btn-primary btn-sm">Criar conta</button>`;

  alvo.innerHTML = `
    <header class="sticky top-0 z-40 bg-white/85 backdrop-blur border-b border-line">
      <div class="max-w-7xl mx-auto px-4 h-16 flex items-center justify-between gap-4">
        <a href="${RAIZ}index.html" class="flex items-center gap-2.5 shrink-0" aria-label="PavimentAI — início">
          <span class="w-9 h-9 rounded-xl bg-brand-600 text-white grid place-items-center">${icone('logo', 'w-5 h-5')}</span>
          <span class="font-extrabold text-lg tracking-tight">Paviment<span class="text-brand-600">AI</span></span>
        </a>
        <nav class="hidden md:flex items-center gap-1" aria-label="Principal">${links}</nav>
        <div class="flex items-center gap-2">
          ${area}
          <button id="btn-menu" class="md:hidden btn btn-ghost btn-sm" aria-label="Abrir menu" aria-expanded="false">${icone('menu', 'w-5 h-5')}</button>
        </div>
      </div>
      <nav id="menu-mobile" class="hidden md:hidden border-t border-line px-4 py-2 flex flex-col gap-1" aria-label="Principal (celular)">${links}</nav>
    </header>`;

  document.getElementById('btn-sair')?.addEventListener('click', logout);
  document.getElementById('btn-entrar')?.addEventListener('click', () => abrirModalAuth('login'));
  document.getElementById('btn-criar')?.addEventListener('click', () => abrirModalAuth('cadastro'));
  const menu = document.getElementById('menu-mobile');
  const btnMenu = document.getElementById('btn-menu');
  btnMenu.addEventListener('click', () => {
    const aberto = menu.classList.toggle('hidden') === false;
    btnMenu.setAttribute('aria-expanded', String(aberto));
  });
}

function renderRodape() {
  const alvo = document.getElementById('rodape');
  if (!alvo) return;
  alvo.innerHTML = `
    <footer class="border-t border-line bg-surface mt-16">
      <div class="max-w-7xl mx-auto px-4 py-8 flex flex-col sm:flex-row gap-3 items-start sm:items-center justify-between text-sm text-ink-soft">
        <p><span class="font-bold text-ink">PavimentAI</span> — zeladoria urbana inteligente com visão computacional.</p>
        <p class="text-xs">Mapa © colaboradores do OpenStreetMap · Limites municipais: IBGE</p>
      </div>
    </footer>`;
}

window.addEventListener('DOMContentLoaded', async () => {
  renderRodape();
  renderCabecalho(null); // já mostra algo enquanto confirma a sessão
  try {
    renderCabecalho(await usuarioAtual());
  } catch (e) {
    toast(`Não foi possível validar a sessão: ${e.message}`, 'erro');
  }
});
