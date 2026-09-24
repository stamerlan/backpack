#include <Python.h>
#include <exception>
#include <new>
#include <optional>
#include <string>
#include <utility>
#include <vector>
#include "defer_call.h"
#include "dialog.h"
#include "utf8.h"
#include "window.h"
#include "py/invoke.h"
#include "py/keep.h"

struct WindowObject {
	PyObject_HEAD
	window_t *window;
};

/* Turn a Python iterable of (name, spec) str tuples into dialog filters.
 * Returns std::nullopt with a Python error set on failure.
 */
static std::optional<dialog::filters_t> parse_filters(PyObject *obj) noexcept
{
	PyObject *seq = PySequence_Fast(obj, "filters must be a sequence");
	if (!seq)
		return std::nullopt;

	try {
		dialog::filters_t filters;
		Py_ssize_t n = PySequence_Fast_GET_SIZE(seq);
		for (Py_ssize_t i = 0; i < n; ++i) {
			PyObject *item = PySequence_Fast_GET_ITEM(seq, i);
			const char *name;
			const char *spec;
			if (!PyArg_ParseTuple(item, "ss", &name, &spec)) {
				Py_DECREF(seq);
				return std::nullopt;
			}
			filters.emplace_back(
				utf8_to_wstr(name), utf8_to_wstr(spec));
		}
		Py_DECREF(seq);
		return filters;
	} catch (const std::bad_alloc&) {
		PyErr_NoMemory();
	} catch (const std::exception& e) {
		PyErr_SetString(PyExc_RuntimeError, e.what());
	} catch (...) {
		PyErr_SetString(PyExc_RuntimeError, "failed to parse filters");
	}
	Py_DECREF(seq);
	return std::nullopt;
}

/* Call py_cb with (hresult, paths). hresult is E_ABORT when aborted on shutdown
 * and HRESULT_FROM_WIN32(ERROR_CANCELLED) when dismissed.
 */
static void call_dialog_cb(PyObject *py_cb, const dialog::result_t& result)
{
	PyGILState_STATE gil = PyGILState_Ensure();
	PyObject *paths = PyList_New(0);
	if (paths && result) {
		for (const auto& p : *result) {
			std::string u = wstr_to_utf8(p);
			PyObject *s = PyUnicode_FromStringAndSize(
				u.data(), static_cast<Py_ssize_t>(u.size()));
			if (s) {
				PyList_Append(paths, s);
				Py_DECREF(s);
			}
		}
	}
	if (paths) {
		HRESULT hr = result ? S_OK : result.error();
		PyObject *args = Py_BuildValue("(kN)",
			static_cast<unsigned long>(hr), paths);
		py::invoke(py_cb, args);
	} else {
		PyErr_WriteUnraisable(py_cb);
	}
	PyGILState_Release(gil);
}

/* Show dialog modally on the window's UI thread and call py_cb with its result.
 */
static void show_dialog(PyObject *self, dialog::show_t show, PyObject *py_cb)
{
	HWND hwnd = reinterpret_cast<WindowObject *>(self)->window->hwnd();
	std::shared_ptr<PyObject> py_cb_ref = py::keep(py_cb);

	try {
		defer_call(hwnd,
			[hwnd, show = std::move(show), py_cb_ref](void) {
				call_dialog_cb(py_cb_ref.get(), show(hwnd));
			}
		);
	} catch (...) {
		/* the post failed (window gone); teardown is under way */
		call_dialog_cb(py_cb, std::unexpected(E_ABORT));
	}
}

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
		defer_call(w->hwnd(),
			[w, wmode = utf8_to_wstr(mode)](void) mutable {
				w->set_theme(std::move(wmode));
			}
		);
	} catch (...) {
		/* the post failed (window gone); teardown is under way */
	}
	Py_RETURN_NONE;
}

static PyObject *py_show_open_dialog(PyObject *self, PyObject *args)
{
	int multiple;
	PyObject *py_filters;
	PyObject *py_cb;
	if (!PyArg_ParseTuple(args, "pOO:show_open_dialog",
			&multiple, &py_filters, &py_cb))
		return nullptr;
	if (!PyCallable_Check(py_cb)) {
		PyErr_SetString(PyExc_TypeError, "cb must be callable");
		return nullptr;
	}
	auto filters = parse_filters(py_filters);
	if (!filters)
		return nullptr;

	try {
		dialog::show_t show = dialog::open(multiple != 0,
			std::move(*filters));
		show_dialog(self, std::move(show), py_cb);
	} catch (...) {
		call_dialog_cb(py_cb, std::unexpected(E_FAIL));
	}
	Py_RETURN_NONE;
}

static PyObject *py_show_save_dialog(PyObject *self, PyObject *args)
{
	const char *filename;
	PyObject *py_filters;
	PyObject *py_cb;
	if (!PyArg_ParseTuple(args, "sOO:show_save_dialog",
			&filename, &py_filters, &py_cb))
		return nullptr;
	if (!PyCallable_Check(py_cb)) {
		PyErr_SetString(PyExc_TypeError, "cb must be callable");
		return nullptr;
	}
	auto filters = parse_filters(py_filters);
	if (!filters)
		return nullptr;

	try {
		dialog::show_t show = dialog::save(utf8_to_wstr(filename),
			std::move(*filters));
		show_dialog(self, std::move(show), py_cb);
	} catch (...) {
		call_dialog_cb(py_cb, std::unexpected(E_FAIL));
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
	{
		"show_open_dialog", py_show_open_dialog, METH_VARARGS,
		PyDoc_STR("show_open_dialog(multiple, filters, cb) -> None")
	},
	{
		"show_save_dialog", py_show_save_dialog, METH_VARARGS,
		PyDoc_STR("show_save_dialog(filename, filters, cb) -> None")
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

PyObject *window_t::to_py(void)
{
	if (PyType_Ready(&WindowType) < 0)
		return nullptr;
	WindowObject *o = PyObject_New(WindowObject, &WindowType);
	if (!o)
		return nullptr;
	o->window = this;
	return reinterpret_cast<PyObject *>(o);
}
