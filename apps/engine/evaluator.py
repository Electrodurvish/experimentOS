import re
from typing import Any

LEAF_OPERATORS = {
    "equals": lambda field_val, val: field_val == val,
    "not_equals": lambda field_val, val: field_val != val,
    "in": lambda field_val, val: field_val in val,
    "not_in": lambda field_val, val: field_val not in val,
    "gt": lambda field_val, val: field_val is not None and field_val > val,
    "gte": lambda field_val, val: field_val is not None and field_val >= val,
    "lt": lambda field_val, val: field_val is not None and field_val < val,
    "lte": lambda field_val, val: field_val is not None and field_val <= val,
    "contains": lambda field_val, val: field_val is not None and val in str(field_val),
    "regex": lambda field_val, val: field_val is not None and bool(re.match(val, str(field_val))),
    "exists": lambda field_val, val: (field_val is not None) if val else (field_val is None),
}


def evaluate_rule(rule: dict, context: dict[str, Any]) -> bool:
    """
    Recursively evaluate a targeting rule AST against a user context.

    Leaf nodes have a "field" key:
        {"field": "user.country", "operator": "equals", "value": "IN"}

    Boolean nodes have an "operator" and "conditions" list:
        {"operator": "AND", "conditions": [...]}

    Returns True if the user matches the targeting criteria.
    Returns True for empty/null rules (no targeting = all users match).
    """
    if not rule:
        return True

    if "field" in rule:
        return _evaluate_leaf(rule, context)

    operator = rule.get("operator", "").upper()
    conditions = rule.get("conditions", [])

    if not conditions:
        return True

    if operator == "AND":
        return all(evaluate_rule(c, context) for c in conditions)
    elif operator == "OR":
        return any(evaluate_rule(c, context) for c in conditions)
    elif operator == "NOT":
        return not evaluate_rule(conditions[0], context)
    else:
        raise ValueError(f"Unknown boolean operator: {operator}")


def _evaluate_leaf(rule: dict, context: dict[str, Any]) -> bool:
    """Evaluate a single leaf condition."""
    field_path = rule["field"]
    operator = rule["operator"]
    compare_value = rule.get("value", rule.get("values"))

    field_value = _resolve_field(field_path, context)

    operator_fn = LEAF_OPERATORS.get(operator)
    if operator_fn is None:
        raise ValueError(f"Unknown leaf operator: {operator}")

    try:
        return operator_fn(field_value, compare_value)
    except (TypeError, ValueError):
        return False


def _resolve_field(field_path: str, context: dict) -> Any:
    """Resolve a dotted field path from the context dict."""
    parts = field_path.split(".")
    value = context
    for part in parts:
        if isinstance(value, dict):
            value = value.get(part)
        else:
            return None
    return value
