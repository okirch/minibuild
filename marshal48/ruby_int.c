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


static void		Int_dealloc(marshal48_Int *self);
static PyObject *	Int_new(PyTypeObject *type, PyObject *args, PyObject *kwds);

static PyMemberDef Int_members[] = {
	{"value", T_STRING, offsetof(marshal48_Int, value), 0,
	 "value"},

	{NULL}  /* Sentinel */
};


PyTypeObject marshal48_IntType = {
	PyVarObject_HEAD_INIT(NULL, 0)

	.tp_name	= "marshal48.Int",
	.tp_basicsize	= sizeof(marshal48_Int),
	.tp_flags	= Py_TPFLAGS_DEFAULT,
	.tp_doc		= "ruby int",

	.tp_init	= (initproc) Int_init,
	.tp_new		= Int_new,
	.tp_dealloc	= (destructor) Int_dealloc,

	.tp_members	= Int_members,
//	.tp_methods	= marshal48_noMethods,
};

/*
 * Constructor: allocate empty Int object, and set its members.
 */
static PyObject *
Int_new(PyTypeObject *type, PyObject *args, PyObject *kwds)
{
	marshal48_Int *self;

	self = (marshal48_Int *) type->tp_alloc(type, 0);
	if (self == NULL)
		return NULL;

	/* init members */
	self->value = 0;

	return (PyObject *)self;
}

/*
 * Initialize the int object
 */
int
Int_init(marshal48_Int *self, PyObject *args, PyObject *kwds)
{
	static char *kwlist[] = {
		"value",
		NULL
	};
	int value;

	if (!PyArg_ParseTupleAndKeywords(args, kwds, "i", kwlist, &value))
		return -1;

	self->value = value;

	return 0;
}

/*
 * Destructor: clean any state inside the Int object
 */
static void
Int_dealloc(marshal48_Int *self)
{
	// NOP
}

int
Int_Check(PyObject *self)
{
	return PyType_IsSubtype(Py_TYPE(self), &marshal48_IntType);
}
