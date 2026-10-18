\getenv flag_user FLAG_APP_USER
\getenv flag_password FLAG_APP_PASSWORD
\getenv targeting_user TARGETING_APP_USER
\getenv targeting_password TARGETING_APP_PASSWORD

-- Cria os usuarios caso ainda nao existam.
SELECT format('CREATE ROLE %I LOGIN', :'flag_user')
WHERE NOT EXISTS (
    SELECT 1 FROM pg_roles WHERE rolname = :'flag_user'
)
\gexec

SELECT format('CREATE ROLE %I LOGIN', :'targeting_user')
WHERE NOT EXISTS (
    SELECT 1 FROM pg_roles WHERE rolname = :'targeting_user'
)
\gexec

ALTER ROLE :"flag_user"
    WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE
    NOREPLICATION NOBYPASSRLS
    PASSWORD :'flag_password';

ALTER ROLE :"targeting_user"
    WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE
    NOREPLICATION NOBYPASSRLS
    PASSWORD :'targeting_password';

-- Remove o acesso publico e autoriza cada usuario no seu banco.
REVOKE ALL ON DATABASE flags_db FROM PUBLIC;
REVOKE ALL ON DATABASE targeting_db FROM PUBLIC;

REVOKE ALL ON DATABASE flags_db FROM :"targeting_user";
REVOKE ALL ON DATABASE targeting_db FROM :"flag_user";

GRANT CONNECT ON DATABASE flags_db TO :"flag_user";
GRANT CONNECT ON DATABASE targeting_db TO :"targeting_user";

\connect flags_db

REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO :"flag_user";

GRANT SELECT, INSERT, UPDATE, DELETE
    ON TABLE public.flags TO :"flag_user";

GRANT USAGE, SELECT
    ON SEQUENCE public.flags_id_seq TO :"flag_user";

\connect targeting_db

REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO :"targeting_user";

GRANT SELECT, INSERT, UPDATE, DELETE
    ON TABLE public.targeting_rules TO :"targeting_user";

GRANT USAGE, SELECT
    ON SEQUENCE public.targeting_rules_id_seq TO :"targeting_user";