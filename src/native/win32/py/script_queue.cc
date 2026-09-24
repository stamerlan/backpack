#include "object.h"
#include <string>
#include <script_queue.h>
#include <utf8.h>
#include "invoke.h"
#include "keep.h"

struct ScriptQueueObject {
	PyObject_HEAD
	script_queue_t *queue;
};

static PyObject *py_exec_script(PyObject *self, PyObject *args)
{
	const char *script;
	PyObject *cb;
	if (!PyArg_ParseTuple(args, "sO:exec_script", &script, &cb))
		return nullptr;
	if (!PyCallable_Check(cb)) {
		PyErr_SetString(PyExc_TypeError, "cb must be callable");
		return nullptr;
	}
	script_queue_t *q = reinterpret_cast<ScriptQueueObject *>(self)->queue;
	std::shared_ptr<PyObject> ref = py::keep(cb);
	bool ok = q->exec_script(utf8_to_wstr(script),
		[ref](HRESULT hr, const std::wstring &json) {
			int status = SUCCEEDED(hr)
				? 0 : (hr == E_ABORT ? 1 : 2);
			std::string payload = wstr_to_utf8(json);
			PyGILState_STATE gil = PyGILState_Ensure();
			py::invoke(ref.get(), Py_BuildValue("(is#)", status,
				payload.data(),
				static_cast<Py_ssize_t>(payload.size())));
			PyGILState_Release(gil);
		});
	if (!ok)
		Py_RETURN_FALSE;
	Py_RETURN_TRUE;
}

static PyMethodDef script_queue_methods[] = {
	{
		"exec_script", py_exec_script, METH_VARARGS,
		PyDoc_STR("exec_script(script, cb) -> bool\n\n"
			"Queue a frontend script; scripts run one at a time in "
			"submission order. cb settles once with "
			"(status, payload): status 0 with the JSON result, "
			"1 on abort, 2 on a transport failure. Returns False "
			"without queuing when the queue is aborted.")
	},
	{ nullptr, nullptr, 0, nullptr },
};

static PyTypeObject ScriptQueueType = {
	.ob_base = PyVarObject_HEAD_INIT(nullptr, 0)
	.tp_name = "native.win32.ScriptQueue",
	.tp_basicsize = sizeof(ScriptQueueObject),
	.tp_flags = Py_TPFLAGS_DEFAULT,
	.tp_doc = PyDoc_STR("Outbound js scripts, running one at a time"),
	.tp_methods = script_queue_methods,
};

PyObject *py::to_object(script_queue_t& queue)
{
	if (PyType_Ready(&ScriptQueueType) < 0)
		return nullptr;
	ScriptQueueObject *o =
		PyObject_New(ScriptQueueObject, &ScriptQueueType);
	if (!o)
		return nullptr;
	o->queue = &queue;
	return reinterpret_cast<PyObject *>(o);
}
