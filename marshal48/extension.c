/*
Ruby marshal48 - for python

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

static PyObject *	marshal48_Unmarshal(PyObject *, PyObject *, PyObject *);

/*
 * Methods belonging to the module itself.
 */
static PyMethodDef marshal48_methods[] = {
	{ "unmarshal", (PyCFunction) marshal48_Unmarshal, METH_VARARGS | METH_KEYWORDS, "Unmarshal ruby data"},

	{ NULL }
};

#ifndef PyMODINIT_FUNC	/* declarations for DLL import/export */
# define PyMODINIT_FUNC void
#endif

#if 0
/*
 * Convert marshal48 error to an exception
 */
PyObject *
marshal48_Exception(const char *msg, int rc)
{
	char buffer[256];

	snprintf(buffer, sizeof(buffer), "%s: %s", msg, marshal48_strerror(rc));
	PyErr_SetString(PyExc_SystemError, buffer);
	return NULL;
}

static PyObject *
marshal48_setDebugLevel(PyObject *self, PyObject *args, PyObject *kwds)
{
	static char *kwlist[] = {
		"level",
		NULL
	};
	int level;

	if (!PyArg_ParseTupleAndKeywords(args, kwds, "i", kwlist, &level))
		return NULL;

	marshal48_debug_level = level;
	Py_INCREF(Py_None);
	return Py_None;

}
#endif

static PyObject *
marshal48_Unmarshal(PyObject *self, PyObject *args, PyObject *kwds)
{
	ruby_context_t *ruby;
	static char *kwlist[] = {
		"io",
		"factory",
		"quiet",
		NULL
	};
	ruby_instance_t *unmarshaled;
	PyObject *io, *factory, *result = NULL;
	int quiet = 1;

	if (!PyArg_ParseTupleAndKeywords(args, kwds, "OO|i", kwlist, &io, &factory, &quiet))
		return NULL;

	ruby = ruby_context_new();

	unmarshaled = marshal48_unmarshal_io(ruby, io, quiet);
	if (unmarshaled != NULL) {
		ruby_converter_t *converter;

		/* now convert it */
		converter = ruby_converter_new(factory);
		result = ruby_instance_convert(unmarshaled, converter);
		ruby_converter_free(converter);
	}

	ruby_context_free(ruby);
	return result;
}

void
marshal48_registerType(PyObject *m, const char *name, PyTypeObject *type)
{
	if (PyType_Ready(type) < 0)
		return;

	Py_INCREF(type);
	PyModule_AddObject(m, name, (PyObject *) type);
}

PyObject *
marshal48_callObject(PyObject *callable, PyObject *args, PyObject *kwds)
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
marshal48_callType(PyTypeObject *typeObject, PyObject *args, PyObject *kwds)
{
	return marshal48_callObject((PyObject *) typeObject, args, kwds);
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

PyObject *
marshal48_instantiate_ruby_type_with_arg(const char *name, PyObject *arg, ruby_converter_t *converter)
{
	PyObject *module, *func, *args, *result;

	if (converter) {
		PyObject *name_obj;

		func = converter->factory;
		if (!PyCallable_Check(func)) {
			PyErr_SetString(PyExc_TypeError, "ruby: factory argument must be callable");
			return NULL;
		}

		args = PyTuple_New(1 + (arg? 1 : 0));

		name_obj = PyUnicode_FromString(name);
		PyTuple_SetItem(args, 0, name_obj);

		if (arg != NULL) {
			PyTuple_SetItem(args, 1, arg);
			Py_INCREF(arg);
		}
	} else {
#if 1
		module = theModule;
#else
		if (!(module = ruby_get_module()))
			module = theModule;
#endif

		if (module == NULL)
			return NULL;

		func = PyDict_GetItemString(PyModule_GetDict(module), name);
		if (!PyCallable_Check(func)) {
			PyErr_Format(PyExc_TypeError, "ruby: cannot instantiate %s", name);
			return NULL;
		}

		if (arg != NULL) {
			args = PyTuple_New(1);
			PyTuple_SetItem(args, 0, arg);
		} else {
			args = PyTuple_New(0);
		}
	}

	result = PyObject_CallObject(func, args);
	Py_DECREF(args);

	/* Returning None is just like throwing an exception */
	if (result == Py_None) {
		Py_DECREF(result);
		result = NULL;
	}

	return result;
}

PyObject *
marshal48_instantiate_ruby_type(const char *name, ruby_converter_t *converter)
{
	return marshal48_instantiate_ruby_type_with_arg(name, NULL, converter);
}

static struct PyModuleDef marshal48_module = {
	PyModuleDef_HEAD_INIT,
	"marshal48",
	"Module for ruby marshal48",
	-1,
	marshal48_methods
};

PyMODINIT_FUNC
PyInit_marshal48(void) 
{
	PyObject* m;

	m = PyModule_Create(&marshal48_module);
	if (m == NULL)
		return NULL;

#if 0
	/* These two aren't really used right now */
	marshal48_registerType(m, "Symbol", &marshal48_SymbolType);
	marshal48_registerType(m, "Int", &marshal48_IntType);

	marshal48_registerType(m, "String", &marshal48_StringType);
	marshal48_registerType(m, "Array", &marshal48_ArrayType);
	marshal48_registerType(m, "Hash", &marshal48_HashType);
	marshal48_registerType(m, "GenericObject", &marshal48_GenericObjectType);
	marshal48_registerType(m, "UserDefined", &marshal48_UserDefinedType);
	marshal48_registerType(m, "UserMarshal", &marshal48_UserMarshalType);
#endif

	theModule = m;

	return m;
}
