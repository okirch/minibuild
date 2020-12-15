/*
Ruby bundler files - for python

Copyright (C) 2020 SUSE

This program is free software; you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, version 2.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License along
with this program; if not, write to the Free Software Foundation, Inc.,
51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.
*/


#include "extension.h"


static PyObject	*	theModule = NULL;

/*
 * Methods belonging to the module itself.
 */
static PyMethodDef bundler_methods[] = {
	{ NULL }
};

#ifndef PyMODINIT_FUNC	/* declarations for DLL import/export */
# define PyMODINIT_FUNC void
#endif

void
bundler_registerType(PyObject *m, const char *name, PyTypeObject *type)
{
	if (PyType_Ready(type) < 0)
		return;

	Py_INCREF(type);
	PyModule_AddObject(m, name, (PyObject *) type);
}

PyObject *
bundler_callObject(PyObject *callable, PyObject *args, PyObject *kwds)
{
	PyObject *obj;

	if (args == NULL) {
		args = PyTuple_New(0);
		obj = PyObject_Call(callable, args, NULL);
		Py_DECREF(args);
	} else {
		obj = PyObject_Call(callable, args, kwds);
	}

	return obj;
}

PyObject *
bundler_callType(PyTypeObject *typeObject, PyObject *args, PyObject *kwds)
{
	return bundler_callObject((PyObject *) typeObject, args, kwds);
}

PyObject *
ruby_get_module(void)
{
	static PyObject *module = NULL;

	if (module == NULL) {
		PyObject *nameObj;

		nameObj = PyUnicode_FromString("ruby");
		module = PyImport_Import(nameObj);
	}

	return module;
}

static struct PyModuleDef bundler_module = {
	PyModuleDef_HEAD_INIT,
	"bundler",
	"Module for ruby bundler support",
	-1,
	bundler_methods
};

PyMODINIT_FUNC
PyInit_bundler(void) 
{
	PyObject* m;

	m = PyModule_Create(&bundler_module);
	if (m == NULL)
		return NULL;

	bundler_registerType(m, "Gemfile", &bundler_GemfileType);
	bundler_registerType(m, "Context", &bundler_ContextType);

	theModule = m;
	return m;
}
