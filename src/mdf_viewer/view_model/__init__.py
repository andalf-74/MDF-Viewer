"""View-model layer — bridge objects that touch both Model and View.

Objects here may reference Qt/PyQtGraph types (curves, ViewBoxes, colors) as
well as model data. This keeps the pure-data ``model`` package free of any UI
imports while still giving the controller a typed object to manage.
"""
