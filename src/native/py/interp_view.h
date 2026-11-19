#ifndef PY_INTERP_VIEW_H
#define PY_INTERP_VIEW_H

#include <Python.h>

namespace py {

/* Attach a thread state to the main interpreter for the guard's lifetime.
 *
 * Unlike PyGILState_Ensure, which hangs or crashes once the interpreter is
 * finalizing or gone, the attach then fails and the guard tests false: the
 * caller must skip any Python work. Nesting is allowed and an already attached
 * thread state is reused.
 */
class interp_view_t {
public:
	interp_view_t(void)
	{
		PyInterpreterView *view = PyInterpreterView_FromMain();
		if (!view)
			return;
		/* the token holds its own guard; the view can go */
		token = PyThreadState_EnsureFromView(view);
		PyInterpreterView_Close(view);
	}
	~interp_view_t(void)
	{
		if (token)
			PyThreadState_Release(token);
	}

	interp_view_t(const interp_view_t&) = delete;
	interp_view_t &operator=(const interp_view_t&) = delete;

	explicit operator bool(void) const noexcept
	{
		return token != nullptr;
	}

private:
	PyThreadStateToken *token = nullptr;
};

} /* namespace py */

#endif /* PY_INTERP_VIEW_H */
