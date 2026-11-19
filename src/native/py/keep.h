#ifndef PY_KEEP_H
#define PY_KEEP_H

#include <Python.h>
#include <memory>
#include "interp_view.h"

namespace py {

/* Keep a Python object alive across the C++/Python boundary.
 *
 * A shared_ptr with a GIL-taking deleter lets the std::function copy freely
 * without touching the reference count and releases the one strong reference
 * under the GIL whenever the last copy dies. A copy that outlives the
 * interpreter (held by WebView2 or app_t past Py_Finalize) leaks the reference
 * instead: the object went away with the interpreter.
 */
inline std::shared_ptr<PyObject> keep(PyObject *o)
{
	Py_XINCREF(o);
	return std::shared_ptr<PyObject>(o, [](PyObject *p) {
		if (!p)
			return;
		interp_view_t py;
		if (py)
			Py_DECREF(p);
	});
}

} /* namespace py */

#endif /* PY_KEEP_H */
