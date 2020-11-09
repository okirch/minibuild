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


static void		Hash_dealloc(marshal48_Hash *self);
static PyObject *	Hash_new(PyTypeObject *type, PyObject *args, PyObject *kwds);
static PyObject *	Hash_set(marshal48_Hash *self, PyObject *args);
static PyObject *	Hash_convert(marshal48_Hash *self, PyObject *args);

static PyMemberDef Hash_members[] = {
	{"id", T_INT, offsetof(marshal48_Hash, id), 0, "object id"},
	{ "value", T_OBJECT, offsetof(marshal48_Hash, value), 0, "internal hash"},

	{ NULL }
};

static PyMethodDef Hash_methods[] = {
	{ "set", (PyCFunction) Hash_set, METH_VARARGS, NULL },
	{ "convert", (PyCFunction) Hash_convert, METH_NOARGS, NULL },
	{ NULL }
};


PyTypeObject marshal48_HashType = {
	PyVarObject_HEAD_INIT(NULL, 0)

	.tp_name	= "marshal48.Hash",
	.tp_basicsize	= sizeof(marshal48_Hash),
	.tp_flags	= Py_TPFLAGS_DEFAULT,
	.tp_doc		= "ruby hash",

	.tp_init	= (initproc) Hash_init,
	.tp_new		= Hash_new,
	.tp_dealloc	= (destructor) Hash_dealloc,

	.tp_members	= Hash_members,
	.tp_methods	= Hash_methods,
};

/*
 * Constructor: allocate empty Hash object, and set its members.
 */
static PyObject *
Hash_new(PyTypeObject *type, PyObject *args, PyObject *kwds)
{
	marshal48_Hash *self;

	self = (marshal48_Hash *) type->tp_alloc(type, 0);
	if (self == NULL)
		return NULL;

	/* init members */
	self->id = -1;
	self->value = PyDict_New();

	return (PyObject *)self;
}

/*
 * Initialize the object
 */
int
Hash_init(marshal48_Hash *self, PyObject *args, PyObject *kwds)
{
	static char *kwlist[] = {
		NULL
	};

	if (!PyArg_ParseTupleAndKeywords(args, kwds, "", kwlist))
		return -1;

	self->value = PyList_New(0);
	return 0;
}

/*
 * Destructor: clean any state inside the Hash object
 */
static void
Hash_dealloc(marshal48_Hash *self)
{
	Py_DECREF(self->value);
	self->value = NULL;
}

int
Hash_Check(PyObject *self)
{
	return PyType_IsSubtype(Py_TYPE(self), &marshal48_HashType);
}

static PyObject *
Hash_set(marshal48_Hash *self, PyObject *args)
{
	PyObject *key, *value;

	if (!PyArg_Parse(args, "OO", &key, &value))
		return NULL;

	if (PyDict_SetItem(self->value, key, value) < 0)
		return NULL;

	Py_RETURN_NONE;
}

static PyObject *
maybe_convert(PyObject *item)
{
	PyObject *cooked;

	cooked = PyObject_CallMethod(item, "convert", NULL);
	if (cooked)
		return cooked;

	return Py_INCREF(item), item;
}

static PyObject *
Hash_convert(marshal48_Hash *self, PyObject *args)
{
	PyObject *result;
	PyObject *key, *value;
	Py_ssize_t pos = 0;

	result = PyDict_New();
	while (PyDict_Next(self->value, &pos, &key, &value)) {

		key = maybe_convert(key);
		value = maybe_convert(value);

		PyDict_SetItem(result, key, value);
	}

	return result;
}
