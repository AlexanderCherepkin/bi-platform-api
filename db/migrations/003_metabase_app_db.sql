-- Ensure the separate application database exists for the Metabase container.
-- Metabase does not create this automatically when MB_DB_TYPE=postgres is set.
CREATE DATABASE metabase_app;
