// =============================================================================
// auth.js — janela de login / cadastro / confirmação de e-mail / recuperar senha.
// Injeta o modal sozinha em qualquer página: basta chamar abrirModalAuth('login').
// Depois do login, leva a pessoa ao painel do papel dela (ou à página `?volta=`).
// =============================================================================

const _AUTH_HTML = `
<div id="modal-auth" class="modal-fundo hidden" role="dialog" aria-modal="true" aria-labelledby="auth-titulo">
  <div class="modal-caixa max-w-md p-6 sm:p-7">
    <div class="flex items-start justify-between mb-5">
      <div>
        <h2 id="auth-titulo" class="text-xl font-extrabold tracking-tight">Entrar</h2>
        <p id="auth-sub" class="text-sm text-ink-soft mt-0.5"></p>
      </div>
      <button type="button" data-auth-fechar class="btn btn-ghost btn-sm -mr-2 -mt-1" aria-label="Fechar">✕</button>
    </div>

    <form id="form-login" class="space-y-3.5">
      <div><label class="label" for="login-email">E-mail</label>
        <input class="input" type="email" id="login-email" autocomplete="username" required /></div>
      <div><label class="label" for="login-senha">Senha</label>
        <input class="input" type="password" id="login-senha" autocomplete="current-password" required /></div>
      <button type="submit" class="btn btn-primary w-full">Entrar</button>
      <div class="flex justify-between text-xs text-ink-soft pt-1">
        <button type="button" data-auth-modo="esqueci" class="hover:text-brand-700 hover:underline">Esqueci minha senha</button>
        <button type="button" data-auth-modo="verificar" class="hover:text-brand-700 hover:underline">Tenho um código</button>
      </div>
      <p class="text-sm text-center text-ink-soft border-t border-line pt-4">Ainda não tem conta?
        <button type="button" data-auth-modo="cadastro" class="font-semibold text-brand-700 hover:underline">Criar conta</button></p>
    </form>

    <form id="form-cadastro" class="hidden space-y-3.5">
      <div><label class="label" for="cad-nome">Nome completo</label>
        <input class="input" type="text" id="cad-nome" required minlength="2" autocomplete="name" /></div>
      <div><label class="label" for="cad-email">E-mail</label>
        <input class="input" type="email" id="cad-email" required autocomplete="email" /></div>
      <div><label class="label" for="cad-tel">Telefone (DDD + número)</label>
        <input class="input" type="tel" id="cad-tel" required placeholder="11999998888" autocomplete="tel" /></div>
      <div><label class="label" for="cad-senha">Senha (mínimo 8 caracteres)</label>
        <input class="input" type="password" id="cad-senha" required minlength="8" autocomplete="new-password" /></div>
      <button type="submit" class="btn btn-primary w-full">Criar conta e receber código</button>
      <p class="text-sm text-center text-ink-soft border-t border-line pt-4">Já tem conta?
        <button type="button" data-auth-modo="login" class="font-semibold text-brand-700 hover:underline">Entrar</button></p>
    </form>

    <form id="form-verificar" class="hidden space-y-3.5">
      <p class="text-sm text-ink-soft">Digite o código de 6 dígitos enviado ao seu e-mail.
        <span class="text-xs">(Em modo <code>dev</code>, o código aparece no terminal da API.)</span></p>
      <div><label class="label" for="verif-email">E-mail</label>
        <input class="input" type="email" id="verif-email" required /></div>
      <div><label class="label" for="verif-codigo">Código</label>
        <input class="input text-center font-mono text-xl tracking-[.4em]" type="text" id="verif-codigo" required pattern="\\d{6}" maxlength="6" inputmode="numeric" placeholder="000000" /></div>
      <button type="submit" class="btn btn-primary w-full">Confirmar e-mail</button>
      <button type="button" id="btn-reenviar" class="btn btn-ghost w-full btn-sm">Reenviar código</button>
    </form>

    <form id="form-esqueci" class="hidden space-y-3.5">
      <div><label class="label" for="esq-email">Seu e-mail</label>
        <div class="flex gap-2"><input class="input" type="email" id="esq-email" required />
          <button type="button" id="btn-enviar-recuperacao" class="btn btn-outline">Enviar código</button></div></div>
      <div><label class="label" for="esq-codigo">Código recebido</label>
        <input class="input text-center font-mono tracking-[.4em]" type="text" id="esq-codigo" required pattern="\\d{6}" maxlength="6" inputmode="numeric" /></div>
      <div><label class="label" for="esq-nova-senha">Nova senha (mín. 8 caracteres)</label>
        <input class="input" type="password" id="esq-nova-senha" required minlength="8" autocomplete="new-password" /></div>
      <button type="submit" class="btn btn-primary w-full">Salvar nova senha</button>
    </form>
  </div>
</div>`;

const _AUTH_TEXTOS = {
  login: ['Entrar', 'Acesse sua conta para registrar e acompanhar ocorrências.'],
  cadastro: ['Criar conta', 'Leva menos de um minuto. Confirmamos seu e-mail em seguida.'],
  verificar: ['Confirmar e-mail', ''],
  esqueci: ['Recuperar senha', 'Enviamos um código para o seu e-mail.'],
};

