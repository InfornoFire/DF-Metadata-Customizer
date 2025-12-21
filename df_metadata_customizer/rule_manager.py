""" "Rule management for metadata customization."""

import re
import warnings
from functools import cmp_to_key

from df_metadata_customizer.widgets import SortRuleRow


class RuleManager:
    """Utility class for managing and applying metadata rules."""

    @staticmethod
    def group_rules_by_logic(rules: list[dict[str, str]]) -> list[list[dict]]:
        """Group rules into logical blocks based on AND/OR operators."""
        if not rules:
            return []

        blocks = []
        current_block = []

        for i, rule in enumerate(rules):
            if i == 0:
                current_block.append(rule)
                continue
            logic = rule.get("logic", "AND")
            if logic == "AND":
                current_block.append(rule)
            else:
                if current_block:
                    blocks.append(current_block)
                current_block = [rule]
        if current_block:
            blocks.append(current_block)
        return blocks

    @staticmethod
    def eval_rule_block(
        rule_block: list[dict[str, str]],
        fv: dict[str, str],
        latest_versions: dict | None = None,
    ) -> bool:
        """Evaluate a block of rules with AND logic (all rules in block must match)."""
        if not rule_block:
            return False
        return all(RuleManager.eval_single_rule(rule, fv, latest_versions) for rule in rule_block)

    @staticmethod
    def eval_single_rule(rule: dict[str, str], fv: dict[str, str], latest_versions: dict | None = None) -> bool:
        """Evaluate a single rule."""
        field = rule.get("if_field", "")
        op = rule.get("if_operator", "")
        val = rule.get("if_value", "")
        actual = str(fv.get(field, ""))

        if op == "is":
            return actual == val
        if op == "contains":
            return val in actual
        if op == "starts with":
            return actual.startswith(val)
        if op == "ends with":
            return actual.endswith(val)
        if op == "is empty":
            return actual == ""
        if op == "is not empty":
            return actual != ""
        if op == "is latest version":
            title = fv.get("Title", "")
            artist = fv.get("Artist", "")
            coverartist = fv.get("CoverArtist", "")
            version = fv.get("Version", "0")
            return RuleManager.is_latest_version_full(title, artist, coverartist, version, latest_versions)
        if op == "is not latest version":
            title = fv.get("Title", "")
            artist = fv.get("Artist", "")
            coverartist = fv.get("CoverArtist", "")
            version = fv.get("Version", "0")
            return not RuleManager.is_latest_version_full(title, artist, coverartist, version, latest_versions)
        return False

    @staticmethod
    def is_latest_version(title: str, version: str, latest_versions: dict | None = None) -> bool:
        """Check if the given title and version is the latest version."""
        warnings.warn(
            "is_latest_version is deprecated, use is_latest_version_full instead",
            DeprecationWarning,
            stacklevel=2,
        )

        if not latest_versions:
            return True

        # Find the song key for this title (we need to search since we don't have artist/coverartist here)
        for song_key, latest_version in latest_versions.items():
            if title in song_key:  # Simple matching - could be improved
                return latest_version == version
        return True

    @staticmethod
    def is_latest_version_full(
        title: str,
        artist: str,
        coverartist: str,
        version: str,
        latest_versions: dict | None = None,
    ) -> bool:
        """Check if the given title, artist, coverartist, and version is the latest version."""
        if not latest_versions:
            return True
        song_key = f"{title}|{artist}|{coverartist}"
        return latest_versions.get(song_key, version) == version

    @staticmethod
    def apply_template(template: str, fv: dict[str, str]) -> str:
        """Apply template with field values."""
        if not template:
            return ""
        try:
            result = template
            for k, v in fv.items():
                placeholder = "{" + k + "}"
                if placeholder in result:
                    safe_value = str(v) if v is not None else ""
                    result = result.replace(placeholder, safe_value)
            # Also handle common field names
            common_fields = {
                "Title": fv.get("Title", ""),
                "Artist": fv.get("Artist", ""),
                "CoverArtist": fv.get("CoverArtist", ""),
                "Version": fv.get("Version", ""),
                "Discnumber": fv.get("Discnumber", ""),
                "Track": fv.get("Track", ""),
                "Date": fv.get("Date", ""),
                "Comment": fv.get("Comment", ""),
                "Special": fv.get("Special", ""),
            }
            for field_name, field_value in common_fields.items():
                placeholder = "{" + field_name + "}"
                if placeholder in result:
                    safe_value = str(field_value) if field_value is not None else ""
                    result = result.replace(placeholder, safe_value)
        except Exception:
            return ""
        return result

    @staticmethod
    def apply_rules_list(rules: list[dict[str, str]], fv: dict[str, str], latest_versions: dict | None = None) -> str:
        """Apply rules list to field values with AND/OR grouping."""
        if not rules:
            return ""
        rule_blocks = RuleManager.group_rules_by_logic(rules)
        for block in rule_blocks:
            if RuleManager.eval_rule_block(block, fv, latest_versions):
                template = block[-1].get("then_template", "")
                result = RuleManager.apply_template(template, fv)
                if result.strip():
                    return result
        return ""

    @staticmethod
    def get_sort_rules(sort_rules: list[SortRuleRow]) -> list[dict]:
        """Get list of sort rules as dictionaries."""
        return [rule.get_sort_rule() for rule in sort_rules]

    @staticmethod
    def apply_multi_sort(sort_rules: list[SortRuleRow], file_data: dict) -> dict | list:
        """Apply multiple sort rules to file data (positional tuple items).

        This uses a comparator-based approach so each rule's ascending/descending
        direction is respected at every level, not just the primary key.
        """
        warnings.warn(
            "apply_multi_sort is deprecated, use apply_multi_sort_with_dict instead",
            DeprecationWarning,
            stacklevel=2,
        )

        rules = RuleManager.get_sort_rules(sort_rules)

        if not rules:
            return file_data

        # Map field name to positional index in the tuple (item[0] is original index)
        field_names = [
            "title",
            "artist",
            "coverartist",
            "version",
            "disc",
            "track",
            "date",
            "comment",
            "special",
            "file",
        ]

        def parse_version(v: object) -> tuple:
            nums = re.findall(r"\d+", str(v))
            nums = tuple(int(n) for n in nums) if nums else (0,)
            return nums + (0,) * (3 - len(nums)) if len(nums) < 3 else nums

        def get_field_value_from_item(item: tuple[int, object], field: str):
            _, *values = item
            try:
                idx = field_names.index(field)
                raw = values[idx]
            except ValueError:
                raw = ""

            if field in ["disc", "track", "special"]:
                try:
                    return int(raw) if raw else 0
                except (ValueError, TypeError):
                    return 0
            if field == "version":
                try:
                    return parse_version(raw)
                except Exception:
                    return (0, 0, 0)
            # Fallback to case-insensitive string compare
            return str(raw).lower()

        def compare(a: tuple[int, object], b: tuple[int, object]) -> int:
            for rule in rules:
                field = rule["field"]
                order = rule["order"]

                v1 = get_field_value_from_item(a, field)
                v2 = get_field_value_from_item(b, field)

                if v1 < v2:
                    return -1 if order == "asc" else 1
                if v1 > v2:
                    return 1 if order == "asc" else -1
            # Stable tie-breaker by original index
            return a[0] - b[0]

        # Sort the data
        try:
            sorted_data = sorted(file_data, key=cmp_to_key(compare))
        except Exception as e:
            print(f"Sorting error: {e}")
            return file_data

        return sorted_data

    @staticmethod
    def apply_multi_sort_with_dict(sort_rules: list[SortRuleRow], file_data: dict) -> dict:
        """Apply multiple sort rules to file data stored as dictionaries.

        Uses a comparator so each rule's direction is applied at its level.
        """
        rules = RuleManager.get_sort_rules(sort_rules)

        if not rules:
            return file_data

        def parse_version(v: object) -> tuple:
            nums = re.findall(r"\d+", str(v))
            nums = tuple(int(n) for n in nums) if nums else (0,)
            return nums + (0,) * (3 - len(nums)) if len(nums) < 3 else nums

        def get_field_value(field_values: dict, field: str):
            raw = field_values.get(field, "")

            if field in ["disc", "track", "special"]:
                try:
                    return int(raw) if raw else 0
                except (ValueError, TypeError):
                    return 0
            if field == "version":
                try:
                    return parse_version(raw)
                except Exception:
                    return (0, 0, 0)
            return str(raw).lower()

        def compare(a: tuple[int, dict], b: tuple[int, dict]) -> int:
            _ia, va = a
            _ib, vb = b
            for rule in rules:
                field = rule["field"]
                order = rule["order"]

                v1 = get_field_value(va, field)
                v2 = get_field_value(vb, field)

                if v1 < v2:
                    return -1 if order == "asc" else 1
                if v1 > v2:
                    return 1 if order == "asc" else -1
            # Stable tie-breaker by original index
            return _ia - _ib

        # Sort the data
        try:
            sorted_data = sorted(file_data, key=cmp_to_key(compare))
        except Exception as e:
            print(f"Sorting error: {e}")
            return file_data

        return sorted_data
