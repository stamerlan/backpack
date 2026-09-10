#include <Python.h>

#include <memory>
#include <string>
#include <string_view>
#include <vector>

#include "app.h"
#include "pyext.h"
#include "utf8.h"

/* The native host every primitive forwards to. Set by pyext_set_app() before
 * the interpreter starts, so it is non-null for the whole run.
 */
static app_t *g_app = nullptr;

void pyext_set_app(app_t *app)
{
	g_app = app;
}

namespace {

/* A Python callable held across the C++/Python boundary.
 *
 * The native bridges keep a callback until an event, script or dialog settles,
 * possibly on a UI or WebView2 thread. A shared_ptr with a GIL-taking deleter
 * lets the std::function copy freely without touching the reference count and
 * releases the one strong reference under the GIL whenever the last copy dies.
 */
using PyRef = std::shared_ptr<PyObject>;

PyRef py_keep(PyObject *cb)
{
	Py_XINCREF(cb);
	return PyRef(cb, [](PyObject *p) {
		if (!p)
			return;
		PyGILState_STATE gil = PyGILState_Ensure();
		Py_DECREF(p);
		PyGILState_Release(gil);
	});
}

/* Call cb with args, reporting any Python error as unraisable. Args is stolen.
 * The caller must hold the GIL.
 */
void invoke(PyObject *cb, PyObject *args)
{
	if (!args) {
		PyErr_WriteUnraisable(cb);
		return;
	}
	PyObject *r = PyObject_CallObject(cb, args);
	Py_DECREF(args);
	if (!r)
		PyErr_WriteUnraisable(cb);
	else
		Py_DECREF(r);
}

/* Turn a Python sequence of (name, spec) str pairs into dialog filters.
 * Returns false with a Python error set on a bad element.
 */
bool to_wfilters(PyObject *obj,
	std::vector<std::pair<std::wstring, std::wstring>>& out)
{
	PyObject *seq = PySequence_Fast(obj, "filters must be a sequence");
	if (!seq)
		return false;
	Py_ssize_t n = PySequence_Fast_GET_SIZE(seq);
	for (Py_ssize_t i = 0; i < n; ++i) {
		PyObject *item = PySequence_Fast_GET_ITEM(seq, i);
		const char *name;
		const char *spec;
		Py_ssize_t nlen = 0, slen = 0;
		if (!PyArg_ParseTuple(item, "s#s#", &name, &nlen, &spec, &slen)) {
			Py_DECREF(seq);
			return false;
		}
		out.emplace_back(
			utf8_to_wstr(std::string_view(
				name, static_cast<size_t>(nlen))),
			utf8_to_wstr(std::string_view(
				spec, static_cast<size_t>(slen))));
	}
	Py_DECREF(seq);
	return true;
}

/* Settle a dialog callback with (status, cancelled, paths). status is 0 on a
 * dialog that ran, 1 when aborted on shutdown, 2 on a failure to run.
 */
void deliver_dialog(const PyRef &ref, const dialog_t::result_t &res)
{
	int status = SUCCEEDED(res.hresult)
		? 0 : (res.hresult == E_ABORT ? 1 : 2);

	PyGILState_STATE gil = PyGILState_Ensure();
	PyObject *paths = PyList_New(0);
	if (paths) {
		for (const auto &p : res.paths) {
			std::string u = wstr_to_utf8(p);
			PyObject *s = PyUnicode_FromStringAndSize(
				u.data(), static_cast<Py_ssize_t>(u.size()));
			if (s) {
				PyList_Append(paths, s);
				Py_DECREF(s);
			}
		}
		invoke(ref.get(), Py_BuildValue("(iON)", status,
			res.cancelled ? Py_True : Py_False, paths));
	} else {
		PyErr_WriteUnraisable(ref.get());
	}
	PyGILState_Release(gil);
}

PyDoc_STRVAR(ping_doc, "Return True. Used to check the builtin module loads");
PyObject *ping(PyObject *, PyObject *)
{
	Py_RETURN_TRUE;
}

PyDoc_STRVAR(get_event_doc,
	"get_event(cb) -> bool\n\n"
	"Register cb for the next inbound event. cb is called with the event as "
	"a JSON-encoded object (UTF-8). Returns False without registering when "
	"the bridge is shut down.");
PyObject *get_event(PyObject *, PyObject *args)
{
	PyObject *cb;
	if (!PyArg_ParseTuple(args, "O:get_event", &cb))
		return nullptr;
	if (!PyCallable_Check(cb)) {
		PyErr_SetString(PyExc_TypeError, "cb must be callable");
		return nullptr;
	}
	if (!g_app)
		Py_RETURN_FALSE;

	PyRef ref = py_keep(cb);
	bool ok = g_app->get_event([ref](std::string ev) {
		PyGILState_STATE gil = PyGILState_Ensure();
		invoke(ref.get(), Py_BuildValue("(s#)",
			ev.data(), static_cast<Py_ssize_t>(ev.size())));
		PyGILState_Release(gil);
	});
	if (!ok)
		Py_RETURN_FALSE;
	Py_RETURN_TRUE;
}

PyDoc_STRVAR(js_call_doc,
	"js_call(script, cb) -> None\n\n"
	"Run a frontend script and settle cb with (status, payload). status is "
	"0 with the raw JSON result - a value, or a pywebviewJavascriptError420 "
	"object on a throw - or 2 when the call did not run.");
PyObject *js_call(PyObject *, PyObject *args)
{
	const char *script;
	Py_ssize_t len;
	PyObject *cb;
	if (!PyArg_ParseTuple(args, "s#O:js_call", &script, &len, &cb))
		return nullptr;
	if (!PyCallable_Check(cb)) {
		PyErr_SetString(PyExc_TypeError, "cb must be callable");
		return nullptr;
	}
	if (!g_app) {
		PyErr_SetString(PyExc_RuntimeError, "native app not ready");
		return nullptr;
	}

	PyRef ref = py_keep(cb);
	std::wstring wscript = utf8_to_wstr(
		std::string_view(script, static_cast<size_t>(len)));
	g_app->eval_js(std::move(wscript),
		[ref](HRESULT hr, const std::wstring &json) {
			int status;
			std::string payload;
			if (SUCCEEDED(hr)) {
				status = 0;
				payload = wstr_to_utf8(json);
			} else {
				status = 2;
			}
			PyGILState_STATE gil = PyGILState_Ensure();
			invoke(ref.get(), Py_BuildValue("(is#)", status,
				payload.data(),
				static_cast<Py_ssize_t>(payload.size())));
			PyGILState_Release(gil);
		});
	Py_RETURN_NONE;
}

PyDoc_STRVAR(show_open_dialog_doc,
	"show_open_dialog(multiple, filters, cb) -> None\n\n"
	"Show an open dialog and settle cb with (status, cancelled, paths). "
	"filters is a sequence of (name, spec) str pairs.");
PyObject *show_open_dialog(PyObject *, PyObject *args)
{
	int multiple;
	PyObject *filters;
	PyObject *cb;
	if (!PyArg_ParseTuple(args, "pOO:show_open_dialog",
			&multiple, &filters, &cb))
		return nullptr;
	if (!PyCallable_Check(cb)) {
		PyErr_SetString(PyExc_TypeError, "cb must be callable");
		return nullptr;
	}
	if (!g_app) {
		PyErr_SetString(PyExc_RuntimeError, "native app not ready");
		return nullptr;
	}
	std::vector<std::pair<std::wstring, std::wstring>> f;
	if (!to_wfilters(filters, f))
		return nullptr;

	PyRef ref = py_keep(cb);
	g_app->show_open_dialog(multiple != 0, std::move(f),
		[ref](dialog_t::result_t res) { deliver_dialog(ref, res); });
	Py_RETURN_NONE;
}

PyDoc_STRVAR(show_save_dialog_doc,
	"show_save_dialog(filename, filters, cb) -> None\n\n"
	"Show a save dialog and settle cb with (status, cancelled, paths). "
	"filters is a sequence of (name, spec) str pairs.");
PyObject *show_save_dialog(PyObject *, PyObject *args)
{
	const char *filename;
	Py_ssize_t len;
	PyObject *filters;
	PyObject *cb;
	if (!PyArg_ParseTuple(args, "s#OO:show_save_dialog",
			&filename, &len, &filters, &cb))
		return nullptr;
	if (!PyCallable_Check(cb)) {
		PyErr_SetString(PyExc_TypeError, "cb must be callable");
		return nullptr;
	}
	if (!g_app) {
		PyErr_SetString(PyExc_RuntimeError, "native app not ready");
		return nullptr;
	}
	std::vector<std::pair<std::wstring, std::wstring>> f;
	if (!to_wfilters(filters, f))
		return nullptr;

	PyRef ref = py_keep(cb);
	std::wstring wname = utf8_to_wstr(
		std::string_view(filename, static_cast<size_t>(len)));
	g_app->show_save_dialog(std::move(wname), std::move(f),
		[ref](dialog_t::result_t res) { deliver_dialog(ref, res); });
	Py_RETURN_NONE;
}

PyDoc_STRVAR(set_title_doc, "set_title(title) -> None");
PyObject *set_title(PyObject *, PyObject *args)
{
	const char *title;
	Py_ssize_t len;
	if (!PyArg_ParseTuple(args, "s#:set_title", &title, &len))
		return nullptr;
	if (g_app)
		g_app->set_title(utf8_to_wstr(
			std::string_view(title, static_cast<size_t>(len))));
	Py_RETURN_NONE;
}

PyDoc_STRVAR(set_theme_doc, "set_theme(mode) -> None");
PyObject *set_theme(PyObject *, PyObject *args)
{
	const char *mode;
	Py_ssize_t len;
	if (!PyArg_ParseTuple(args, "s#:set_theme", &mode, &len))
		return nullptr;
	if (g_app)
		g_app->set_theme(utf8_to_wstr(
			std::string_view(mode, static_cast<size_t>(len))));
	Py_RETURN_NONE;
}

PyDoc_STRVAR(hide_doc, "hide() -> None");
PyObject *hide(PyObject *, PyObject *)
{
	if (g_app)
		g_app->hide();
	Py_RETURN_NONE;
}

PyDoc_STRVAR(quit_doc, "quit() -> None");
PyObject *quit(PyObject *, PyObject *)
{
	if (g_app)
		g_app->quit();
	Py_RETURN_NONE;
}

PyMethodDef pyext_methods[] = {
	{ "ping", ping, METH_NOARGS, ping_doc },
	{ "get_event", get_event, METH_VARARGS, get_event_doc },
	{ "js_call", js_call, METH_VARARGS, js_call_doc },
	{ "show_open_dialog", show_open_dialog, METH_VARARGS,
		show_open_dialog_doc },
	{ "show_save_dialog", show_save_dialog, METH_VARARGS,
		show_save_dialog_doc },
	{ "set_title", set_title, METH_VARARGS, set_title_doc },
	{ "set_theme", set_theme, METH_VARARGS, set_theme_doc },
	{ "hide", hide, METH_NOARGS, hide_doc },
	{ "quit", quit, METH_NOARGS, quit_doc },
	{ nullptr, nullptr, 0, nullptr },
};

PyDoc_STRVAR(pyext_doc, "Native Windows host primitives for Backpack App");
PyModuleDef pyext_module = {
	PyModuleDef_HEAD_INIT,
	"_app",
	pyext_doc,
	0,
	pyext_methods,
	nullptr,
	nullptr,
	nullptr,
	nullptr,
};

} /* namespace */

PyObject *pyext_init(void)
{
	return PyModule_Create(&pyext_module);
}
