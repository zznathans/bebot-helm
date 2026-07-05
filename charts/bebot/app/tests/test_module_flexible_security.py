from __future__ import annotations

from bebot.main_modules.flexible_security import FlexibleSecurity
from bebot.main_modules.tools import Tools


class SelectRouter:
    """Routes bot.db.select() calls to canned results based on SQL content,
    so the module's multi-query control flow can be exercised without a
    real database."""

    def __init__(self):
        self.join_rows: list = []
        self.group_rows: list = []
        self.rules_by_gid: dict[int, list] = {}
        self.whois_results: list = []  # queue, consumed one item per whois query
        self.calls: list[str] = []

    def __call__(self, sql, *a, **kw):
        self.calls.append(sql)
        if "t1.access_level" in sql:
            return self.group_rows
        if "FROM #___whois" in sql:
            return self.whois_results.pop(0) if self.whois_results else []
        if "WHERE gid = " in sql:
            gid = int(sql.split("WHERE gid = ")[1].split(" ")[0])
            return self.rules_by_gid.get(gid, [])
        if "field = 'join'" in sql:
            return self.join_rows
        return []


def make_module(bot, monkeypatch, router=None):
    Tools(bot)
    router = router if router is not None else SelectRouter()
    monkeypatch.setattr(bot.db, "select", router)
    module = FlexibleSecurity(bot)
    return module, router


# -- construction -------------------------------------------------------------

def test_creates_table_on_construction(bot, monkeypatch):
    module, router = make_module(bot, monkeypatch)
    create_queries = [q for q in bot.db.queries if "CREATE TABLE" in q]
    assert len(create_queries) == 1
    assert "security_flexible" in create_queries[0]


def test_registers_as_flexible_security_module(bot, monkeypatch):
    module, router = make_module(bot, monkeypatch)
    assert bot.core("flexible_security") is module


def test_disabled_by_default_when_no_join_rows(bot, monkeypatch):
    module, router = make_module(bot, monkeypatch)
    assert module.enabled is False


def test_enabled_when_join_rows_present(bot, monkeypatch):
    router = SelectRouter()
    router.join_rows = [(1, "join", "&&", "")]
    module, router = make_module(bot, monkeypatch, router)
    assert module.enabled is True


# -- flexible_group_access: disabled short-circuit -----------------------------

def test_disabled_returns_highest_unchanged_without_querying(bot, monkeypatch):
    module, router = make_module(bot, monkeypatch)
    router.calls.clear()
    result = module.flexible_group_access("SomePlayer", 5)
    assert result == 5
    assert router.calls == []  # no DB work done when disabled


# -- flexible_group_access: enabled, no matching groups ------------------------

def test_enabled_no_groups_returns_highest(bot, monkeypatch):
    router = SelectRouter()
    router.join_rows = [(1, "join", "&&", "")]
    module, router = make_module(bot, monkeypatch, router)
    result = module.flexible_group_access("SomePlayer", 5)
    assert result == 5
    assert "SomePlayer" not in module.cache


# -- flexible_group_access: AND group, match ------------------------------------

def test_and_group_match_returns_group_acl_and_caches(bot, monkeypatch):
    router = SelectRouter()
    router.join_rows = [(1, "join", "&&", "")]
    router.group_rows = [(1, 100, "&&")]
    router.rules_by_gid[1] = [("level", ">=", "200"), ("profession", "=", "Enforcer")]
    router.whois_results = [[("Player",)]]
    module, router = make_module(bot, monkeypatch, router)

    result = module.flexible_group_access("player", 50)

    assert result == 100
    assert module.cache["Player"] == 100
    whois_query = next(q for q in router.calls if "FROM #___whois" in q)
    assert "level >= '200'" in whois_query
    assert " AND " in whois_query
    assert "profession = 'Enforcer'" in whois_query
    assert "nickname = 'Player'" in whois_query


def test_or_group_uses_or_joiner(bot, monkeypatch):
    router = SelectRouter()
    router.join_rows = [(1, "join", "&&", "")]
    router.group_rows = [(2, 64, "||")]
    router.rules_by_gid[2] = [("level", ">=", "100"), ("level", "<", "200")]
    router.whois_results = [[("Player",)]]
    module, router = make_module(bot, monkeypatch, router)

    result = module.flexible_group_access("Player", 10)

    assert result == 64
    whois_query = next(q for q in router.calls if "FROM #___whois" in q)
    assert " OR " in whois_query


# -- flexible_group_access: no match falls through to highest -------------------

def test_no_whois_match_caches_and_returns_highest(bot, monkeypatch):
    router = SelectRouter()
    router.join_rows = [(1, "join", "&&", "")]
    router.group_rows = [(1, 100, "&&")]
    router.rules_by_gid[1] = [("level", ">=", "200")]
    router.whois_results = [[]]  # whois query returns no match
    module, router = make_module(bot, monkeypatch, router)

    result = module.flexible_group_access("Player", 50)

    assert result == 50
    assert module.cache["Player"] == 50


