CREATE OR REPLACE FUNCTION make_plpgsql()
RETURNS VOID
LANGUAGE SQL
AS $$
CREATE LANGUAGE plpgsql;
$$;
 
SELECT
    CASE
    WHEN EXISTS(
        SELECT 1
        FROM pg_catalog.pg_language
        WHERE lanname='plpgsql'
    )
    THEN NULL
    ELSE make_plpgsql() END;
 
DROP FUNCTION make_plpgsql();

CREATE OR REPLACE FUNCTION safe_insert_new_user() RETURNS trigger AS $$
BEGIN
  if exists( select 1 from accounts where email = NEW.email) then
    RETURN NULL;
  else
    RETURN NEW;
  end if;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION drop_trigger()
RETURNS VOID
LANGUAGE SQL
AS $$
DROP TRIGGER safe_insert_new_user_trigger ON accounts;
$$;
 
SELECT
    CASE
    WHEN EXISTS(
        SELECT 1
        FROM pg_catalog.pg_trigger
        WHERE tgname = 'safe_insert_new_user_trigger' AND
              tgrelid = 'accounts'::regclass
    )
    THEN drop_trigger()
    ELSE NULL END;
 
DROP FUNCTION drop_trigger();

CREATE TRIGGER safe_insert_new_user_trigger BEFORE INSERT ON accounts
   FOR EACH ROW EXECUTE PROCEDURE safe_insert_new_user();
