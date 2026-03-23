import importlib

import pytest


def test_get_query_found():
    import app.api.sql_store as sql_store
    importlib.reload(sql_store)

    query = sql_store.get_query("insert_job")
    assert "INSERT INTO public.opt_jobs" in query


def test_get_scenario_query_found():
    import app.api.sql_store as sql_store
    importlib.reload(sql_store)

    query = sql_store.get_query("select_scenario_product_params")
    assert "FROM public.opt_planning_scenarios" in query


def test_get_milp_scenario_query_found():
    import app.api.sql_store as sql_store
    importlib.reload(sql_store)

    query = sql_store.get_query("select_milp_scenario")
    assert "FROM public.opt_milp_scenarios" in query


def test_get_optimization_payload_query_found():
    import app.api.sql_store as sql_store
    importlib.reload(sql_store)

    query = sql_store.get_query("select_optimization_payload_by_scenario_latest")
    assert "FROM public.optimization_scenario" in query


def test_get_query_missing():
    import app.api.sql_store as sql_store
    importlib.reload(sql_store)

    with pytest.raises(FileNotFoundError):
        sql_store.get_query("missing_query")
