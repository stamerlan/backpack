#ifndef PY_INVOKE_H
#define PY_INVOKE_H

#include <Python.h>

namespace py {

/* Call callable with args, reporting any Python error as unraisable.
 * Args is stolen. The caller must hold the GIL.
 */
inline void invoke(PyObject *callable, PyObject *args)
{
	if (!args) {
		PyErr_WriteUnraisable(callable);
		return;
	}
	PyObject *r = PyObject_CallObject(callable, args);
	Py_DECREF(args);
	if (!r)
		PyErr_WriteUnraisable(callable);
	else
		Py_DECREF(r);
}

} /* namespace py */

#endif /* PY_INVOKE_H */
