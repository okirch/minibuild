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


static void		String_dealloc(marshal48_String *self);
static PyObject *	String_new(PyTypeObject *type, PyObject *args, PyObject *kwds);
static PyObject *	String_convert(marshal48_String *self, PyObject *args);
static PyObject *	String_set_instance_var(marshal48_String *self, PyObject *args);

static PyMemberDef String_members[] = {
	{"id", T_INT, offsetof(marshal48_String, id), 0, "object id"},
	{"value", T_STRING, offsetof(marshal48_String, value), 0, "value"},

	{ NULL }
};

static PyMethodDef String_methods[] = {
	{ "convert", (PyCFunction) String_convert, METH_NOARGS, NULL },
	{ "set_instance_var", (PyCFunction) String_set_instance_var, METH_VARARGS, NULL },
	{ NULL }
};

PyTypeObject marshal48_StringType = {
	PyVarObject_HEAD_INIT(NULL, 0)

	.tp_name	= "ruby.String",
	.tp_basicsize	= sizeof(marshal48_String),
	.tp_flags	= Py_TPFLAGS_DEFAULT,
	.tp_doc		= "ruby string",

	.tp_init	= (initproc) String_init,
	.tp_new		= String_new,
	.tp_dealloc	= (destructor) String_dealloc,

	.tp_members	= String_members,
	.tp_methods	= String_methods,
};

/*
 * Constructor: allocate empty String object, and set its members.
 */
static PyObject *
String_new(PyTypeObject *type, PyObject *args, PyObject *kwds)
{
	marshal48_String *self;

	self = (marshal48_String *) type->tp_alloc(type, 0);
	if (self == NULL)
		return NULL;

	/* init members */
	self->id = -1;
	self->value = NULL;

	return (PyObject *)self;
}

/*
 * Initialize the string object
 */
int
String_init(marshal48_String *self, PyObject *args, PyObject *kwds)
{
	static char *kwlist[] = {
		"value",
		NULL
	};
	char *value = NULL;

	if (!PyArg_ParseTupleAndKeywords(args, kwds, "|s", kwlist, &value))
		return -1;

	if (value != NULL)
		self->value = strdup(value);
	else
		self->value = strdup("zoppo");
	return 0;
}

/*
 * Convert from ruby type to native python type
 */
static PyObject *
String_convert(marshal48_String *self, PyObject *args)
{
	if (!PyArg_ParseTuple(args, ""))
		return NULL;

	return PyUnicode_FromString(self->value);
}

static PyObject *
String_set_instance_var(marshal48_String *self, PyObject *args)
{
	char *name;
	PyObject *value;

	if (!PyArg_ParseTuple(args, "sO", &name, &value))
		return NULL;

	/* String encoding True/False - not quite sure what this means;
	 * so we'll ignore it for now. */
	if (!strcmp(name, "E")) {
		if (!PyBool_Check(value)) {
			PyErr_SetString(PyExc_TypeError, "String: instance variable E must be a boolean");
			return NULL;
		}

		if (PyObject_IsTrue(value)) {
			/* Do something */
		} else {
			/* Do something else */
		}
	} else {
		PyErr_Format(PyExc_TypeError, "String: unsupported instance variable %s", name);
		return NULL;
	}

	Py_DECREF(value);

	Py_RETURN_NONE;
}

/*
 * Destructor: clean any state inside the String object
 */
static void
String_dealloc(marshal48_String *self)
{
	drop_string(&self->value);
}

int
String_Check(PyObject *self)
{
	return PyType_IsSubtype(Py_TYPE(self), &marshal48_StringType);
}
