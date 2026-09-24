#include "object.h"
#include <string>
#include <defer_call.h>
#include <utf8.h>
#include <window.h>

struct WindowObject {
	PyObject_HEAD
	window_t *window;
};

static PyObject *py_set_title(PyObject *self, PyObject *args)
{
	const char *title;
	if (!PyArg_ParseTuple(args, "s:set_title", &title))
		return nullptr;
	window_t *w = reinterpret_cast<WindowObject *>(self)->window;
	try {
		defer_call(w->hwnd(), [w, wtitle = utf8_to_wstr(title)](void) {
			w->set_title(wtitle);
		});
	} catch (...) {
		/* the post failed (window gone); teardown is under way */
	}
	Py_RETURN_NONE;
}

static PyObject *py_hide(PyObject *self, PyObject *)
{
	window_t *w = reinterpret_cast<WindowObject *>(self)->window;
	try {
		defer_call(w->hwnd(), [w](void) { w->hide(); });
	} catch (...) {
		/* the post failed (window gone); teardown is under way */
	}
	Py_RETURN_NONE;
}

static PyObject *py_set_theme(PyObject *self, PyObject *args)
{
	const char *mode;
	if (!PyArg_ParseTuple(args, "s:set_theme", &mode))
		return nullptr;
	window_t *w = reinterpret_cast<WindowObject *>(self)->window;
	try {
		defer_call(w->hwnd(), [w, wmode = utf8_to_wstr(mode)](void) {
			w->set_theme(wmode);
		});
	} catch (...) {
		/* the post failed (window gone); teardown is under way */
	}
	Py_RETURN_NONE;
}

static PyMethodDef window_methods[] = {
	{
		"set_title", py_set_title, METH_VARARGS,
		PyDoc_STR("set_title(title) -> None")
	},
	{ "hide", py_hide, METH_NOARGS, PyDoc_STR("hide() -> None") },
	{
		"set_theme", py_set_theme, METH_VARARGS,
		PyDoc_STR("set_theme(mode) -> None")
	},
	{ nullptr, nullptr, 0, nullptr },
};

static PyTypeObject WindowType = {
	.ob_base = PyVarObject_HEAD_INIT(nullptr, 0)
	.tp_name = "native.win32.Window",
	.tp_basicsize = sizeof(WindowObject),
	.tp_flags = Py_TPFLAGS_DEFAULT,
	.tp_doc = PyDoc_STR("Native window"),
	.tp_methods = window_methods,
};

PyObject *py::to_object(window_t& window)
{
	if (PyType_Ready(&WindowType) < 0)
		return nullptr;
	WindowObject *o = PyObject_New(WindowObject, &WindowType);
	if (!o)
		return nullptr;
	o->window = &window;
	return reinterpret_cast<PyObject *>(o);
}
