-- Owner-reviewed template. Run interactively as the infrastructure owner.
-- Does not contain a password and is NOT run by migrations or application startup.
-- Replace taskora_migrator with the actual object-owning migration role first.
BEGIN;
CREATE ROLE taskora_runtime LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION;
GRANT CONNECT ON DATABASE taskora TO taskora_runtime;
GRANT USAGE ON SCHEMA public TO taskora_runtime;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO taskora_runtime;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO taskora_runtime;
ALTER DEFAULT PRIVILEGES FOR ROLE taskora_migrator IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO taskora_runtime;
ALTER DEFAULT PRIVILEGES FOR ROLE taskora_migrator IN SCHEMA public
    GRANT USAGE, SELECT ON SEQUENCES TO taskora_runtime;
COMMIT;
-- Set the password using the secure interactive psql \password command.
-- Runtime never needs schema ownership, CREATE DATABASE, or a superuser account.