function abrirModalAuth(modo = 'login') {
  const modal = document.getElementById('modal-auth');
  modal.classList.remove('hidden');
  const [titulo, sub] = _AUTH_TEXTOS[modo] || _AUTH_TEXTOS.login;
  document.getElementById('auth-titulo').textContent = titulo;
  document.getElementById('auth-sub').textContent = sub;
  ['login', 'cadastro', 'verificar', 'esqueci'].forEach((m) =>
    document.getElementById(`form-${m}`).classList.toggle('hidden', m !== modo));
  modal.querySelector(`#form-${modo} input`)?.focus();
}

function fecharModalAuth() {
  document.getElementById('modal-auth').classList.add('hidden');
}

// Só aceita voltar para caminhos do próprio site (evita redirecionamento para fora)
function _destinoSeguro(volta) {
  return volta && /^\/(?!\/)/.test(volta) ? volta : null;
}

async function _fazerLogin(e) {
  e.preventDefault();
  const body = new URLSearchParams({
    username: document.getElementById('login-email').value.trim(),
    password: document.getElementById('login-senha').value,
  });
  try {
    const res = await api('/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body,
    });
    salvarTokens(res.access_token, res.refresh_token);
    const u = await usuarioAtual(true);
    const volta = _destinoSeguro(new URLSearchParams(location.search).get('volta'));
    location.href = volta || painelDoPapel(u?.papel);
  } catch (err) {
    toast(err.message, 'erro');
  }
}

async function _fazerCadastro(e) {
  e.preventDefault();
  const email = document.getElementById('cad-email').value.trim();
  try {
    const res = await api('/auth/cadastro', {
      method: 'POST',
      json: {
        nome: document.getElementById('cad-nome').value.trim(),
        email,
        telefone: document.getElementById('cad-tel').value.trim(),
        senha: document.getElementById('cad-senha').value,
      },
    });
    toast(res.mensagem, 'sucesso');
    document.getElementById('verif-email').value = email;
    abrirModalAuth('verificar');
  } catch (err) {
    toast(err.message, 'erro');
  }
}

async function _verificarEmail(e) {
  e.preventDefault();
  const email = document.getElementById('verif-email').value.trim();
  try {
    const res = await api('/auth/verificar-email', {
      method: 'POST',
      json: { email, codigo: document.getElementById('verif-codigo').value.trim() },
    });
    toast(res.mensagem, 'sucesso');
    document.getElementById('login-email').value = email;
    abrirModalAuth('login');
  } catch (err) {
    toast(err.message, 'erro');
  }
}

async function _reenviarCodigo() {
  const email = document.getElementById('verif-email').value.trim();
  if (!email) return toast('Preencha o e-mail primeiro.', 'aviso');
  try {
    toast((await api('/auth/reenviar-codigo', { method: 'POST', json: { email } })).mensagem, 'sucesso');
  } catch (err) { toast(err.message, 'erro'); }
}

async function _pedirRecuperacao() {
  const email = document.getElementById('esq-email').value.trim();
  if (!email) return toast('Informe seu e-mail primeiro.', 'aviso');
  try {
    toast((await api('/auth/esqueci-senha', { method: 'POST', json: { email } })).mensagem, 'sucesso');
  } catch (err) { toast(err.message, 'erro'); }
}

async function _redefinirSenha(e) {
  e.preventDefault();
  try {
    const res = await api('/auth/redefinir-senha', {
      method: 'POST',
      json: {
        email: document.getElementById('esq-email').value.trim(),
        codigo: document.getElementById('esq-codigo').value.trim(),
        senha_nova: document.getElementById('esq-nova-senha').value,
      },
    });
    toast(res.mensagem, 'sucesso');
    abrirModalAuth('login');
  } catch (err) { toast(err.message, 'erro'); }
}

window.addEventListener('DOMContentLoaded', () => {
  document.body.insertAdjacentHTML('beforeend', _AUTH_HTML);
  const modal = document.getElementById('modal-auth');
  modal.addEventListener('click', (e) => {
    if (e.target === modal || e.target.closest('[data-auth-fechar]')) return fecharModalAuth();
    const modo = e.target.closest('[data-auth-modo]')?.dataset.authModo;
    if (modo) abrirModalAuth(modo);
  });
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape') fecharModalAuth(); });
  document.getElementById('form-login').addEventListener('submit', _fazerLogin);
  document.getElementById('form-cadastro').addEventListener('submit', _fazerCadastro);
  document.getElementById('form-verificar').addEventListener('submit', _verificarEmail);
  document.getElementById('form-esqueci').addEventListener('submit', _redefinirSenha);
  document.getElementById('btn-reenviar').addEventListener('click', _reenviarCodigo);
  document.getElementById('btn-enviar-recuperacao').addEventListener('click', _pedirRecuperacao);

  // index.html?auth=login|cadastro abre o modal direto (usado pelos redirecionamentos)
  const pedido = new URLSearchParams(location.search).get('auth');
  if (pedido && _AUTH_TEXTOS[pedido]) {
    usuarioAtual().then((u) => { if (!u) abrirModalAuth(pedido); });
  }
});
