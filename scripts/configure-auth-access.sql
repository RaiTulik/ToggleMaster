\getenv app_user AUTH_APP_USER
\getenv app_password AUTH_APP_PASSWORD

-- Cria o usuario caso ainda nao exista.
SELECT format('CREATE ROLE %I LOGIN', :'app_user')
WHERE NOT EXISTS (
    SELECT 1 FROM pg_roles WHERE rolname = :'app_user'
)
\gexec

-- Define a senha e impede privilegios administrativos.
ALTER ROLE :"app_user"
    WITH LOGIN
    NOSUPERUSER
    NOCREATEDB
    NOCREATEROLE
    NOREPLICATION
    NOBYPASSRLS
    PASSWORD :'app_password';

-- Permite conexao ao banco somente para identidades autorizadas.
REVOKE ALL ON DATABASE auth_db FROM PUBLIC;
GRANT CONNECT ON DATABASE auth_db TO :"app_user";

-- Permite usar as tabelas existentes, sem criar objetos no schema.
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO :"app_user";

GRANT SELECT, INSERT, UPDATE, DELETE
    ON TABLE public.api_keys TO :"app_user";

GRANT USAGE, SELECT
    ON SEQUENCE public.api_keys_id_seq TO :"app_user";