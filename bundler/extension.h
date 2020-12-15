/*
Ruby Marshal48 machine - for python

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


#ifndef BUNDLER_PYTHON_EXT_H
#define BUNDLER_PYTHON_EXT_H

#include <Python.h>
#include <stdbool.h>


extern PyTypeObject	bundler_GemfileType;
extern PyTypeObject	bundler_ContextType;
extern PyObject *       bundler_Exception(const char *fmt, ...);

static inline void
assign_string(char **var, const char *str)
{
	if (*var == str)
		return;

	if (*var) {
		free(*var);
		*var = NULL;
	}

	if (str)
		*var = strdup(str);
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

#endif /* BUNDLER_PYTHON_EXT_H */

