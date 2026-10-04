# -*- coding: utf-8 -*-
"""Keep pluginmanager importable regardless of the installed setuptools.

pluginmanager (unmaintained, last release 2016) does `import pkg_resources`
at import time for its entry-point manager. setuptools deprecated that module
and removed it in 82.0.0, so a plain `pip install -U setuptools` used to stop
Jarvis starting at all.

Jarvis never loads plugins from entry points, so all pluginmanager needs is
something importable under that name. This module:

  * silences the deprecation warning when the real pkg_resources exists, and
  * otherwise registers a minimal stand-in backed by importlib.metadata.

Import it before the first `import pluginmanager`. Importing it twice is a
no-op.
"""
import sys
import warnings


def _install_shim():
    import types
    from importlib import metadata

    def iter_entry_points(group, name=None):
        eps = metadata.entry_points()
        selected = eps.select(group=group) if hasattr(eps, 'select') \
            else eps.get(group, [])
        for ep in selected:
            if name is None or ep.name == name:
                yield ep

    shim = types.ModuleType('pkg_resources')
    shim.__doc__ = 'Minimal pkg_resources stand-in (see pkg_resources_compat).'
    shim.iter_entry_points = iter_entry_points
    sys.modules['pkg_resources'] = shim


if 'pkg_resources' not in sys.modules:
    with warnings.catch_warnings():
        warnings.filterwarnings('ignore', message='pkg_resources is deprecated')
        try:
            import pkg_resources  # noqa: F401
        except ImportError:
            _install_shim()