def test_multiple_groups_checked_in_order_second_group_matches(bot, monkeypatch):
    router = SelectRouter()
    router.join_rows = [(1, "join", "&&", "")]
    router.group_rows = [(1, 100, "&&"), (2, 80, "&&")]
    router.rules_by_gid[1] = [("level", ">=", "200")]
    router.rules_by_gid[2] = [("level", ">=", "50")]
    router.whois_results = [[], [("Player",)]]  # first group no match, second matches
    module, router = make_module(bot, monkeypatch, router)

    result = module.flexible_group_access("Player", 10)

    assert result == 80
    assert module.cache["Player"] == 80


def test_group_with_no_rules_is_skipped(bot, monkeypatch):
    router = SelectRouter()
    router.join_rows = [(1, "join", "&&", "")]
    router.group_rows = [(1, 100, "&&")]
    router.rules_by_gid[1] = []  # no non-join rules for this gid
    module, router = make_module(bot, monkeypatch, router)

    result = module.flexible_group_access("Player", 10)

    assert result == 10
    whois_queries = [q for q in router.calls if "FROM #___whois" in q]
    assert whois_queries == []


# -- faction "all" special-casing -----------------------------------------------

def test_faction_equals_all_builds_or_clause(bot, monkeypatch):
    router = SelectRouter()
    router.join_rows = [(1, "join", "&&", "")]
    router.group_rows = [(1, 100, "&&")]
    router.rules_by_gid[1] = [("faction", "=", "all")]
    router.whois_results = [[("Player",)]]
    module, router = make_module(bot, monkeypatch, router)

    module.flexible_group_access("Player", 10)

    whois_query = next(q for q in router.calls if "FROM #___whois" in q)
    assert "faction = 'omni'" in whois_query
    assert "faction = 'clan'" in whois_query
    assert "faction = 'neutral'" in whois_query
    assert " OR " in whois_query


def test_faction_not_equals_all_builds_and_clause(bot, monkeypatch):
    router = SelectRouter()
    router.join_rows = [(1, "join", "&&", "")]
    router.group_rows = [(1, 100, "&&")]
    router.rules_by_gid[1] = [("faction", "!=", "all")]
    router.whois_results = [[("Player",)]]
    module, router = make_module(bot, monkeypatch, router)

    module.flexible_group_access("Player", 10)

    whois_query = next(q for q in router.calls if "FROM #___whois" in q)
    assert "faction != 'omni'" in whois_query
    assert "faction != 'clan'" in whois_query
    assert "faction != 'neutral'" in whois_query
    assert " AND " in whois_query


# -- caching --------------------------------------------------------------------

def test_second_call_uses_cache_without_requerying_groups(bot, monkeypatch):
    router = SelectRouter()
    router.join_rows = [(1, "join", "&&", "")]
    router.group_rows = [(1, 100, "&&")]
    router.rules_by_gid[1] = [("level", ">=", "200")]
    router.whois_results = [[("Player",)]]
    module, router = make_module(bot, monkeypatch, router)

    first = module.flexible_group_access("Player", 10)
    calls_after_first = len(router.calls)
    second = module.flexible_group_access("player", 10)  # different case, sanitized to same key

    assert first == 100
    assert second == 100
    assert len(router.calls) == calls_after_first  # no additional queries, served from cache


def test_cached_value_lower_than_new_highest_returns_new_highest(bot, monkeypatch):
    router = SelectRouter()
    router.join_rows = [(1, "join", "&&", "")]
    module, router = make_module(bot, monkeypatch, router)
    module.cache["Player"] = 30

    result = module.flexible_group_access("Player", 200)

    assert result == 200


def test_player_name_is_sanitized_before_cache_lookup(bot, monkeypatch):
    router = SelectRouter()
    router.join_rows = [(1, "join", "&&", "")]
    module, router = make_module(bot, monkeypatch, router)
    module.cache["Weirdname"] = 77

    result = module.flexible_group_access("  weird!!name  ", 10)

    assert result == 77


# -- clear_cache / cron -----------------------------------------------------------

def test_clear_cache_empties_cache_and_rechecks_enable(bot, monkeypatch):
    router = SelectRouter()
    router.join_rows = [(1, "join", "&&", "")]
    module, router = make_module(bot, monkeypatch, router)
    module.cache["Player"] = 100
    router.join_rows = []  # simulate the last flexible group having been deleted

    module.clear_cache()

    assert module.cache == {}
    assert module.enabled is False


def test_cron_clears_cache(bot, monkeypatch):
    router = SelectRouter()
    router.join_rows = [(1, "join", "&&", "")]
    module, router = make_module(bot, monkeypatch, router)
    module.cache["Player"] = 100

    module.cron()

    assert module.cache == {}


# -- whois-module gap: dummy module fallback must not crash -----------------------

def test_missing_whois_module_does_not_crash_matching_lookup(bot, monkeypatch):
    # "whois" is never registered as a core module in this port (Core/Ao/Whois.php
    # isn't ported), so bot.core("whois") resolves to the DummyModule fallback.
    # Exercising a full match path must not raise even though .lookup() is called.
    router = SelectRouter()
    router.join_rows = [(1, "join", "&&", "")]
    router.group_rows = [(1, 100, "&&")]
    router.rules_by_gid[1] = [("level", ">=", "1")]
    router.whois_results = [[("Player",)]]
    module, router = make_module(bot, monkeypatch, router)

    result = module.flexible_group_access("Player", 0)

    assert result == 100
    assert not bot.exists_module("whois")
