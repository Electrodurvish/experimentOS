import pytest

from apps.engine.evaluator import evaluate_rule


class TestEvaluateRule:
    def test_empty_rule_matches(self):
        assert evaluate_rule({}, {"user": {"country": "IN"}}) is True
        assert evaluate_rule(None, {}) is True

    def test_equals(self):
        rule = {"field": "user.country", "operator": "equals", "value": "IN"}
        assert evaluate_rule(rule, {"user": {"country": "IN"}}) is True
        assert evaluate_rule(rule, {"user": {"country": "US"}}) is False

    def test_not_equals(self):
        rule = {"field": "user.country", "operator": "not_equals", "value": "IN"}
        assert evaluate_rule(rule, {"user": {"country": "US"}}) is True
        assert evaluate_rule(rule, {"user": {"country": "IN"}}) is False

    def test_in_operator(self):
        rule = {"field": "user.country", "operator": "in", "values": ["IN", "US", "GB"]}
        assert evaluate_rule(rule, {"user": {"country": "IN"}}) is True
        assert evaluate_rule(rule, {"user": {"country": "FR"}}) is False

    def test_not_in_operator(self):
        rule = {"field": "user.country", "operator": "not_in", "values": ["IN", "US"]}
        assert evaluate_rule(rule, {"user": {"country": "FR"}}) is True
        assert evaluate_rule(rule, {"user": {"country": "IN"}}) is False

    def test_gt(self):
        rule = {"field": "user.age", "operator": "gt", "value": 18}
        assert evaluate_rule(rule, {"user": {"age": 25}}) is True
        assert evaluate_rule(rule, {"user": {"age": 18}}) is False
        assert evaluate_rule(rule, {"user": {"age": 10}}) is False

    def test_gte(self):
        rule = {"field": "user.age", "operator": "gte", "value": 18}
        assert evaluate_rule(rule, {"user": {"age": 18}}) is True
        assert evaluate_rule(rule, {"user": {"age": 17}}) is False

    def test_lt(self):
        rule = {"field": "user.age", "operator": "lt", "value": 18}
        assert evaluate_rule(rule, {"user": {"age": 10}}) is True
        assert evaluate_rule(rule, {"user": {"age": 18}}) is False

    def test_lte(self):
        rule = {"field": "user.age", "operator": "lte", "value": 18}
        assert evaluate_rule(rule, {"user": {"age": 18}}) is True
        assert evaluate_rule(rule, {"user": {"age": 19}}) is False

    def test_contains(self):
        rule = {"field": "user.email", "operator": "contains", "value": "@example.com"}
        assert evaluate_rule(rule, {"user": {"email": "test@example.com"}}) is True
        assert evaluate_rule(rule, {"user": {"email": "test@other.com"}}) is False

    def test_regex(self):
        rule = {"field": "user.email", "operator": "regex", "value": r".*@example\.com$"}
        assert evaluate_rule(rule, {"user": {"email": "test@example.com"}}) is True
        assert evaluate_rule(rule, {"user": {"email": "test@other.com"}}) is False

    def test_exists(self):
        rule = {"field": "user.premium", "operator": "exists", "value": True}
        assert evaluate_rule(rule, {"user": {"premium": True}}) is True
        assert evaluate_rule(rule, {"user": {}}) is False

        rule_not = {"field": "user.premium", "operator": "exists", "value": False}
        assert evaluate_rule(rule_not, {"user": {}}) is True
        assert evaluate_rule(rule_not, {"user": {"premium": True}}) is False

    def test_and_operator(self):
        rule = {
            "operator": "AND",
            "conditions": [
                {"field": "user.country", "operator": "equals", "value": "IN"},
                {"field": "user.platform", "operator": "equals", "value": "android"},
            ],
        }
        assert evaluate_rule(rule, {"user": {"country": "IN", "platform": "android"}}) is True
        assert evaluate_rule(rule, {"user": {"country": "IN", "platform": "ios"}}) is False
        assert evaluate_rule(rule, {"user": {"country": "US", "platform": "android"}}) is False

    def test_or_operator(self):
        rule = {
            "operator": "OR",
            "conditions": [
                {"field": "user.country", "operator": "equals", "value": "IN"},
                {"field": "user.country", "operator": "equals", "value": "US"},
            ],
        }
        assert evaluate_rule(rule, {"user": {"country": "IN"}}) is True
        assert evaluate_rule(rule, {"user": {"country": "US"}}) is True
        assert evaluate_rule(rule, {"user": {"country": "FR"}}) is False

    def test_not_operator(self):
        rule = {
            "operator": "NOT",
            "conditions": [
                {"field": "user.country", "operator": "equals", "value": "IN"},
            ],
        }
        assert evaluate_rule(rule, {"user": {"country": "US"}}) is True
        assert evaluate_rule(rule, {"user": {"country": "IN"}}) is False

    def test_nested_boolean(self):
        rule = {
            "operator": "AND",
            "conditions": [
                {
                    "operator": "OR",
                    "conditions": [
                        {"field": "user.country", "operator": "equals", "value": "IN"},
                        {"field": "user.country", "operator": "equals", "value": "US"},
                    ],
                },
                {"field": "user.platform", "operator": "equals", "value": "android"},
            ],
        }
        assert evaluate_rule(rule, {"user": {"country": "IN", "platform": "android"}}) is True
        assert evaluate_rule(rule, {"user": {"country": "US", "platform": "android"}}) is True
        assert evaluate_rule(rule, {"user": {"country": "IN", "platform": "ios"}}) is False
        assert evaluate_rule(rule, {"user": {"country": "FR", "platform": "android"}}) is False

    def test_missing_field_returns_false(self):
        rule = {"field": "user.country", "operator": "equals", "value": "IN"}
        assert evaluate_rule(rule, {}) is False
        assert evaluate_rule(rule, {"user": {}}) is False

    def test_missing_field_with_comparison_returns_false(self):
        rule = {"field": "user.age", "operator": "gt", "value": 18}
        assert evaluate_rule(rule, {"user": {}}) is False

    def test_unknown_operator_raises(self):
        rule = {"field": "user.x", "operator": "unknown_op", "value": 1}
        with pytest.raises(ValueError, match="Unknown leaf operator"):
            evaluate_rule(rule, {"user": {"x": 1}})

    def test_unknown_boolean_operator_raises(self):
        rule = {"operator": "XOR", "conditions": []}
        # Empty conditions returns True
        assert evaluate_rule(rule, {}) is True
        rule["conditions"] = [{"field": "x", "operator": "equals", "value": 1}]
        with pytest.raises(ValueError, match="Unknown boolean operator"):
            evaluate_rule(rule, {"x": 1})
