# PavimentAI — Front-end

Páginas HTML simples (sem build), Tailwind via CDN + um tema compartilhado em verde e branco.
A API (FastAPI) já entrega esta pasta em `/web/`, então não precisa de servidor separado.

## Como rodar

```bash
# opção 1: pela própria API (recomendado) — abre http://127.0.0.1:8000/web/
cd api && pavimentai

# opção 2: Live Server / qualquer servidor estático na pasta web/ (porta 5500, 3000, 5173 ou 8080).
# Nesse caso o front chama a API em http://127.0.0.1:8000. Para outro endereço, no console do navegador:
#   localStorage.setItem('PAVIMENTAI_API_URL', 'http://meu-servidor:8000')
```

## Quem faz o quê

| Pasta | Responsável | Papel que acessa | Status |
| :--- | :--- | :--- | :--- |
| `index.html` + `assets/js/mapa-publico.js` | Rebeca | público | pronto |
| `admin/` | Rebeca | `admin` | pronto |
| `gestao/` | João | `gestor` e `admin` | esqueleto |
| `cidadao/` | Vic | qualquer usuário logado | esqueleto |
| `assets/` | todos (ver regra abaixo) | — | compartilhado |
| `_legado/index.antigo.html` | ninguém | — | só para consulta/cópia |

**Regra para evitar conflito no Git:** cada pessoa mexe só na própria pasta. Mudou algo em `assets/`
(tema, `core.js`, `layout.js`…)? Avise o grupo antes, porque afeta todas as páginas.

## Estrutura

```text
web/
├── index.html              # página inicial: hero + mapa público + login/cadastro
├── admin/                  # index.html + admin.js
├── gestao/                 # index.html (esqueleto)  → crie gestao.js aqui
├── cidadao/                # index.html (esqueleto)  → crie cidadao.js aqui
├── assets/
│   ├── css/tema.css        # componentes: .btn .card .input .badge .switch .modal-fundo …
│   └── js/
│       ├── tailwind-config.js   # cores da marca (brand-*), fonte
│       ├── core.js              # api(), tokens, usuarioAtual(), exigirPapel(), logout()
│       ├── ui.js                # toast(), escaparHTML(), badges, icone(), formatarData()
│       ├── layout.js            # cabeçalho e rodapé (edite itensDoMenu() para o menu)
│       ├── auth.js              # modal de login/cadastro, abrirModalAuth('login')
│       └── mapa-publico.js      # só da página inicial
└── _legado/index.antigo.html    # SPA antigo (2 mil linhas) — fonte para portar gestão e cidadão
```

## Receita de uma página nova

1. Copie `gestao/index.html` (ou `admin/index.html`) para a sua pasta.
2. Ajuste `data-pagina` no `<body>` (marca o item ativo do menu).
3. Carregue os scripts nesta ordem: `core.js` → `ui.js` → `layout.js` → `auth.js` → o seu.
4. No começo do seu JS: `const eu = await exigirPapel(['gestor', 'admin']);`
5. Chame a API com `await api('/rota')`. Erros viram exceção com `.message` pronto para `toast(err.message, 'erro')`.

Links entre páginas: use `RAIZ + 'admin/'`, nunca caminho fixo.

## Contratos entre páginas (querystring)

| Quem chama | Destino | Para quê |
| :--- | :--- | :--- |
| mapa (index) | `cidadao/?nova=1&lat=..&lon=..` | abrir "nova ocorrência" com o ponto marcado |
| mapa (index) | `cidadao/?ocorrencia=ID` | abrir detalhe / sinalizar erro |
| mapa (index) | `gestao/?ocorrencia=ID` | abrir o detalhe de gestão |
| qualquer página protegida | `index.html?auth=login&volta=/caminho` | pede login e volta para `volta` |

Depois do login a pessoa vai para o painel do papel dela: `cidadao/`, `gestao/` ou `admin/`.

## Visual

- **Cores:** `brand-50…900` (verde), `ink` (texto), `ink-soft` (secundário), `line` (bordas), `surface` (fundo suave). Evite `amber`, `purple` e `slate` soltos; para estados use os `.badge-*`.
- **Fonte:** Plus Jakarta Sans.
- **Botões:** `.btn .btn-primary` (ação principal, uma por tela), `.btn-outline`, `.btn-ghost`, `.btn-danger`; `.btn-sm` / `.btn-lg` para tamanhos.
- **Formulários:** `.label` + `.input` / `.select` / `.textarea`.
- **Cartões:** `.card` (branco com borda) e `.card-soft` (fundo suave).
- **Sempre** passe texto vindo da API por `escaparHTML()` antes de usar em `innerHTML`.
