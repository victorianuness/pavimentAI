# pavimentAI

## Configuração de ambiente

Os arquivos locais de configuração devem ter o nome exato `.env` e não devem ser enviados ao GitHub. Para iniciar com Docker Compose, crie os dois arquivos a partir dos modelos:

```powershell
Copy-Item .env.example .env
Copy-Item api\.env.example api\.env
```

Edite ambos e substitua os valores `troque_...`; gere um `JWT_SECRET` novo usando o comando indicado em `api\.env.example`. Use senhas fortes sem espaços para evitar problemas com a interpolação do Docker Compose. O `.env` da raiz configura a senha do usuário `postgres` do contêiner; `api\.env` configura as credenciais e opções da API. Não reutilize senhas de produção nos exemplos nem nos arquivos enviados ao repositório.

Para executar a API diretamente na máquina, crie também `api\.env` a partir de `api\.env.example`. Consulte [api/readme_da_api.md](api/readme_da_api.md) para os passos de inicialização.