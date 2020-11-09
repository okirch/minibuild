/*
Simple ruby types for marshal48

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


#include <Python.h>
#include <structmember.h>

#include "extension.h"


static void		Array_dealloc(marshal48_Array *self);
static PyObject *	Array_new(PyTypeObject *type, PyObject *args, PyObject *kwds);
static PyObject *	Array_append(marshal48_Array *self, PyObject *args);
static PyObject *	Array_convert(marshal48_Array *self, PyObject *args);

static PyMemberDef Array_members[] = {
	{"id", T_INT, offsetof(marshal48_Array, id), 0, "object id"},
	{"values", T_OBJECT, offsetof(marshal48_Array, values), 0, "array values"},

	{ NULL }
};

static PyMethodDef Array_methods[] = {
	{ "append", (PyCFunction) Array_append, METH_VARARGS, NULL },
	{ "convert", (PyCFunction) Array_convert, METH_NOARGS, NULL },
	{ NULL }
};


PyTypeObject marshal48_ArrayType = {
	PyVarObject_HEAD_INIT(NULL, 0)

	.tp_name	= "marshal48.Array",
	.tp_basicsize	= sizeof(marshal48_Array),
	.tp_flags	= Py_TPFLAGS_DEFAULT,
	.tp_doc		= "ruby array",

	.tp_init	= (initproc) Array_init,
	.tp_new		= Array_new,
	.tp_dealloc	= (destructor) Array_dealloc,

	.tp_members	= Array_members,
	.tp_methods	= Array_methods,
};

/*
 * Constructor: allocate empty Array object, and set its members.
 */
static PyObject *
Array_new(PyTypeObject *type, PyObject *args, PyObject *kwds)
{
	marshal48_Array *self;

	self = (marshal48_Array *) type->tp_alloc(type, 0);
	if (self == NULL)
		return NULL;

	/* init members */
	self->id = -1;
	self->values = PyList_New(0);

	return (PyObject *)self;
}

/*
 * Initialize the array object
 */
int
Array_init(marshal48_Array *self, PyObject *args, PyObject *kwds)
{
	static char *kwlist[] = {
		NULL
	};

	if (!PyArg_ParseTupleAndKeywords(args, kwds, "", kwlist))
		return -1;

	self->values = PyList_New(0);
	return 0;
}

/*
 * Destructor: clean any state inside the Array object
 */
static void
Array_dealloc(marshal48_Array *self)
{
	Py_DECREF(self->values);
	self->values = NULL;
}

int
Array_Check(PyObject *self)
{
	return PyType_IsSubtype(Py_TYPE(self), &marshal48_ArrayType);
}

static PyObject *
Array_append(marshal48_Array *self, PyObject *args)
{
	PyObject *item;

	if (!PyArg_Parse(args, "O", &item))
		return NULL;

	/* FIXME: we should check that the object we append is a ruby object
	 * that provides a convert() method */
	PyList_Append(self->values, item);

	Py_RETURN_NONE;
}

static PyObject *
Array_convert(marshal48_Array *self, PyObject *args)
{
	PyObject *result;
	unsigned int i, len;

	if (!PyArg_Parse(args, ""))
		return NULL;

	len = PyList_Size(self->values);

	result = PyList_New(len);
	for (i = 0; i < len; ++i) {
		PyObject *item = PyList_GET_ITEM(self->values, i);

		assert(item);
		item = PyObject_CallMethod(item, "convert", NULL);
		if (item == NULL) {
			Py_DECREF(result);
			return NULL;
		}

		PyList_SET_ITEM(result, i, item);
	}

	return result;
}
