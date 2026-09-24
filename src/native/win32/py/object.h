#ifndef PY_OBJECT_H
#define PY_OBJECT_H

#include <Python.h>
#include <windows.h>

class event_queue_t;
class script_queue_t;
class webview_t;
class window_t;

namespace py {

PyObject *to_object(window_t& window);
PyObject *to_object(webview_t& webview, HWND hwnd);
PyObject *to_object(event_queue_t& events);
PyObject *to_object(script_queue_t& queue);

} /* namespace py */

#endif /* PY_OBJECT_H */
