# Copyright 2026 Marimo. All rights reserved.
from __future__ import annotations

from types import ModuleType
from typing import TYPE_CHECKING, Any, Union

from marimo._messaging.notification import VariableValue
from marimo._plugins.ui._impl.tables.utils import get_table_manager_or_none

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence


def get_variable_preview(
    obj: Any,
    max_items: int = 5,
    max_str_len: int = 50,
    max_bytes: int = 32,
    _depth: int = 0,
    _seen: set[int] | None = None,
) -> str:
    """
    Generate a preview string for any Python object.

    Args:
        obj: Any Python object
        max_items: Maximum number of items to show for sequences/mappings
        max_str_len: Maximum length for string previews
        max_bytes: Maximum number of bytes to show for binary data
        _depth: Internal parameter to track recursion depth
        _seen: Set to track circular references

    Returns:
        str: A preview string
    """
    if _seen is None:
        _seen = set()

    # Check for circular references
    obj_id = id(obj)
    if obj_id in _seen:
        return f"<circular reference: {type(obj).__name__}>"

    # Track mutable objects that could be circular
    if isinstance(obj, (list, dict, set, tuple)):
        _seen.add(obj_id)

    # Add max recursion depth
    MAX_DEPTH = 5
    if _depth > MAX_DEPTH:
        return f"<max depth reached: {type(obj).__name__}>"

    def truncate_str(s: str, max_len: int) -> str:
        return s if len(s) <= max_len else s[:max_len]

    def preview_sequence(
        seq: Union[Sequence[Any], set[Any], frozenset[Any]],
    ) -> str:
        # Convert set-like objects to list for indexing
        if isinstance(seq, (set, frozenset)):
            seq = list(seq)

        length = len(seq)
        if length <= max_items:
            items = [
                get_variable_preview(
                    x, max_items // 2, _depth=_depth + 1, _seen=_seen
                )
                for x in seq
            ]
        else:
            half = max_items // 2
            first = [
                get_variable_preview(
                    x, max_items // 2, _depth=_depth + 1, _seen=_seen
                )
                for x in seq[:half]
            ]
            last = [
                get_variable_preview(
                    x, max_items // 2, _depth=_depth + 1, _seen=_seen
                )
                for x in seq[-half:]
            ]
            items = first + ["..."] + last
        return f"[{', '.join(items)}]"

    def preview_mapping(d: Mapping[Any, Any]) -> str:
        length = len(d)
        if length <= max_items:
            items = [
                f"{get_variable_preview(k, max_items // 2, _depth=_depth + 1, _seen=_seen)}: {get_variable_preview(v, max_items // 2, _depth=_depth + 1, _seen=_seen)}"
                for k, v in d.items()
            ]
        else:
            half = max_items // 2
            items = (
                [
                    f"{get_variable_preview(k, max_items // 2, _depth=_depth + 1, _seen=_seen)}: {get_variable_preview(v, max_items // 2, _depth=_depth + 1, _seen=_seen)}"
                    for k, v in list(d.items())[:half]
                ]
                + ["..."]
                + [
                    f"{get_variable_preview(k, max_items // 2, _depth=_depth + 1, _seen=_seen)}: {get_variable_preview(v, max_items // 2, _depth=_depth + 1, _seen=_seen)}"
                    for k, v in list(d.items())[-half:]
                ]
            )
        return f"{{{', '.join(items)}}}"

    def preview_bytes(data: bytes | bytearray) -> str:
        length = len(data)
        if length <= max_bytes:
            preview = data.hex()
        else:
            half = max_bytes // 2
            preview = f"{data[:half].hex()}...{data[-half:].hex()}"
        return f"<{length} bytes: {preview}>"

    # Get type name
    type_name = type(obj).__name__

    try:
        # Handle None
        if obj is None:
            return "None"

        # Handle basic types
        elif isinstance(obj, (bool, int, float, complex)):
            return str(obj)

        # Handle strings
        elif isinstance(obj, str):
            return f"'{truncate_str(obj, max_str_len)}'"

        # Handle bytes and bytearray
        elif isinstance(obj, (bytes, bytearray)):
            return f"{type_name}{preview_bytes(obj)}"

        # Handle lists, tuples, sets
        elif isinstance(obj, (list, tuple, set, frozenset)):
            preview = preview_sequence(obj)
            if isinstance(obj, (set, frozenset)):
                preview = f"{{{preview[1:-1]}}}"
            elif isinstance(obj, tuple):
                preview = f"({preview[1:-1]})"
            return preview

        # Handle dictionaries
        elif isinstance(obj, dict):
            return preview_mapping(obj)

        # Handle dataframes
        table_manager = get_table_manager_or_none(obj)
        if table_manager is not None:
            return str(table_manager)

        # Handle common standard library types
        elif hasattr(obj, "__dict__"):
            return f"<{type_name} object at {hex(id(obj))}>"

        # Fallback for other types
        else:
            try:
                preview = str(obj)
                return truncate_str(preview, max_str_len)
            except Exception:
                return f"<unprintable {type_name} object>"

    except Exception as e:
        return f"<error previewing {type_name}: {str(e)}>"


