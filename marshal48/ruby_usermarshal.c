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


static void		UserMarshal_dealloc(marshal48_UserMarshal *self);
static PyObject *	UserMarshal_new(PyTypeObject *type, PyObject *args, PyObject *kwds);
static PyObject *	UserMarshal_construct(marshal48_UserMarshal *self, PyObject *args);

static PyMemberDef UserMarshal_members[] = {
	{"data", T_OBJECT, offsetof(marshal48_UserMarshal, data), 0, "data"},
	{ NULL }
};

static PyMethodDef UserMarshal_methods[] = {
	{ "construct", (PyCFunction) UserMarshal_construct, METH_NOARGS, NULL },
	{ NULL }
};


PyTypeObject marshal48_UserMarshalType = {
	PyVarObject_HEAD_INIT(NULL, 0)

	.tp_name	= "marshal48.UserMarshal",
	.tp_base	= &marshal48_GenericObjectType,
	.tp_basicsize	= sizeof(marshal48_UserMarshal),
	.tp_flags	= Py_TPFLAGS_DEFAULT,
	.tp_doc		= "ruby array",

	.tp_init	= (initproc) UserMarshal_init,
	.tp_new		= UserMarshal_new,
	.tp_dealloc	= (destructor) UserMarshal_dealloc,

	.tp_members	= UserMarshal_members,
	.tp_methods	= UserMarshal_methods,
};

/*
 * Constructor: allocate empty object, and set its members.
 */
static PyObject *
UserMarshal_new(PyTypeObject *type, PyObject *args, PyObject *kwds)
{
	marshal48_UserMarshal *self;

	self = (marshal48_UserMarshal *) type->tp_alloc(type, 0);
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
UserMarshal_init(marshal48_UserMarshal *self, PyObject *args, PyObject *kwds)
{
	if (marshal48_GenericObjectType.tp_init((PyObject *) self, args, kwds) < 0)
		return -1;

	self->data = NULL;
	return 0;
}

/*
 * Destructor: clean any state inside the UserMarshal object
 */
static void
UserMarshal_dealloc(marshal48_UserMarshal *self)
{
	drop_object(&self->data);
}

int
UserMarshal_Check(PyObject *self)
{
	return PyType_IsSubtype(Py_TYPE(self), &marshal48_UserMarshalType);
}

static PyObject *
UserMarshal_construct(marshal48_UserMarshal *self, PyObject *args)
{
	PyObject *instance, *r;

	if (!PyArg_ParseTuple(args, "O", &instance))
		return NULL;

	if (self->data == NULL) {
		PyErr_SetString(PyExc_ValueError, "UserMarshal.construct() called without data");
		return NULL;
	}

	r = PyObject_CallMethod(instance, "marshal_load", "O", self->data);
	if (r == NULL)
		return NULL;
	Py_DECREF(r);

	return 0;
}
