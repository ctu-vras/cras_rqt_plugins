# SPDX-License-Identifier: BSD-3-Clause
# SPDX-FileCopyrightText: Czech Technical University in Prague

from typing import get_args, get_origin, TypeVar, Sequence


def resolve_subclass_args(cls: type, parent_type: type) -> Sequence[type | TypeVar]:
    """Resolve the type arguments of a subclass of a parent type.

    :param cls: Subclass of the parent type
    :param parent_type: Parent type
    :param type_vars: List of all TypeVars of the parent type and their names
    :return: Tuple of resolved arguments
    """
    # Build a map of TypeVar -> resolved argument as we walk the MRO
    type_map: dict[TypeVar, object] = {}
    for base_cls in cls.__mro__:
        for orig_base in getattr(base_cls, "__orig_bases__", ()):
            origin = get_origin(orig_base)
            args = get_args(orig_base)
            if origin is None or not args:
                continue

            # Substitute any TypeVars already resolved by subclasses
            resolved_args = tuple(type_map.get(a, a) for a in args)

            if origin is parent_type:
                return resolved_args

            # Map the origin's __type_params__ (PEP 695) to the resolved args
            params = getattr(origin, "__type_params__", ())
            for param, arg in zip(params, resolved_args):
                if isinstance(param, TypeVar):
                    type_map[param] = arg

    raise TypeError(f"Could not resolve Parent type arguments for {cls.__name__}")
