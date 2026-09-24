#include "object.h"
#include <defer_call.h>
#include <webview.h>

struct WebViewObject {
	PyObject_HEAD
	webview_t *webview;
	HWND hwnd;
};

static PyObject *py_close(PyObject *self, PyObject *)
{
	auto *o = reinterpret_cast<WebViewObject *>(self);
	webview_t *wv = o->webview;
	try {
		defer_call(o->hwnd, [wv](void) { wv->close(); });
	} catch (...) {
		/* the post failed (window gone); teardown is under way */
	}
	Py_RETURN_NONE;
}

static PyMethodDef webview_methods[] = {
	{ "close", py_close, METH_NOARGS, PyDoc_STR("close() -> None") },
	{ nullptr, nullptr, 0, nullptr },
};

static PyTypeObject WebViewType = {
	.ob_base = PyVarObject_HEAD_INIT(nullptr, 0)
	.tp_name = "native.win32.WebView",
	.tp_basicsize = sizeof(WebViewObject),
	.tp_flags = Py_TPFLAGS_DEFAULT,
	.tp_doc = PyDoc_STR("Native WebView2 control"),
	.tp_methods = webview_methods,
};

PyObject *py::to_object(webview_t& webview, HWND hwnd)
{
	if (PyType_Ready(&WebViewType) < 0)
		return nullptr;
	WebViewObject *o = PyObject_New(WebViewObject, &WebViewType);
	if (!o)
		return nullptr;
	o->webview = &webview;
	o->hwnd = hwnd;
	return reinterpret_cast<PyObject *>(o);
}
