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


#ifndef MARSHAL48_PYTHON_EXT_H
#define MARSHAL48_PYTHON_EXT_H


#include <Python.h>
#include <string.h>
#include <stdbool.h>

typedef struct {
	PyObject_HEAD
	char *		name;
} marshal48_Symbol;

typedef struct {
	PyObject_HEAD
	int		value;
} marshal48_Int;

typedef struct {
	PyObject_HEAD
	int		id;
	char *		value;
} marshal48_String;

typedef struct {
	PyObject_HEAD
	int		id;
	PyObject *	values;
} marshal48_Array;

typedef struct {
	PyObject_HEAD
	int		id;
	PyObject *	value;
} marshal48_Hash;

typedef struct {
	PyObject_HEAD
	int		id;
	char *		classname;
	PyObject *	instance_vars;	/* dict */
} marshal48_GenericObject;

typedef struct {
	marshal48_GenericObject base;
	PyObject *	data;
} marshal48_UserDefined;

typedef struct {
	marshal48_GenericObject base;
	PyObject *	data;
} marshal48_UserMarshal;

extern PyObject *	marshal48_unmarshal_io(PyObject *io);
extern PyObject *	marshal48_instantiate_ruby_type(const char *name);
extern PyObject *	marshal48_instantiate_ruby_type_with_arg(const char *name, PyObject *);

extern PyTypeObject	marshal48_SymbolType;
extern PyTypeObject	marshal48_IntType;
extern PyTypeObject	marshal48_StringType;
extern PyTypeObject	marshal48_ArrayType;
extern PyTypeObject	marshal48_HashType;
extern PyTypeObject	marshal48_GenericObjectType;
extern PyTypeObject	marshal48_UserDefinedType;
extern PyTypeObject	marshal48_UserMarshalType;

extern int		Symbol_init(marshal48_Symbol *self, PyObject *args, PyObject *kwds);
extern int		Int_init(marshal48_Int *self, PyObject *args, PyObject *kwds);
extern int		String_init(marshal48_String *self, PyObject *args, PyObject *kwds);
extern int		Array_init(marshal48_Array *self, PyObject *args, PyObject *kwds);
extern int		Hash_init(marshal48_Hash *self, PyObject *args, PyObject *kwds);
extern int		GenericObject_init(marshal48_GenericObject *self, PyObject *args, PyObject *kwds);
extern int		UserDefined_init(marshal48_UserDefined *self, PyObject *args, PyObject *kwds);
extern int		UserMarshal_init(marshal48_UserMarshal *self, PyObject *args, PyObject *kwds);

static inline void
assign_string(char **var, char *str)
{
	if (*var == str)
		return;
	if (str)
		str = strdup(str);
	if (*var)
		free(*var);
	*var = str;
}

static inline PyObject *
return_string_or_none(const char *value)
{
	if (value == NULL) {
		Py_INCREF(Py_None);
		return Py_None;
	}
	return PyUnicode_FromString(value);
}

static inline PyObject *
return_bool(bool bv)
{
	PyObject *result;

	result = bv? Py_True : Py_False;
	Py_INCREF(result);
	return result;
}

static inline void
drop_string(char **var)
{
	assign_string(var, NULL);
}

static inline void
assign_object(PyObject **var, PyObject *obj)
{
	if (obj) {
		Py_INCREF(obj);
	}
	if (*var) {
		Py_DECREF(*var);
	}
	*var = obj;
}

static inline void
drop_object(PyObject **var)
{
	assign_object(var, NULL);
}

#endif /* MARSHAL48_PYTHON_EXT_H */

