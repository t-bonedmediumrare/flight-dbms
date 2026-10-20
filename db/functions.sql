-- Logs every change to fare_class.current_price into price_history.
-- The reason comes from the session setting app.price_reason if reprice() set one.
CREATE OR REPLACE FUNCTION log_price_change() RETURNS trigger AS $$
BEGIN
  IF NEW.current_price IS DISTINCT FROM OLD.current_price THEN
    INSERT INTO price_history (class_id, old_price, new_price, reason, changed_at)
    VALUES (
      NEW.class_id,
      OLD.current_price,
      NEW.current_price,
      COALESCE(NULLIF(current_setting('app.price_reason', true), ''), 'price update'),
      now()
    );
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_fare_price_history ON fare_class;
CREATE TRIGGER trg_fare_price_history
  AFTER UPDATE OF current_price ON fare_class
  FOR EACH ROW EXECUTE FUNCTION log_price_change();
