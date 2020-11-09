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


static void		UserDefined_dealloc(marshal48_UserDefined *self);
static PyObject *	UserDefined_new(PyTypeObject *type, PyObject *args, PyObject *kwds);
static PyObject *	UserDefined_construct(marshal48_UserDefined *self, PyObject *args);

static PyMemberDef UserDefined_members[] = {
	{"data", T_OBJECT, offsetof(marshal48_UserDefined, data), 0, "data"},
	{ NULL }
};

static PyMethodDef UserDefined_methods[] = {
	{ "construct", (PyCFunction) UserDefined_construct, METH_NOARGS, NULL },
	{ NULL }
};


PyTypeObject marshal48_UserDefinedType = {
	PyVarObject_HEAD_INIT(NULL, 0)

	.tp_name	= "marshal48.UserDefined",
	.tp_base	= &marshal48_GenericObjectType,
	.tp_basicsize	= sizeof(marshal48_UserDefined),
	.tp_flags	= Py_TPFLAGS_DEFAULT,
	.tp_doc		= "ruby array",

	.tp_init	= (initproc) UserDefined_init,
	.tp_new		= UserDefined_new,
	.tp_dealloc	= (destructor) UserDefined_dealloc,

	.tp_members	= UserDefined_members,
	.tp_methods	= UserDefined_methods,
};

/*
 * Constructor: allocate empty object, and set its members.
 */
static PyObject *
UserDefined_new(PyTypeObject *type, PyObject *args, PyObject *kwds)
{
	marshal48_UserDefined *self;

	self = (marshal48_UserDefined *) type->tp_alloc(type, 0);
	if (self == NULL)
		return NULL;

	/* init members */
	self->base.classname = NULL;
	self->base.instance_vars = NULL;
	self->data = NULL;

	return (PyObject *)self;
}

/*
 * Initialize the object
 */
int
UserDefined_init(marshal48_UserDefined *self, PyObject *args, PyObject *kwds)
{
	if (marshal48_GenericObjectType.tp_init((PyObject *) self, args, kwds) < 0)
		return -1;

	self->data = NULL;
	return 0;
}

/*
 * Destructor: clean any state inside the UserDefined object
 */
static void
UserDefined_dealloc(marshal48_UserDefined *self)
{
	drop_object(&self->data);
}

int
UserDefined_Check(PyObject *self)
{
	return PyType_IsSubtype(Py_TYPE(self), &marshal48_UserDefinedType);
}

/*
 * If self.data is a byte array that starts with the Marshal48 signature,
 * unmarshal it and call instance->load() with the result.
 */
static bool
UserDefined_try_unmarshal(marshal48_UserDefined *self, PyObject *instance, PyObject **argp)
{
	const char *bytes;

	if (!PyByteArray_Check(self->data) || PyByteArray_GET_SIZE(self->data) < 2)
		return false;

	bytes = PyByteArray_AS_STRING(self->data);
	if (bytes[0] != 0x04 || bytes[1] != 0x08)
		return false;

	*argp = marshal48_unmarshal_io(self->data);
	if (*argp == NULL)
		return false;

	return true;
}

static PyObject *
UserDefined_construct(marshal48_UserDefined *self, PyObject *args)
{
	PyObject *instance, *load_arg, *r;

	if (!PyArg_ParseTuple(args, "O", &instance))
		return NULL;

	if (self->data == NULL) {
		PyErr_SetString(PyExc_ValueError, "UserDefined.construct() called without data");
		return NULL;
	}

	if (!UserDefined_try_unmarshal(self, instance, &load_arg)) {
		Py_INCREF(self->data);
		load_arg = self->data;
	}

	r = PyObject_CallMethod(instance, "load", "O", load_arg);
	Py_DECREF(load_arg);

	if (r == NULL)
		return NULL;
	Py_DECREF(r);

	return 0;
}
