-- Dev DB Init Script
-- Creates the app_user role and fixes Postgres 15+ schema permissions
-- paper_user is the superuser (used for migrations)

-- Grant CREATE on public schema to paper_user (Postgres 15+ revokes this)
GRANT ALL ON SCHEMA public TO paper_user;

-- Create app_user role for RLS enforcement
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'app_user') THEN
        CREATE ROLE app_user WITH LOGIN PASSWORD 'app_pass';
    END IF;
END
$$;

-- Grant connect
GRANT CONNECT ON DATABASE paper_trading TO app_user;

-- Grant schema usage + create
GRANT USAGE, CREATE ON SCHEMA public TO app_user;

-- Default privileges: any tables paper_user creates, app_user can use
ALTER DEFAULT PRIVILEGES FOR ROLE paper_user IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO app_user;
