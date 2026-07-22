"""v5 spec §6: 詞彙表常數（文件＋常數，零引擎）。"""
import option_chaser
from option_chaser import vocabulary as voc


def test_version():
    assert option_chaser.__version__ == "0.6.0"


def test_statuses():
    assert voc.SCENARIO_STATUSES == ("Active", "Reached", "Expired", "Invalidated")


def test_event_types_v5():
    assert voc.EVENT_TYPES_V5 == (
        "SCENARIO_CREATED", "STATUS_CHANGED", "ANALYSIS_COMPLETED",
        "GROUP_RELATION_CONFIRMED", "SCENARIO_DELETED")


def test_event_types_v7_reserved():
    assert voc.EVENT_TYPES_V7_RESERVED == (
        "PRICE_REACHED", "TARGET_DATE_ARRIVED", "EXPIRY_BUFFER_LOW",
        "LIQUIDITY_DEGRADED", "REANALYSIS_REQUESTED")
    assert voc.EVENT_TYPES == voc.EVENT_TYPES_V5 + voc.EVENT_TYPES_V7_RESERVED


def test_action_types():
    assert voc.ACTION_TYPES == (
        "HOLD", "OPEN", "ADD", "REDUCE", "CLOSE", "RECOVER_PRINCIPAL",
        "KEEP_RUNNER", "ROLL_TO_NEXT_MILESTONE", "SWITCH_SCENARIO",
        "HOLD_CASH", "RERUN_ANALYSIS")
    assert len(voc.ACTION_TYPES) == 11


def test_relation_choices():
    assert voc.RELATION_CHOICES == (
        "milestone-path", "independent", "exclusive", "undefined")


def test_all_tuples_of_str():
    for t in (voc.SCENARIO_STATUSES, voc.EVENT_TYPES, voc.ACTION_TYPES,
              voc.RELATION_CHOICES):
        assert isinstance(t, tuple) and all(isinstance(x, str) for x in t)
