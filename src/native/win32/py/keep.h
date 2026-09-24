#ifndef PY_KEEP_H
#define PY_KEEP_H

#include <Python.h>
#include <memory>

namespace py {

/* Keep a Python object alive across the C++/Python boundary.
 *
 * A shared_ptr with a GIL-taking deleter lets the std::function copy freely
 * without touching the reference count and releases the one strong reference
 * under the GIL whenever the last copy dies.
 */
inline std::shared_ptr<PyObject> keep(PyObject *o)
{
	Py_XINCREF(o);
	return std::shared_ptr<PyObject>(o, [](PyObject *p) {
		if (!p)
			return;
		PyGILState_STATE gil = PyGILState_Ensure();
		Py_DECREF(p);
		PyGILState_Release(gil);
	});
}

} /* namespace py */

#endif /* PY_KEEP_H */
