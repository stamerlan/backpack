#ifndef PYEXT_H
#define PYEXT_H

struct _object;
typedef struct _object PyObject;

PyObject *pyext_init(void);

#endif /* PYEXT_H */
