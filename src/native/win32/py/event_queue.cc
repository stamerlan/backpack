#include "object.h"
#include <string>
#include <event_queue.h>
#include "invoke.h"
#include "keep.h"

/* Python object wrapping a borrowed event_queue_t. */
struct EventQueueObject {
	PyObject_HEAD
	event_queue_t *events;
};

static PyObject *py_get(PyObject *self, PyObject *args)
{
	PyObject *cb;
	if (!PyArg_ParseTuple(args, "O:get", &cb))
		return nullptr;
	if (!PyCallable_Check(cb)) {
		PyErr_SetString(PyExc_TypeError, "cb must be callable");
		return nullptr;
	}
	event_queue_t *ev = reinterpret_cast<EventQueueObject *>(self)->events;
	std::shared_ptr<PyObject> ref = py::keep(cb);
	bool ok = ev->set_cb([ref](std::string event) {
		PyGILState_STATE gil = PyGILState_Ensure();
		py::invoke(ref.get(), Py_BuildValue("(s#)",
			event.data(), static_cast<Py_ssize_t>(event.size())));
		PyGILState_Release(gil);
	});
	if (!ok)
		Py_RETURN_FALSE;
	Py_RETURN_TRUE;
}

static PyMethodDef event_queue_methods[] = {
	{
		"get", py_get, METH_VARARGS,
		PyDoc_STR("get(cb) -> bool\n\n"
			"Register cb for the next inbound event, called with "
			"the event as a JSON string (UTF-8), or with an empty "
			"string when the queue is aborted. Returns False "
			"without registering when the queue is shut down.")
	},
	{ nullptr, nullptr, 0, nullptr },
};

static PyTypeObject EventQueueType = {
	.ob_base = PyVarObject_HEAD_INIT(nullptr, 0)
	.tp_name = "native.win32.EventQueue",
	.tp_basicsize = sizeof(EventQueueObject),
	.tp_flags = Py_TPFLAGS_DEFAULT,
	.tp_doc =
		PyDoc_STR("Inbound event queue: frontend calls and OS notices"),
	.tp_methods = event_queue_methods,
};

PyObject *py::to_object(event_queue_t& events)
{
	if (PyType_Ready(&EventQueueType) < 0)
		return nullptr;
	EventQueueObject *o = PyObject_New(EventQueueObject, &EventQueueType);
	if (!o)
		return nullptr;
	o->events = &events;
	return reinterpret_cast<PyObject *>(o);
}
