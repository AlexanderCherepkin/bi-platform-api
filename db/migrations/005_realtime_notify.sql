-- =============================================================================
-- BI DWH — Real-time notifications for metrics updates
-- Trigger + NOTIFY on fact_transactions and fact_expenses mutations
-- =============================================================================

CREATE OR REPLACE FUNCTION fn_notify_metrics_update()
RETURNS TRIGGER AS $$
DECLARE
    v_id bigint;
BEGIN
    IF TG_TABLE_NAME = 'fact_transactions' THEN
        v_id := COALESCE(NEW.transaction_id, OLD.transaction_id);
    ELSIF TG_TABLE_NAME = 'fact_expenses' THEN
        v_id := COALESCE(NEW.expense_id, OLD.expense_id);
    ELSE
        v_id := NULL;
    END IF;

    PERFORM pg_notify('metrics_update', jsonb_build_object(
        'table', TG_TABLE_NAME,
        'op', LOWER(TG_OP),
        'id', v_id,
        'ts', NOW()
    )::text);
    RETURN COALESCE(NEW, OLD);
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_metrics_update_transactions ON fact_transactions;
CREATE TRIGGER trg_metrics_update_transactions
    AFTER INSERT OR UPDATE OR DELETE ON fact_transactions
    FOR EACH ROW EXECUTE FUNCTION fn_notify_metrics_update();

DROP TRIGGER IF EXISTS trg_metrics_update_expenses ON fact_expenses;
CREATE TRIGGER trg_metrics_update_expenses
    AFTER INSERT OR UPDATE OR DELETE ON fact_expenses
    FOR EACH ROW EXECUTE FUNCTION fn_notify_metrics_update();
