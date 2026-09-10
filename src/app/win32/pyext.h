#ifndef PYEXT_H
#define PYEXT_H

struct _object;
typedef struct _object PyObject;

class app_t;

/* Point the _app extension at the native host before the interpreter starts.
 * The extension owns no window; every primitive it exposes forwards to this
 * app_t, so it must be set before Python imports _app.
 */
void pyext_set_app(app_t *app);

/* Builtin module init for _app, registered with PyImport_AppendInittab. */
PyObject *pyext_init(void);

#endif /* PYEXT_H */