def _stringify_variable_value(value: object) -> str:
    """Convert a value to its string representation.

    Limits string length and handles objects that may have expensive __str__.
    """
    MAX_STR_LEN = 50

    if isinstance(value, str):
        if len(value) > MAX_STR_LEN:
            return value[:MAX_STR_LEN]
        return value

    try:
        # str(value) can be slow for large objects
        # or lead to large memory spikes
        return get_variable_preview(value, max_str_len=MAX_STR_LEN)
    except BaseException:
        # Catch-all: some libraries like Polars have bugs and raise
        # BaseExceptions, which shouldn't crash the kernel
        return "<UNKNOWN>"


def _format_variable_value(value: object) -> str:
    """Format a variable value for display.

    Handles special types like UIElement, Html, and ModuleType.
    """

    from marimo._output.hypertext import Html
    from marimo._plugins.ui._core.ui_element import UIElement

    resolved = value
    if isinstance(value, UIElement):
        resolved = value.value
    elif isinstance(value, Html):
        resolved = value.text
    elif isinstance(value, ModuleType):
        resolved = value.__name__
    return _stringify_variable_value(resolved)


def _safe_repr(obj: object, max_len: int = 100) -> str:
    """Truncated repr for sample items. Handles broken __repr__."""
    try:
        r = repr(obj)
        if len(r) > max_len:
            return r[:max_len]
        return r
    except Exception:
        return f"<{type(obj).__name__}>"


def _compute_dataframe_meta(obj: Any) -> dict[str, Any] | None:
    """Compute structured metadata for a DataFrame (pandas or polars)."""
    module = type(obj).__module__ or ""
    meta: dict[str, Any] = {"type": "dataframe"}

    try:
        if module.startswith("pandas"):
            meta["shape"] = list(obj.shape)
            meta["columns"] = [
                {"name": str(c), "dtype": str(obj[c].dtype)}
                for c in obj.columns
            ]
            try:
                null_counts = obj.isnull().sum()
                meta["null_counts"] = {
                    str(k): int(v) for k, v in null_counts.items() if v > 0
                }
            except Exception:
                pass
            try:
                head = obj.head(10)
                rows: list[dict[str, Any]] = []
                for record in head.to_dict(orient="records"):
                    rows.append(
                        {str(k): _safe_repr(v) for k, v in record.items()}
                    )
                meta["head"] = rows
            except Exception:
                pass
            return meta

        elif module.startswith("polars"):
            meta["shape"] = list(obj.shape)
            meta["columns"] = [
                {"name": str(c), "dtype": str(obj[c].dtype)}
                for c in obj.columns
            ]
            try:
                null_row = obj.null_count().to_dicts()[0]
                meta["null_counts"] = {
                    str(k): int(v) for k, v in null_row.items() if v > 0
                }
            except Exception:
                pass
            try:
                head = obj.head(10).to_dicts()
                meta["head"] = [
                    {str(k): _safe_repr(v) for k, v in row.items()}
                    for row in head
                ]
            except Exception:
                pass
            return meta

    except Exception:
        pass

    # Fallback: use table manager for shape info only
    manager = get_table_manager_or_none(obj)
    if manager is not None:
        meta["shape"] = [
            manager.get_num_rows(force=False),
            manager.get_num_columns(),
        ]
        meta["columns"] = [
            {"name": name, "dtype": ext_type}
            for name, (_, ext_type) in zip(
                [n for n, _ in manager.get_field_types()],
                manager.get_field_types(),
            )
        ]
        return meta

    return None


