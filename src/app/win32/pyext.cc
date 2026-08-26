#include "pyext.h"
#include <Python.h>

PyDoc_STRVAR(ping_doc, "Return True. Used to check the builtin module loads");
static PyObject *ping(PyObject *, PyObject *)
{
	Py_RETURN_TRUE;
}

static PyMethodDef pyext_methods[] = {
	{ "ping", ping, METH_NOARGS, ping_doc },
	{ nullptr, nullptr, 0, nullptr },
};

PyDoc_STRVAR(pyext_doc, "Native Windows host primitives for Backpack App");
static PyModuleDef pyext_module = {
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

PyObject *pyext_init(void)
{
	return PyModule_Create(&pyext_module);
}
