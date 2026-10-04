#include "object.h"
#include <string_view>
#include <logger.h>

struct LoggerObject {
	PyObject_HEAD
};

static PyObject *py_write(PyObject *, PyObject *args)
{
	int level;
	const char *name, *func, *msg;
	Py_ssize_t name_n, func_n, msg_n;
	if (!PyArg_ParseTuple(args, "is#s#s#:write", &level, &name, &name_n,
		&func, &func_n, &msg, &msg_n))
		return nullptr;
	/* The args tuple keeps the UTF-8 buffers alive without the GIL */
	Py_BEGIN_ALLOW_THREADS
	logger::write(level, std::string_view(name, name_n),
		std::string_view(func, func_n), std::string_view(msg, msg_n));
	Py_END_ALLOW_THREADS
	Py_RETURN_NONE;
}

static PyObject *py_get_level(PyObject *, void *)
{
	return PyLong_FromLong(logger::level());
}

static PyMethodDef logger_methods[] = {
	{
		"write", py_write, METH_VARARGS,
		PyDoc_STR("write(level, name, func, msg) -> None\n\n"
			"Write one record to the native log.")
	},
	{ nullptr, nullptr, 0, nullptr },
};

static PyGetSetDef logger_getset[] = {
	{
		"level", py_get_level, nullptr,
		PyDoc_STR("Native log level, a Python logging level"), nullptr
	},
	{ nullptr, nullptr, nullptr, nullptr, nullptr },
};

static PyTypeObject LoggerType = {
	.ob_base = PyVarObject_HEAD_INIT(nullptr, 0)
	.tp_name = "native.win32.Logger",
	.tp_basicsize = sizeof(LoggerObject),
	.tp_flags = Py_TPFLAGS_DEFAULT,
	.tp_doc = PyDoc_STR("Native log sink"),
	.tp_methods = logger_methods,
	.tp_getset = logger_getset,
};

PyObject *py::logger_object(void)
{
	if (PyType_Ready(&LoggerType) < 0)
		return nullptr;
	return reinterpret_cast<PyObject *>(
		PyObject_New(LoggerObject, &LoggerType));
}
