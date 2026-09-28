-- Creates a least-privilege role for the agent to connect with.
-- The agent must never connect as a superuser: this role can only
-- SELECT from the business tables and cannot run DDL/DML.

DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'readonly_agent') THEN
        CREATE ROLE readonly_agent LOGIN PASSWORD :'agent_password';
    END IF;
END
$$;

ALTER ROLE readonly_agent SET statement_timeout = '5s';
ALTER ROLE readonly_agent SET default_transaction_read_only = on;

GRANT CONNECT ON DATABASE agentic_bi TO readonly_agent;
GRANT USAGE ON SCHEMA public TO readonly_agent;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO readonly_agent;

-- Ensure future tables are also readable without manual re-granting.
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT SELECT ON TABLES TO readonly_agent;
