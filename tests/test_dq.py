from etl.utils.dq import run_dq_checks


def test_dq_detects_missing_date_and_amount():
    data = {
        "transactions": [
            {"transaction_date": "2024-01-01", "amount_original": 100},
            {"transaction_date": None, "amount_original": None},
        ]
    }
    issues = run_dq_checks(data)
    assert len(issues) == 2
    assert any(i.rule == "missing_date" for i in issues)
    assert any(i.rule == "missing_amount" for i in issues)


def test_dq_detects_negative_revenue():
    data = {
        "deals": [
            {"deal_date": "2024-01-01", "amount_original": -100},
        ]
    }
    issues = run_dq_checks(data)
    assert len(issues) == 1
    assert issues[0].rule == "negative_revenue"
    assert issues[0].source == "amocrm"


def test_dq_ignores_negative_expense_amounts_as_revenue():
    data = {
        "expenses": [
            {"expense_date": "2024-01-01", "amount_original": -100},
        ]
    }
    issues = run_dq_checks(data)
    assert len(issues) == 1
    assert issues[0].rule == "negative_expense"


def test_dq_no_issues_on_valid_data():
    data = {
        "transactions": [{"transaction_date": "2024-01-01", "amount_original": 100}],
        "deals": [{"deal_date": "2024-01-01", "amount_original": 200}],
        "expenses": [{"expense_date": "2024-01-01", "amount_original": 50}],
    }
    issues = run_dq_checks(data)
    assert issues == []