def _compute_variable_meta(value: object) -> dict[str, Any] | None:
    """Compute structured metadata for a variable.

    Returns type-specific metadata dict, or None for simple/small types.
    Runs in the kernel process with access to the actual Python object.
    """
    if value is None or isinstance(value, (bool, int, float, complex)):
        return None

    if isinstance(value, str):
        if len(value) > 200:
            return {"type": "str", "length": len(value), "truncated": True}
        return None

    if isinstance(value, (bytes, bytearray)):
        length = len(value)
        if length > 100:
            return {
                "type": "bytes",
                "length": length,
                "masked": True,
                "preview": value[:20].hex(),
            }
        return {"type": "bytes", "length": length, "masked": False}

    if isinstance(value, list):
        return {
            "type": "list",
            "length": len(value),
            "sample": [_safe_repr(item) for item in value[:10]],
        }

    if isinstance(value, tuple):
        return {
            "type": "tuple",
            "length": len(value),
            "sample": [_safe_repr(item) for item in value[:10]],
        }

    if isinstance(value, dict):
        keys = list(value.keys())[:10]
        return {
            "type": "dict",
            "length": len(value),
            "keys_sample": [_safe_repr(k) for k in keys],
            "values_sample": [_safe_repr(value[k]) for k in keys],
        }

    if isinstance(value, (set, frozenset)):
        sample = []
        for i, item in enumerate(value):
            if i >= 10:
                break
            sample.append(_safe_repr(item))
        return {
            "type": "set",
            "length": len(value),
            "sample": sample,
        }

    # numpy array
    try:
        import numpy as np

        if isinstance(value, np.ndarray):
            meta: dict[str, Any] = {
                "type": "ndarray",
                "shape": list(value.shape),
                "dtype": str(value.dtype),
            }
            if np.issubdtype(value.dtype, np.number):
                try:
                    meta["stats"] = {
                        "min": _safe_repr(value.min()),
                        "max": _safe_repr(value.max()),
                        "mean": _safe_repr(value.mean()),
                    }
                except Exception:
                    pass
            meta["sample"] = [_safe_repr(x) for x in value.flat[:10]]
            return meta
    except ImportError:
        pass

    # DataFrame (pandas/polars/narwhals)
    manager = get_table_manager_or_none(value)
    if manager is not None:
        return _compute_dataframe_meta(value)

    return None


def create_variable_value(
    name: str, value: object, datatype: str | None = None
) -> VariableValue:
    """Factory function to create a VariableValue from an object.

    Args:
        name: Variable name
        value: Variable value (any Python object)
        datatype: Optional datatype override. If None, will be inferred.

    Returns:
        VariableValue with formatted value and datatype
    """
    # Defensively try-catch attribute accesses, which could raise exceptions
    # If datatype is already defined, don't try to infer it
    if datatype is None:
        try:
            computed_datatype = (
                type(value).__name__ if value is not None else None
            )
        except Exception:
            computed_datatype = datatype
    else:
        computed_datatype = datatype

    try:
        formatted_value = _format_variable_value(value)
    except Exception:
        formatted_value = None

    try:
        meta = _compute_variable_meta(value)
    except Exception:
        meta = None

    return VariableValue(
        name=name,
        value=formatted_value,
        datatype=computed_datatype,
        meta=meta,
    )
