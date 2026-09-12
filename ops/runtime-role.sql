-- Owner-reviewed psql template. Never run by migrations or application startup.
-- Supply -v target_database=... -v app_schema=... -v migration_role=... -v runtime_role=...
-- app_schema must contain only Taskora/Django objects owned by migration_role.
-- No passwords or connection strings belong in this file or invocation logs.
\set ON_ERROR_STOP on
\if :{?target_database}
\else
DO $$ BEGIN RAISE EXCEPTION 'Supply target_database explicitly.'; END $$;
\endif
\if :{?app_schema}
\else
DO $$ BEGIN RAISE EXCEPTION 'Supply app_schema explicitly.'; END $$;
\endif
\if :{?migration_role}
\else
DO $$ BEGIN RAISE EXCEPTION 'Supply migration_role explicitly.'; END $$;
\endif
\if :{?runtime_role}
\else
DO $$ BEGIN RAISE EXCEPTION 'Supply a NEW runtime_role explicitly.'; END $$;
\endif

BEGIN;
SELECT set_config('taskora.role_setup.database', :'target_database', true) AS target_database,
       set_config('taskora.role_setup.schema', :'app_schema', true) AS app_schema,
       set_config('taskora.role_setup.migrator', :'migration_role', true) AS migration_role,
       set_config('taskora.role_setup.runtime', :'runtime_role', true) AS runtime_role
\gset

DO $role_setup$
DECLARE
    target_db text := current_setting('taskora.role_setup.database');
    target_schema text := current_setting('taskora.role_setup.schema');
    migrator text := current_setting('taskora.role_setup.migrator');
    runtime_name text := current_setting('taskora.role_setup.runtime');
    schema_oid oid;
    migrator_oid oid;
    object_record record;
BEGIN
    IF current_database() <> target_db THEN
        RAISE EXCEPTION 'Wrong database: reconnect to the reviewed target before granting privileges.';
    END IF;
    IF target_schema = 'information_schema' OR target_schema ~ '^pg_' THEN
        RAISE EXCEPTION 'System schemas cannot be application schemas.';
    END IF;
    SELECT oid INTO schema_oid FROM pg_namespace WHERE nspname = target_schema;
    SELECT oid INTO migrator_oid FROM pg_roles WHERE rolname = migrator;
    IF schema_oid IS NULL OR migrator_oid IS NULL THEN
        RAISE EXCEPTION 'The reviewed application schema and migration owner must already exist.';
    END IF;
    IF runtime_name = '' OR runtime_name = migrator OR runtime_name ~ '^pg_'
       OR EXISTS (SELECT FROM pg_roles WHERE rolname = runtime_name) THEN
        RAISE EXCEPTION 'Use a new, separate runtime role; existing roles are never overwritten.';
    END IF;
    -- PUBLIC privileges also apply to NOINHERIT roles. Fail instead of revoking
    -- shared permissions belonging to other applications or administrators.
    IF EXISTS (
        SELECT FROM pg_namespace n,
            LATERAL aclexplode(coalesce(n.nspacl, acldefault('n', n.nspowner))) a
        WHERE n.nspname !~ '^pg_' AND n.nspname <> 'information_schema'
          AND a.grantee = 0 AND a.privilege_type = 'CREATE'
    ) OR EXISTS (
        SELECT FROM pg_database d,
            LATERAL aclexplode(coalesce(d.datacl, acldefault('d', d.datdba))) a
        WHERE d.datname = target_db AND a.grantee = 0 AND a.privilege_type = 'CREATE'
    ) THEN
        RAISE EXCEPTION 'Inherited PUBLIC CREATE exists. Owner must review shared ACLs separately; this template changes none.';
    END IF;
    IF EXISTS (
        SELECT FROM pg_class c WHERE c.relnamespace = schema_oid
          AND c.relkind IN ('r', 'p', 'v', 'm', 'f', 'S')
          AND (c.relowner <> migrator_oid OR c.relname !~ '^(marketplace_|django_|auth_|authtoken_)')
    ) THEN
        RAISE EXCEPTION 'Schema contains unrelated or differently owned objects. Select a dedicated reviewed Taskora schema.';
    END IF;

    EXECUTE format('CREATE ROLE %I LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS NOINHERIT', runtime_name);
    EXECUTE format('GRANT CONNECT ON DATABASE %I TO %I', target_db, runtime_name);
    EXECUTE format('GRANT USAGE ON SCHEMA %I TO %I', target_schema, runtime_name);
    -- Enumerate verified objects; never issue an unbounded ALL TABLES grant.
    FOR object_record IN SELECT relname, relkind FROM pg_class
        WHERE relnamespace = schema_oid AND relowner = migrator_oid
          AND relkind IN ('r', 'p', 'v', 'm', 'f', 'S')
    LOOP
        IF object_record.relkind = 'S' THEN
            EXECUTE format('GRANT USAGE, SELECT ON SEQUENCE %I.%I TO %I', target_schema, object_record.relname, runtime_name);
        ELSE
            EXECUTE format('GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE %I.%I TO %I', target_schema, object_record.relname, runtime_name);
        END IF;
    END LOOP;
    -- The migration role must be dedicated to this application. Its future
    -- objects inherit grants only inside this explicitly reviewed schema.
    EXECUTE format('ALTER DEFAULT PRIVILEGES FOR ROLE %I IN SCHEMA %I GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO %I', migrator, target_schema, runtime_name);
    EXECUTE format('ALTER DEFAULT PRIVILEGES FOR ROLE %I IN SCHEMA %I GRANT USAGE, SELECT ON SEQUENCES TO %I', migrator, target_schema, runtime_name);
    EXECUTE format('ALTER ROLE %I IN DATABASE %I SET search_path TO pg_catalog, %I', runtime_name, target_db, target_schema);
END
$role_setup$;
COMMIT;
-- Set the password afterward with the secure interactive psql \password command.
-- Review PUBLIC CONNECT/EXECUTE/TEMP and other cluster ACLs separately; granting
-- CONNECT here does not revoke access that PUBLIC already has to other databases.
