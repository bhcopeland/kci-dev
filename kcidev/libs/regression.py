"""Pure regression classification and reporting.

This module deliberately has no Click or HTTP dependencies.  It can therefore
be used by the command line, the public Python client, and the MCP server.
"""

from collections import Counter, defaultdict
from dataclasses import dataclass, field

CATEGORIES = ("regression", "fixed", "unstable", "persistent_fail", "new", "missing")
FAIL_STATUSES = {"FAIL", "ERROR"}


def _value(item, *names, default="unknown"):
    for name in names:
        value = item.get(name)
        if value not in (None, ""):
            return value
    return default


def result_identity(item, kind="test"):
    """Return the complete, stable identity of a result (never its result id)."""
    environment = item.get("environment_misc") or {}
    return {
        "kind": kind,
        "origin": _value(item, "origin"),
        "platform": _value(
            item, "platform", "hardware", default=environment.get("platform", "unknown")
        ),
        "architecture": _value(item, "architecture", "arch"),
        "compiler": _value(item, "compiler"),
        "config": _value(item, "config", "config_name"),
        "path": _value(
            item, "path", "test_path", default="build" if kind == "build" else "unknown"
        ),
    }


def _key(item, kind):
    identity = result_identity(item, kind)
    # A tree report groups results by their execution identity, regardless of
    # whether the result came from a build, boot, or test endpoint.
    identity.pop("kind")
    return tuple(identity.values())


def _duplicate_sort_key(item):
    """Order otherwise-identical results before pairing them across revisions."""
    return (
        str(item.get("status") or "UNKNOWN").upper(),
        str(item.get("id") or ""),
    )


def _tree_report_keys(tree_report, category):
    keys = set()
    for platform, configs in (tree_report or {}).get(category, {}).items():
        for config, arch_compilers in configs.items():
            for arch_compiler, paths in arch_compilers.items():
                architecture, _, compiler = arch_compiler.partition("/")
                for path, tests in paths.items():
                    for test in tests or [{}]:
                        identity = result_identity(
                            {
                                **test,
                                "origin": (tree_report or {}).get("origin"),
                                "platform": platform,
                                "config": config,
                                "architecture": architecture,
                                "compiler": compiler,
                                "path": path,
                            },
                            "test",
                        )
                        identity.pop("kind")
                        keys.add(tuple(identity.values()))
    return keys


@dataclass
class RegressionReport:
    """A deterministic comparison report which preserves duplicate results."""

    base: str
    head: str
    items: list = field(default_factory=list)
    incomplete: bool = False

    @classmethod
    def compare(cls, base, head, base_results, head_results, tree_report=None):
        report = cls(base=base, head=head)
        history = {
            "regression": _tree_report_keys(tree_report, "possible_regressions"),
            "fixed": _tree_report_keys(tree_report, "fixed_regressions"),
            "unstable": _tree_report_keys(tree_report, "unstable_tests"),
        }
        for kind in ("build", "boot", "test"):
            old = defaultdict(list)
            new = defaultdict(list)
            for item in base_results.get(kind + "s", []):
                old[_key(item, kind)].append(item)
            for item in head_results.get(kind + "s", []):
                new[_key(item, kind)].append(item)
            for key in sorted(set(old) | set(new)):
                # The API does not guarantee result order.
                old[key].sort(key=_duplicate_sort_key)
                new[key].sort(key=_duplicate_sort_key)
                count = max(len(old[key]), len(new[key]))
                for occurrence in range(count):
                    before = (
                        old[key][occurrence] if occurrence < len(old[key]) else None
                    )
                    after = new[key][occurrence] if occurrence < len(new[key]) else None
                    category = cls._classify(before, after, key, history)
                    if category is None:
                        continue
                    chosen = after if after is not None else before
                    report.items.append(
                        {
                            "category": category,
                            "identity": result_identity(chosen, kind),
                            "occurrence": occurrence,
                            "base_status": before.get("status") if before else None,
                            "head_status": after.get("status") if after else None,
                            "base_id": before.get("id") if before else None,
                            "head_id": after.get("id") if after else None,
                            "known_issues": [],
                        }
                    )
        return report

    @staticmethod
    def _classify(before, after, key, history):
        if before is None:
            return "new"
        if after is None:
            return "missing"
        old = str(before.get("status") or "UNKNOWN").upper()
        new = str(after.get("status") or "UNKNOWN").upper()
        if key in history["unstable"]:
            return "unstable"
        if new in FAIL_STATUSES and (key in history["regression"] or old == "PASS"):
            return "regression"
        if new == "PASS" and (key in history["fixed"] or old in FAIL_STATUSES):
            return "fixed"
        if old in FAIL_STATUSES and new in FAIL_STATUSES:
            return "persistent_fail"
        if old != new:
            return "unstable"
        return None

    @property
    def counts(self):
        counts = Counter(item["category"] for item in self.items)
        return {category: counts[category] for category in CATEGORIES}

    def has_violation(self, fail_on="regression"):
        policies = {part.strip() for part in fail_on.split(",") if part.strip()}
        return any(self.counts.get(policy, 0) for policy in policies)

    def to_dict(self):
        return {
            "base": self.base,
            "head": self.head,
            "counts": self.counts,
            "incomplete": self.incomplete,
            "items": self.items,
        }
